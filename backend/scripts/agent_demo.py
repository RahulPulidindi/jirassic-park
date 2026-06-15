#!/usr/bin/env python3
"""Drive the Jirassic Park MCP server with a real LLM (Anthropic Claude).

This is a *demonstration*, not a benchmark. It shows that an AI agent — armed
with nothing but the MCP server's tool catalog and a natural-language goal —
can accomplish a realistic, multi-step Jira workflow end-to-end.

Workflow demoed:

    "Customer support ticket SUP-1 needs to be escalated to engineering."

The agent must, without further instruction, decide to:
  1. Read SUP-1 to understand the customer complaint.
  2. Discover the PLAT (platform engineering) project lead.
  3. File a clean engineering bug in PLAT mirroring the customer report.
  4. Link the two issues so the support ticket points to the new bug.
  5. Assign the new bug to the PLAT lead.
  6. Add a comment back on SUP-1 telling the customer it has been escalated.

The agent discovers everything else (tool names, schemas, who leads PLAT,
link types, issue type names) through the MCP server itself.

Prerequisites:
  - Jirassic Park container running on localhost:8080 (see `make up`).
  - `ANTHROPIC_API_KEY` exported.
  - `anthropic` SDK installed (`pip install -e .[agent]` in backend/).

Usage:
    ANTHROPIC_API_KEY=sk-ant-... python backend/scripts/agent_demo.py
"""

from __future__ import annotations

import asyncio
import json
import os
import sys
from typing import Any

try:
    from anthropic import Anthropic
except ImportError:  # pragma: no cover
    print(
        "ERROR: anthropic SDK is not installed.\n"
        "Install with:  pip install -e backend/[agent]\n"
        "or rebuild the container which already pins it.",
        file=sys.stderr,
    )
    sys.exit(2)

from mcp import ClientSession
from mcp.client.streamable_http import streamablehttp_client


MCP_URL = os.environ.get("MCP_URL", "http://localhost:8080/mcp/")
TOKEN = os.environ.get("JP_ADMIN_TOKEN", "admin-token-jurassic")
MODEL = os.environ.get("AGENT_MODEL", "claude-sonnet-4-5")
MAX_TURNS = int(os.environ.get("AGENT_MAX_TURNS", "20"))

SYSTEM_PROMPT = """You are a project-management assistant operating inside a
Jira-like system. Every action you take must go through the MCP tools the
environment exposes; you cannot edit the database directly.

You have full access to the tool catalog the user sees. Use it.

When you accomplish a multi-step goal:
  - Read first. Don't guess identifiers — look them up with the discovery tools.
  - Be concise in summaries you write into the system, but precise.
  - When you create or modify something, immediately tell the user (in your
    plain-text reply) exactly what you did and what the resulting IDs are.
  - Stop and reply when the goal is complete. Don't keep poking around.
"""

USER_TASK = """A customer reported issue SUP-1. Please escalate it to the
platform-engineering team (project key PLAT).

Concretely: create a Bug in PLAT that describes the underlying engineering
problem (write a clean, engineer-facing summary and description based on what
the customer said), link SUP-1 to it, assign the new bug to whoever leads the
PLAT project, and leave a comment on SUP-1 telling the customer it has been
escalated and quoting the new bug's ID.

When you're done, reply with a one-paragraph summary of what you did and the
new bug's ID.
"""


# ----- pretty printing ------------------------------------------------------


def _banner(msg: str, color: str = "36") -> None:
    print(f"\n\033[1;{color}m== {msg} ==\033[0m")


def _dim(msg: str) -> str:
    return f"\033[2m{msg}\033[0m"


def _green(msg: str) -> str:
    return f"\033[32m{msg}\033[0m"


def _yellow(msg: str) -> str:
    return f"\033[33m{msg}\033[0m"


def _truncate(s: str, n: int = 400) -> str:
    s = s if isinstance(s, str) else json.dumps(s, default=str)
    if len(s) <= n:
        return s
    return s[:n] + _dim(f"  …(+{len(s) - n} chars)")


# ----- MCP helpers ----------------------------------------------------------


def _payload(result) -> Any:
    """Pull JSON out of a CallToolResult (handles structuredContent + text)."""
    sc = getattr(result, "structuredContent", None) or getattr(result, "structured_content", None)
    if isinstance(sc, dict) and "result" in sc:
        return sc["result"]
    if isinstance(sc, dict):
        return sc
    if not result.content:
        return None
    first = result.content[0]
    text = getattr(first, "text", str(first))
    try:
        return json.loads(text)
    except (TypeError, json.JSONDecodeError):
        return text


def _strip_auth(schema: dict[str, Any]) -> dict[str, Any]:
    """Remove the auth_token field from a tool's input schema.

    The MCP server requires auth_token on every call, but it's an environment
    detail the agent shouldn't have to reason about. We hide it from the LLM
    and inject it automatically on every call.
    """
    if not isinstance(schema, dict):
        return {"type": "object", "properties": {}}
    schema = json.loads(json.dumps(schema))  # deep copy
    props = schema.get("properties") or {}
    props.pop("auth_token", None)
    schema["properties"] = props
    req = schema.get("required") or []
    schema["required"] = [r for r in req if r != "auth_token"]
    return schema


def _tools_for_anthropic(mcp_tools) -> list[dict[str, Any]]:
    out = []
    for t in mcp_tools:
        out.append(
            {
                "name": t.name,
                "description": (t.description or "").strip(),
                "input_schema": _strip_auth(t.inputSchema or {"type": "object", "properties": {}}),
            }
        )
    return out


# ----- agent loop -----------------------------------------------------------


