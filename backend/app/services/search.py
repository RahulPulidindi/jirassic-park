"""JQL-lite parser and evaluator.

Grammar (BNF-style, simplified):

    query        := or_expr [ ORDER BY order_clause ]
    or_expr      := and_expr ( OR and_expr )*
    and_expr     := not_expr ( AND not_expr )*
    not_expr     := [ NOT ] primary
    primary      := "(" or_expr ")" | comparison
    comparison   := field OP value
    OP           := "=" | "!=" | ">" | ">=" | "<" | "<=" | "in" | "not in" |
                    "~" | "!~" | "is" | "is not"
    value        := literal | function_call | list
    list         := "(" value ("," value)* ")"
    literal      := STRING | NUMBER | IDENT | RELDATE
    function_call:= IDENT "(" [ args ] ")"
    order_clause := field [ ASC | DESC ] ( "," field [ ASC | DESC ] )*

Supported fields (case-insensitive):
    id / key, summary, description, text (free-text across id+summary+
    description+comments - so `text ~ "PLAT-60"` matches PLAT-60),
    project / project_key, status, priority, issue_type / type,
    assignee / owner, reporter,
    labels, sprint, epic, parent,
    created, updated, due, due_date,
    story_points / "story points" (quoted)

Supported functions:
    currentUser()  - resolves to the calling user's id
    unassigned()   - resolves to NULL
    now()          - current datetime

Relative dates: a signed integer followed by d, w, m, or y (-7d, -2w, etc.) -
interpreted as `now() + delta`. So `created >= -7d` matches issues created in
the last 7 days.

Saved filter resolution:
    filter = "My Open Bugs"     -> recursively parsed and evaluated
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field as dc_field
from datetime import datetime, timedelta

from app.clock import now as _now
from typing import Any, Optional

from fastapi import HTTPException
from sqlalchemy import and_, exists, func, not_, or_, select
from sqlalchemy.orm import Session
from sqlalchemy.sql.elements import ColumnElement

from app.models import (
    Comment,
    Issue,
    IssueLabel,
    SavedFilter,
    Sprint,
    SprintIssue,
    User,
    WorkflowStatus,
)


# ----- AST -------------------------------------------------------------


@dataclass
class Literal:
    value: Any


@dataclass
class FunctionCall:
    name: str
    args: list["Node"] = dc_field(default_factory=list)


@dataclass
class ListExpr:
    items: list["Node"] = dc_field(default_factory=list)


@dataclass
class RelativeDate:
    delta_days: float  # signed


@dataclass
class Comparison:
    field: str
    op: str
    value: "Node"


@dataclass
class BoolOp:
    op: str  # AND | OR
    left: "Node"
    right: "Node"


@dataclass
class Not:
    expr: "Node"


@dataclass
class OrderBy:
    field: str
    desc: bool = False


@dataclass
class Query:
    where: Optional["Node"]
    order_by: list[OrderBy] = dc_field(default_factory=list)


Node = (
    Literal | FunctionCall | ListExpr | RelativeDate | Comparison | BoolOp | Not | OrderBy | Query
)


# ----- Tokenizer -------------------------------------------------------


@dataclass
class Token:
    kind: str  # ident, number, string, op, lparen, rparen, comma, reldate, eof
    value: str
    pos: int


_OPS = {"=", "!=", ">", ">=", "<", "<=", "~", "!~"}
_KEYWORDS = {"AND", "OR", "NOT", "IN", "IS", "ORDER", "BY", "ASC", "DESC"}


class Lexer:
    def __init__(self, src: str):
        self.src = src
        self.i = 0

    def tokens(self) -> list[Token]:
        out: list[Token] = []
        while self.i < len(self.src):
            c = self.src[self.i]
            if c.isspace():
                self.i += 1
                continue
            if c == "(":
                out.append(Token("lparen", c, self.i)); self.i += 1; continue
            if c == ")":
                out.append(Token("rparen", c, self.i)); self.i += 1; continue
            if c == ",":
                out.append(Token("comma", c, self.i)); self.i += 1; continue
            if c in "\"'":
                out.append(self._string(c)); continue
            # 2-char ops first
            two = self.src[self.i:self.i + 2]
            if two in ("!=", ">=", "<=", "!~"):
                out.append(Token("op", two, self.i)); self.i += 2; continue
            if c in "=<>~":
                out.append(Token("op", c, self.i)); self.i += 1; continue
            if c.isdigit() or (c == "-" and self.i + 1 < len(self.src) and self.src[self.i + 1].isdigit()):
                out.append(self._number_or_reldate()); continue
            if c.isalpha() or c == "_":
                out.append(self._ident()); continue
            raise HTTPException(400, f"JQL parse error: unexpected char {c!r} at pos {self.i}.")
        out.append(Token("eof", "", self.i))
        return out

    def _string(self, quote: str) -> Token:
        start = self.i
        self.i += 1
        buf: list[str] = []
        while self.i < len(self.src):
            c = self.src[self.i]
            if c == "\\" and self.i + 1 < len(self.src):
                buf.append(self.src[self.i + 1]); self.i += 2; continue
            if c == quote:
                self.i += 1
                return Token("string", "".join(buf), start)
            buf.append(c); self.i += 1
        raise HTTPException(400, f"JQL parse error: unterminated string starting at pos {start}.")

    def _number_or_reldate(self) -> Token:
        start = self.i
        if self.src[self.i] == "-":
            self.i += 1
        while self.i < len(self.src) and (self.src[self.i].isdigit() or self.src[self.i] == "."):
            self.i += 1
        # Maybe a relative date suffix d/w/m/y
        if self.i < len(self.src) and self.src[self.i] in "dwmy":
            self.i += 1
            return Token("reldate", self.src[start:self.i], start)
        return Token("number", self.src[start:self.i], start)

    def _ident(self) -> Token:
        start = self.i
        # Identifiers allow alnum, _, ., and - in continuation (e.g. label names
        # like "customer-reported"). Hyphen mid-word is unambiguous because the
        # lexer always tries _ident before treating '-' as a sign/operator.
        while self.i < len(self.src) and (self.src[self.i].isalnum() or self.src[self.i] in "_.-"):
            self.i += 1
        word = self.src[start:self.i]
        upper = word.upper()
        if upper in _KEYWORDS:
            return Token("kw", upper, start)
        return Token("ident", word, start)


# ----- Parser ----------------------------------------------------------


class Parser:
    def __init__(self, tokens: list[Token]):
        self.tokens = tokens
        self.i = 0

    @property
    def cur(self) -> Token:
        return self.tokens[self.i]

    def eat(self, kind: str, value: Optional[str] = None) -> Token:
        t = self.cur
        if t.kind != kind or (value is not None and t.value != value):
            raise HTTPException(400, f"JQL parse error at pos {t.pos}: expected {kind}{' '+value if value else ''}, got {t.kind}={t.value!r}.")
        self.i += 1
        return t

    def parse(self) -> Query:
        where = None
        order_by: list[OrderBy] = []
        # Empty query
        if self.cur.kind != "eof":
            # If next token is ORDER, where is None
            if not (self.cur.kind == "kw" and self.cur.value == "ORDER"):
                where = self.parse_or()
        if self.cur.kind == "kw" and self.cur.value == "ORDER":
            self.eat("kw", "ORDER")
            self.eat("kw", "BY")
            order_by = self.parse_order()
        if self.cur.kind != "eof":
            raise HTTPException(400, f"JQL parse error at pos {self.cur.pos}: trailing tokens {self.cur.value!r}.")
        return Query(where=where, order_by=order_by)

    def parse_or(self) -> Node:
        node = self.parse_and()
        while self.cur.kind == "kw" and self.cur.value == "OR":
            self.eat("kw", "OR")
            right = self.parse_and()
            node = BoolOp("OR", node, right)
        return node

    def parse_and(self) -> Node:
        node = self.parse_not()
        while self.cur.kind == "kw" and self.cur.value == "AND":
            self.eat("kw", "AND")
            right = self.parse_not()
            node = BoolOp("AND", node, right)
        return node

    def parse_not(self) -> Node:
        if self.cur.kind == "kw" and self.cur.value == "NOT":
            self.eat("kw", "NOT")
            return Not(self.parse_primary())
        return self.parse_primary()

    def parse_primary(self) -> Node:
        if self.cur.kind == "lparen":
            self.eat("lparen")
            node = self.parse_or()
            self.eat("rparen")
            return node
        return self.parse_comparison()

    def parse_comparison(self) -> Node:
        if self.cur.kind == "string":
            # Quoted field name
            field_tok = self.eat("string")
            field_name = field_tok.value
        else:
            field_tok = self.eat("ident")
            field_name = field_tok.value

        op = self._parse_op()
        value = self.parse_value()
        return Comparison(field=field_name.lower(), op=op, value=value)

    def _parse_op(self) -> str:
        # Handle multi-keyword ops: NOT IN, IS NOT
        if self.cur.kind == "kw" and self.cur.value == "IN":
            self.eat("kw", "IN")
            return "in"
        if self.cur.kind == "kw" and self.cur.value == "NOT":
            self.eat("kw", "NOT")
            self.eat("kw", "IN")
            return "not in"
        if self.cur.kind == "kw" and self.cur.value == "IS":
            self.eat("kw", "IS")
            if self.cur.kind == "kw" and self.cur.value == "NOT":
                self.eat("kw", "NOT")
                return "is not"
            return "is"
        if self.cur.kind == "op":
            t = self.eat("op")
            return t.value
        raise HTTPException(400, f"JQL parse error at pos {self.cur.pos}: expected operator, got {self.cur.value!r}.")

    def parse_value(self) -> Node:
        t = self.cur
        if t.kind == "lparen":
            self.eat("lparen")
            items = [self.parse_value()]
            while self.cur.kind == "comma":
                self.eat("comma")
                items.append(self.parse_value())
            self.eat("rparen")
            return ListExpr(items=items)
        if t.kind == "string":
            self.eat("string")
            return Literal(t.value)
        if t.kind == "number":
            self.eat("number")
            v = float(t.value) if "." in t.value else int(t.value)
            return Literal(v)
        if t.kind == "reldate":
            self.eat("reldate")
            return self._parse_reldate(t.value)
        if t.kind == "ident":
            self.eat("ident")
            # Function call?
            if self.cur.kind == "lparen":
                self.eat("lparen")
                args: list[Node] = []
                if self.cur.kind != "rparen":
                    args.append(self.parse_value())
                    while self.cur.kind == "comma":
                        self.eat("comma")
                        args.append(self.parse_value())
                self.eat("rparen")
                return FunctionCall(name=t.value.lower(), args=args)
            # Bare identifier -> string literal
            return Literal(t.value)
        raise HTTPException(400, f"JQL parse error at pos {t.pos}: expected value, got {t.kind}={t.value!r}.")

    def _parse_reldate(self, raw: str) -> RelativeDate:
        suffix = raw[-1]
        n = float(raw[:-1])
        multiplier = {"d": 1, "w": 7, "m": 30, "y": 365}[suffix]
        return RelativeDate(delta_days=n * multiplier)

    def parse_order(self) -> list[OrderBy]:
        order_by: list[OrderBy] = []
        order_by.append(self._parse_order_clause())
        while self.cur.kind == "comma":
            self.eat("comma")
            order_by.append(self._parse_order_clause())
        return order_by

    def _parse_order_clause(self) -> OrderBy:
        if self.cur.kind == "ident":
            tok = self.eat("ident")
            field_name = tok.value.lower()
        else:
            tok = self.eat("string")
            field_name = tok.value.lower()
        desc = False
        if self.cur.kind == "kw" and self.cur.value in ("ASC", "DESC"):
            kw = self.eat("kw")
            desc = kw.value == "DESC"
        return OrderBy(field=field_name, desc=desc)


def parse_jql(src: str) -> Query:
    tokens = Lexer(src or "").tokens()
    return Parser(tokens).parse()


# ----- Evaluator -------------------------------------------------------


# Field name -> (resolver function returning SQLAlchemy column expression, field "kind")
# Kind affects how we coerce values: text, status, priority, user, date, int, label, sprint, list_via_join
_FIELD_ALIASES = {
    "key": "id",
    "type": "issue_type",
    "assignee": "owner",
    "storypoints": "story_points",
    "story points": "story_points",
    "due": "due_date",
    "project_key": "project",
    "project": "project",
}


@dataclass
class EvalContext:
    db: Session
    current_user: Optional[User] = None


PRIORITY_ORDER = {"Lowest": 0, "Low": 1, "Medium": 2, "High": 3, "Highest": 4}


def evaluate(query: Query, ctx: EvalContext) -> tuple[list[Issue], int]:
    """Execute the query and return (rows, total_count).

    `limit`/`offset` callers apply separately on top.
    """
    stmt = select(Issue)
    if query.where is not None:
        stmt = stmt.where(_to_sql(query.where, ctx))

    # Counting before order/limit
    total = ctx.db.execute(select(func.count()).select_from(stmt.subquery())).scalar() or 0

    # Order
    if query.order_by:
        for ob in query.order_by:
            col = _order_column(ob.field)
            if col is None:
                continue
            stmt = stmt.order_by(col.desc() if ob.desc else col.asc())
    else:
        stmt = stmt.order_by(Issue.updated_at.desc())

    rows = ctx.db.execute(stmt).scalars().all()
    return list(rows), int(total)


def search(db: Session, jql: str, *, current_user: Optional[User] = None,
           limit: int = 50, offset: int = 0) -> tuple[list[Issue], int]:
    query = parse_jql(jql)
    ctx = EvalContext(db=db, current_user=current_user)
    all_rows, total = evaluate(query, ctx)
    return all_rows[offset:offset + limit], total


# ----- AST -> SQL ------------------------------------------------------


def _resolve_field(name: str) -> str:
    name = name.lower()
    return _FIELD_ALIASES.get(name, name)


def _to_sql(node: Node, ctx: EvalContext) -> ColumnElement:
    if isinstance(node, BoolOp):
        left = _to_sql(node.left, ctx)
        right = _to_sql(node.right, ctx)
        return and_(left, right) if node.op == "AND" else or_(left, right)
    if isinstance(node, Not):
        return not_(_to_sql(node.expr, ctx))
    if isinstance(node, Comparison):
        return _comparison_to_sql(node, ctx)
    raise HTTPException(400, f"JQL eval error: cannot eval {type(node).__name__} at top level.")


def _resolve_value(node: Node, ctx: EvalContext) -> Any:
    if isinstance(node, Literal):
        # Jira's `EMPTY` / `NULL` sentinels (bare identifiers in JQL like
        # `sprint is EMPTY` or `assignee = NULL`) resolve to None at eval
        # time. Without this, the bare identifier is treated as the string
        # "EMPTY", which is never a real sprint/user/label name and yields
        # the unhelpful "sprint does not support is." error.
        if isinstance(node.value, str) and node.value.lower() in ("empty", "null", "none"):
            return None
        return node.value
    if isinstance(node, FunctionCall):
        fname = node.name.lower()
        if fname == "currentuser":
            return ctx.current_user.id if ctx.current_user else None
        if fname == "unassigned":
            return None
        if fname == "empty" or fname == "null":
            return None
        if fname == "now":
            return _now()
        raise HTTPException(400, f"Unknown JQL function: {fname}.")
    if isinstance(node, RelativeDate):
        return _now() + timedelta(days=node.delta_days)
    if isinstance(node, ListExpr):
        return [_resolve_value(n, ctx) for n in node.items]
    raise HTTPException(400, f"JQL eval error: cannot resolve {type(node).__name__} as value.")


def _comparison_to_sql(node: Comparison, ctx: EvalContext) -> ColumnElement:
    field = _resolve_field(node.field)
    value = _resolve_value(node.value, ctx)

    # ---- Saved-filter expansion ----
    if field == "filter":
        if not isinstance(value, str):
            raise HTTPException(422, "filter = expects a string filter name.")
        sf = ctx.db.query(SavedFilter).filter(SavedFilter.name == value).one_or_none()
        if sf is None:
            sf = ctx.db.query(SavedFilter).filter(SavedFilter.id == value).one_or_none()
        if sf is None:
            raise HTTPException(404, f"Saved filter '{value}' not found.")
        sub_query = parse_jql(sf.jql)
        if sub_query.where is None:
            return Issue.id == Issue.id  # always true
        if node.op == "=":
            return _to_sql(sub_query.where, ctx)
        if node.op == "!=":
            return not_(_to_sql(sub_query.where, ctx))
        raise HTTPException(422, "filter only supports = and !=.")

    # ---- Status: by name ----
    if field == "status":
        sub = select(WorkflowStatus.id).where(WorkflowStatus.name == value).scalar_subquery() if isinstance(value, str) else None
        return _status_filter(node.op, value)

    # ---- Priority ----
    if field == "priority":
        return _string_filter(Issue.priority, node.op, value)

    # ---- Issue type ----
    if field == "issue_type":
        return _string_filter(Issue.issue_type, node.op, value)

    # ---- Project ----
    if field == "project":
        return _string_filter(Issue.project_key, node.op, value)

    # ---- Resolution ----
    if field == "resolution":
        return _string_filter(Issue.resolution, node.op, value)

    # ---- Assignee/Reporter ----
    if field == "owner":
        return _user_filter(Issue.owner, node.op, value, ctx)
    if field == "reporter":
        return _user_filter(Issue.reporter, node.op, value, ctx)

    # ---- Story points / numeric ----
    if field == "story_points":
        return _numeric_filter(Issue.story_points, node.op, value)

    # ---- Dates ----
    if field == "created":
        return _date_filter(Issue.created_at, node.op, value)
    if field == "updated":
        return _date_filter(Issue.updated_at, node.op, value)
    if field == "due_date":
        return _date_filter(Issue.due_date, node.op, value)

    # ---- ID / key / summary / description ----
    if field == "id":
        return _string_filter(Issue.id, node.op, value)
    if field == "summary":
        return _string_filter(Issue.summary, node.op, value, allow_substring=True)
    if field == "description":
        return _string_filter(Issue.description, node.op, value, allow_substring=True)

    # ---- Text search across id+summary+description+comments ----
    # Issue.id is included so the global quick-search ("PLAT-60") locates the
    # issue even when no body text mentions the key. This mirrors Jira's
    # behavior where the search bar resolves keys as a first-class hit.
    if field == "text":
        if not isinstance(value, str):
            raise HTTPException(422, "text expects a string value.")
        like = f"%{value.lower()}%"
        comment_match = exists(
            select(1)
            .where(Comment.issue_id == Issue.id)
            .where(func.lower(Comment.body).like(like))
            .correlate(Issue)
        )
        match = or_(
            func.lower(Issue.id).like(like),
            func.lower(Issue.summary).like(like),
            and_(Issue.description.is_not(None), func.lower(Issue.description).like(like)),
            comment_match,
        )
        if node.op == "~":
            return match
        if node.op == "!~":
            return not_(match)
        raise HTTPException(422, "text supports ~ and !~ only.")

    # ---- Labels (joined) ----
    if field == "labels":
        sub_query = lambda val: select(1).where(IssueLabel.issue_id == Issue.id).where(IssueLabel.label_name == val).correlate(Issue)
        if isinstance(value, list):
            anys = or_(*[exists(sub_query(v)) for v in value])
            if node.op == "in" or node.op == "=":
                return anys
            if node.op == "not in" or node.op == "!=":
                return not_(anys)
            raise HTTPException(422, f"labels does not support {node.op} with a list.")
        if value is None and node.op in ("is", "="):
            return ~exists(select(1).where(IssueLabel.issue_id == Issue.id).correlate(Issue))
        if value is None and node.op in ("is not", "!="):
            return exists(select(1).where(IssueLabel.issue_id == Issue.id).correlate(Issue))
        if node.op == "=":
            return exists(sub_query(value))
        if node.op == "!=":
            return not_(exists(sub_query(value)))
        raise HTTPException(422, f"labels does not support {node.op}.")

    # ---- Sprint (joined via SprintIssue, by name or id) ----
    if field == "sprint":
        def sprint_subq(val):
            return (
                select(1)
                .select_from(SprintIssue)
                .join(Sprint, SprintIssue.sprint_id == Sprint.id)
                .where(SprintIssue.issue_id == Issue.id)
                .where(or_(Sprint.id == val, Sprint.name == val))
                .correlate(Issue)
            )
        if isinstance(value, list):
            anys = or_(*[exists(sprint_subq(v)) for v in value])
            if node.op in ("in", "="):
                return anys
            if node.op in ("not in", "!="):
                return not_(anys)
        if value is None and node.op in ("is", "="):
            return ~exists(select(1).select_from(SprintIssue).where(SprintIssue.issue_id == Issue.id).correlate(Issue))
        if value is None and node.op in ("is not", "!="):
            return exists(select(1).select_from(SprintIssue).where(SprintIssue.issue_id == Issue.id).correlate(Issue))
        if node.op == "=":
            return exists(sprint_subq(value))
        if node.op == "!=":
            return not_(exists(sprint_subq(value)))
        raise HTTPException(422, f"sprint does not support {node.op}.")

    # ---- Epic / parent ----
    if field == "epic":
        return _string_filter(Issue.epic_id, node.op, value, none_ok=True)
    if field == "parent":
        return _string_filter(Issue.parent_id, node.op, value, none_ok=True)

    raise HTTPException(400, f"Unknown JQL field: {field}.")


def _string_filter(col, op: str, value, allow_substring: bool = False, none_ok: bool = False) -> ColumnElement:
    if value is None:
        if op in ("=", "is"):
            return col.is_(None)
        if op in ("!=", "is not"):
            return col.is_not(None)
        raise HTTPException(422, f"Operator {op} doesn't support NULL.")
    if isinstance(value, list):
        if op in ("in", "="):
            return col.in_(value)
        if op in ("not in", "!="):
            return ~col.in_(value)
        raise HTTPException(422, f"Operator {op} doesn't accept a list.")
    if op == "=":
        return col == value
    if op == "!=":
        return col != value
    if op == "~":
        if not allow_substring:
            raise HTTPException(422, "~ only allowed on text-type fields.")
        return func.lower(col).like(f"%{str(value).lower()}%")
    if op == "!~":
        if not allow_substring:
            raise HTTPException(422, "!~ only allowed on text-type fields.")
        return not_(func.lower(col).like(f"%{str(value).lower()}%"))
    if op in (">", ">=", "<", "<="):
        return _cmp_op(col, op, value)
    raise HTTPException(422, f"Operator {op} not supported on this field.")


def _user_filter(col, op: str, value, ctx: EvalContext) -> ColumnElement:
    # value may be a user id, or a function call already-resolved to user.id, or None (unassigned)
    if value is None or (isinstance(value, str) and value.lower() == "unassigned"):
        if op in ("=", "is"):
            return col.is_(None)
        if op in ("!=", "is not"):
            return col.is_not(None)
    if isinstance(value, str):
        # Allow matching by user name too
        user = (
            ctx.db.query(User)
            .filter((User.id == value) | (User.name == value) | (User.display_name == value))
            .first()
        )
        resolved = user.id if user else value
        return _string_filter(col, op, resolved)
    if isinstance(value, list):
        resolved = []
        for v in value:
            if v is None:
                continue
            u = ctx.db.query(User).filter((User.id == v) | (User.name == v) | (User.display_name == v)).first()
            resolved.append(u.id if u else v)
        return _string_filter(col, op, resolved)
    return _string_filter(col, op, value)


def _numeric_filter(col, op: str, value) -> ColumnElement:
    if value is None:
        if op in ("=", "is"):
            return col.is_(None)
        if op in ("!=", "is not"):
            return col.is_not(None)
    if isinstance(value, list):
        if op in ("in", "="):
            return col.in_(value)
        if op in ("not in", "!="):
            return ~col.in_(value)
    return _cmp_op(col, op, value)


def _date_filter(col, op: str, value) -> ColumnElement:
    if isinstance(value, str):
        # ISO-like date
        try:
            value = datetime.fromisoformat(value)
        except ValueError:
            pass
    return _cmp_op(col, op, value)


def _cmp_op(col, op: str, value) -> ColumnElement:
    if op == "=":
        return col == value
    if op == "!=":
        return col != value
    if op == ">":
        return col > value
    if op == ">=":
        return col >= value
    if op == "<":
        return col < value
    if op == "<=":
        return col <= value
    raise HTTPException(422, f"Operator {op} not supported here.")


def _status_filter(op: str, value) -> ColumnElement:
    if isinstance(value, list):
        sub = select(WorkflowStatus.id).where(WorkflowStatus.name.in_(value))
        if op in ("in", "="):
            return Issue.status_id.in_(sub)
        if op in ("not in", "!="):
            return ~Issue.status_id.in_(sub)
    if value is None:
        return Issue.status_id.is_(None) if op in ("=", "is") else Issue.status_id.is_not(None)
    sub = select(WorkflowStatus.id).where(WorkflowStatus.name == value)
    if op == "=":
        return Issue.status_id.in_(sub)
    if op == "!=":
        return ~Issue.status_id.in_(sub)
    raise HTTPException(422, f"status does not support {op}.")


def _order_column(field: str):
    f = _resolve_field(field)
    if f == "priority":
        return Issue.priority  # NB: lexical order; documented in architecture.md
    if f == "status":
        return Issue.status_id
    if f == "owner":
        return Issue.owner
    if f == "reporter":
        return Issue.reporter
    if f == "created":
        return Issue.created_at
    if f == "updated":
        return Issue.updated_at
    if f == "due_date":
        return Issue.due_date
    if f == "story_points":
        return Issue.story_points
    if f == "id":
        return Issue.id
    if f == "summary":
        return Issue.summary
    if f == "project":
        return Issue.project_key
    if f == "issue_type":
        return Issue.issue_type
    return None
