"""Deterministic id mappings between Jirassic Park's string ids and the
opaque numeric/hex ids that real Jira returns.

Real Jira uses:
- Issue id  : integer string ("10234")           — key is the human label ("PLAT-60")
- User      : accountId (24-char hex)
- Project   : numeric id
- Status    : numeric id (per workflow)
- Priority  : numeric id
- IssueType : numeric id
- Comment   : numeric id

We derive each id by hashing the canonical Jirassic Park id. Stable across
restarts so contract tests can compare against a captured fixture by exact
value, and so agents that store references by id (rather than key) don't
break when the seed is rebuilt.
"""

from __future__ import annotations

import hashlib


def _hash_int(s: str, mod: int = 99_990_000, base: int = 10_000) -> int:
    """Hash a string to a stable numeric id in [base, base + mod)."""
    h = hashlib.sha1(s.encode("utf-8")).hexdigest()
    return base + (int(h[:10], 16) % mod)


def numeric_id_for_issue(issue_key: str) -> str:
    """e.g. 'PLAT-60' -> '10000234'. Returned as a string because Jira sends
    it as a string in JSON despite being a numeric id (Atlassian convention)."""
    return str(_hash_int(f"issue:{issue_key}"))


def numeric_id_for_project(project_key: str) -> str:
    return str(_hash_int(f"project:{project_key}", mod=99_000, base=10_000))


def numeric_id_for_status(status_id: str) -> str:
    return str(_hash_int(f"status:{status_id}", mod=99_000, base=1_000))


def numeric_id_for_priority(priority_name: str) -> str:
    # Real Jira's default priorities are well-known ids 1-5.
    fixed = {"Highest": "1", "High": "2", "Medium": "3", "Low": "4", "Lowest": "5"}
    if priority_name in fixed:
        return fixed[priority_name]
    return str(_hash_int(f"priority:{priority_name}", mod=99_000, base=1_000))


def numeric_id_for_issuetype(issue_type: str) -> str:
    # Atlassian's well-known issue-type ids are 1-7 in default schemes.
    fixed = {"Bug": "1", "New Feature": "2", "Task": "3", "Improvement": "4",
             "Story": "10001", "Epic": "10000", "Subtask": "5"}
    if issue_type in fixed:
        return fixed[issue_type]
    return str(_hash_int(f"issuetype:{issue_type}", mod=99_000, base=10_000))


def numeric_id_for_comment(comment_id: str) -> str:
    return str(_hash_int(f"comment:{comment_id}"))


def numeric_id_for_link(link_id: str) -> str:
    return str(_hash_int(f"link:{link_id}"))


def account_id_for(user_id: str) -> str:
    """Real Jira's accountId is a 24-char identifier. We use a 24-char hex
    digest so the shape matches."""
    return hashlib.sha1(f"account:{user_id}".encode()).hexdigest()[:24]