async def run_agent() -> int:
    if "ANTHROPIC_API_KEY" not in os.environ:
        print("ERROR: ANTHROPIC_API_KEY is not set.", file=sys.stderr)
        return 2

    anthropic = Anthropic()

    _banner(f"Connecting to MCP at {MCP_URL}")
    async with streamablehttp_client(MCP_URL) as (read, write, _meta):
        async with ClientSession(read, write) as session:
            await session.initialize()
            tool_list = await session.list_tools()
            tools = _tools_for_anthropic(tool_list.tools)
            print(f"   exposed {len(tools)} MCP tools to the agent")

            _banner("Task", "35")
            print(USER_TASK.strip())

            messages: list[dict[str, Any]] = [
                {"role": "user", "content": USER_TASK}
            ]

            steps_taken = 0
            for turn in range(1, MAX_TURNS + 1):
                _banner(f"Turn {turn} — Claude is thinking…")
                response = anthropic.messages.create(
                    model=MODEL,
                    max_tokens=4096,
                    system=SYSTEM_PROMPT,
                    tools=tools,
                    messages=messages,
                )

                # Echo the assistant turn (text + planned tool calls).
                assistant_blocks: list[dict[str, Any]] = []
                tool_uses: list[dict[str, Any]] = []
                for block in response.content:
                    if block.type == "text":
                        text = block.text.strip()
                        if text:
                            print(_green(text))
                        assistant_blocks.append({"type": "text", "text": block.text})
                    elif block.type == "tool_use":
                        steps_taken += 1
                        args_preview = {k: v for k, v in (block.input or {}).items()}
                        print(
                            _yellow(f"→ {block.name}")
                            + _dim(f"  {_truncate(json.dumps(args_preview, default=str), 220)}")
                        )
                        tool_uses.append(
                            {
                                "type": "tool_use",
                                "id": block.id,
                                "name": block.name,
                                "input": block.input,
                            }
                        )
                        assistant_blocks.append(tool_uses[-1])
                    else:
                        assistant_blocks.append({"type": block.type})

                messages.append({"role": "assistant", "content": assistant_blocks})

                if response.stop_reason != "tool_use" or not tool_uses:
                    _banner("Agent finished", "32")
                    return await _print_aftermath(session, steps_taken)

                # Execute every requested tool call through MCP, then feed
                # results back in a single user turn.
                tool_results: list[dict[str, Any]] = []
                for tu in tool_uses:
                    args = dict(tu["input"] or {})
                    args["auth_token"] = TOKEN  # inject env credential
                    try:
                        result = await session.call_tool(tu["name"], args)
                        payload = _payload(result)
                        is_error = bool(getattr(result, "isError", False))
                        text = json.dumps(payload, default=str)
                    except Exception as exc:  # pragma: no cover - surface to LLM
                        payload = {"error": str(exc)}
                        is_error = True
                        text = json.dumps(payload)
                    color = "31" if is_error else "0"
                    print(
                        f"\033[{color}m← {tu['name']}\033[0m  "
                        + _dim(_truncate(text, 400))
                    )
                    tool_results.append(
                        {
                            "type": "tool_result",
                            "tool_use_id": tu["id"],
                            "content": text,
                            "is_error": is_error,
                        }
                    )

                messages.append({"role": "user", "content": tool_results})

            print(_yellow(f"Hit MAX_TURNS={MAX_TURNS}. Stopping."))
            return await _print_aftermath(session, steps_taken)

    return 0


async def _print_aftermath(session: ClientSession, steps_taken: int) -> int:
    """After the agent finishes, print proof of work: the SUP ticket state +
    the activities log so a reviewer can audit what actually happened."""
    _banner("Aftermath — fetching real state from the database via MCP", "34")
    print(_dim(f"(agent issued {steps_taken} tool call(s) total)"))

    sup = _payload(await session.call_tool("jira_get_issue", {"auth_token": TOKEN, "id": "SUP-1"}))
    if isinstance(sup, dict):
        print()
        print(_yellow("SUP-1 after the agent's work:"))
        print(f"  status:     {sup.get('status')}")
        print(f"  owner:      {sup.get('owner')}")
        out_links = sup.get("outbound_links") or []
        in_links = sup.get("inbound_links") or []
        all_links = out_links + in_links
        if all_links:
            print(f"  links:      {len(all_links)}")
            for ln in all_links:
                arrow = "→" if ln in out_links else "←"
                other = ln.get("target_id") if ln in out_links else ln.get("source_id")
                print(f"    {arrow} {ln.get('link_type'):>10}  {other}")
        comments = sup.get("recent_comments") or []
        if comments:
            print(f"  comments:   {len(comments)} on issue (showing newest)")
            last = comments[-1]
            print(f"    by {last.get('author_id')}: {_truncate(last.get('body', ''), 240)}")

        # Fetch + print any PLAT bug the agent linked SUP-1 to.
        plat_ids = sorted({
            ln.get("target_id")
            for ln in out_links
            if str(ln.get("target_id", "")).startswith("PLAT-")
        })
        for pid in plat_ids:
            bug = _payload(await session.call_tool("jira_get_issue", {"auth_token": TOKEN, "id": pid}))
            if isinstance(bug, dict):
                print()
                print(_yellow(f"{pid} (created by the agent):"))
                print(f"  type:       {bug.get('issue_type')}")
                print(f"  summary:    {bug.get('summary')}")
                print(f"  owner:      {bug.get('owner')}")
                print(f"  status:     {bug.get('status')}")
                desc = bug.get("description") or ""
                if desc:
                    print(f"  description: {_truncate(desc, 300)}")

    return 0


# ----- entrypoint -----------------------------------------------------------


def main() -> int:
    try:
        return asyncio.run(run_agent())
    except KeyboardInterrupt:
        return 130


if __name__ == "__main__":
    sys.exit(main())
