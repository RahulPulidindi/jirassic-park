#!/usr/bin/env python3
"""End-to-end MCP smoke test against a running Jirassic Park server.

Connects to http://localhost:8080/mcp using the standard Streamable HTTP MCP
transport, lists the available `jira_*` tools, and walks through a small
representative flow (whoami -> summarize -> search -> create -> transition ->
history). Prints everything in human-readable form.

Usage (with the container or local backend running):

    python backend/scripts/mcp_demo.py
    # or against a non-default URL / token:
    MCP_URL=http://localhost:8080/mcp JP_ADMIN_TOKEN=admin-token-jurassic \
        python backend/scripts/mcp_demo.py
"""

from __future__ import annotations

import asyncio
import json
import os
import sys
from typing import Any

from mcp import ClientSession
from mcp.client.streamable_http import streamablehttp_client


MCP_URL = os.environ.get("MCP_URL", "http://localhost:8080/mcp/")
TOKEN = os.environ.get("JP_ADMIN_TOKEN", "admin-token-jurassic")


def _banner(msg: str) -> None:
    print(f"\n\033[1;36m== {msg} ==\033[0m")


def _payload(result) -> Any:
    """Pull JSON out of a CallToolResult.

    FastMCP returns list-shaped tool outputs as `structuredContent={"result":[...]}` and
    splits them across multiple TextContent blocks. Prefer structuredContent when
    available; fall back to parsing the first text block.
    """
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


async def main() -> int:
    print(f"Connecting to {MCP_URL} ...")
    try:
        async with streamablehttp_client(MCP_URL) as (read, write, _meta):
            async with ClientSession(read, write) as session:
                await session.initialize()

                _banner("1. List available tools")
                tools = await session.list_tools()
                names = sorted(t.name for t in tools.tools)
                print(f"   server exposes {len(names)} tools:")
                for n in names:
                    print(f"     - {n}")

                _banner("2. jira_whoami")
                me = _payload(
                    await session.call_tool("jira_whoami", {"auth_token": TOKEN})
                )
                print(json.dumps(me, indent=2))

                _banner("3. jira_summarize_project key=SCRUM")
                summary = _payload(
                    await session.call_tool(
                        "jira_summarize_project",
                        {"auth_token": TOKEN, "key": "SCRUM"},
                    )
                )
                print(json.dumps(summary, indent=2)[:600], "...")

                _banner("4. jira_search  jql='priority = Highest AND status != Done'")
                search = _payload(
                    await session.call_tool(
                        "jira_search",
                        {
                            "auth_token": TOKEN,
                            "jql": "priority = Highest AND status != Done",
                            "limit": 5,
                        },
                    )
                )
                if isinstance(search, dict):
                    print(f"   total: {search.get('total')}")
                    for i in search.get("issues", [])[:5]:
                        print(f"     {i['id']:10s}  [{i['status']:>12s}]  {i['summary'][:60]}")

                _banner("5. jira_create_issue (PLAT bug, then transition + comment)")
                created = _payload(
                    await session.call_tool(
                        "jira_create_issue",
                        {
                            "auth_token": TOKEN,
                            "project_key": "PLAT",
                            "issue_type": "Bug",
                            "summary": "MCP smoke test bug",
                            "description": "Created by mcp_demo.py.",
                            "priority": "Medium",
                            "labels": ["mcp-smoke"],
                        },
                    )
                )
                iid = created["id"]
                print(f"   created {iid} status='{created['status']}'")

                transitioned = _payload(
                    await session.call_tool(
                        "jira_transition_issue",
                        {
                            "auth_token": TOKEN,
                            "id": iid,
                            "to_status": "In Progress",
                            "comment": "Starting on this from MCP.",
                        },
                    )
                )
                print(f"   transitioned {iid} -> '{transitioned['status']}'")

                _banner("6. jira_set_sprint  move {} to the active sprint in its project".format(iid))
                sprints = _payload(
                    await session.call_tool(
                        "jira_list_sprints",
                        {"auth_token": TOKEN, "project_key": iid.split("-")[0]},
                    )
                ) or []
                active = next((s for s in sprints if s["state"] == "active"), None)
                if active:
                    moved = _payload(
                        await session.call_tool(
                            "jira_set_sprint",
                            {"auth_token": TOKEN, "id": iid, "sprint_id": active["id"]},
                        )
                    )
                    print(
                        f"   sprint_id={moved.get('sprint_id')}  sprint_name={moved.get('sprint_name')!r}"
                    )
                    backlog = _payload(
                        await session.call_tool(
                            "jira_set_sprint",
                            {"auth_token": TOKEN, "id": iid, "sprint_id": None},
                        )
                    )
                    print(
                        f"   moved back to backlog: sprint_id={backlog.get('sprint_id')}"
                    )
                else:
                    print("   (no active SCRUM sprint in seed -- skipping)")

                _banner("7. jira_get_clock + @mention round-trip")
                clock_state = _payload(
                    await session.call_tool("jira_get_clock", {"auth_token": TOKEN})
                )
                print(
                    f"   clock: mode={clock_state['mode']}  now={clock_state['now']}"
                )

                # Mention a real user. The notifications feed for that user is
                # the source of truth for what got delivered, and identical
                # whether you read it via REST or MCP.
                mention_iid = iid
                await session.call_tool(
                    "jira_add_comment",
                    {
                        "auth_token": TOKEN,
                        "id": mention_iid,
                        "body": "Heads up @priya_iyer please take a look.",
                    },
                )
                priya_token = "token_priya_iyer"
                feed = _payload(
                    await session.call_tool(
                        "jira_my_mentions", {"auth_token": priya_token, "limit": 5}
                    )
                ) or []
                print(f"   priya inbox: {len(feed)} mention(s)")
                for row in feed[:3]:
                    print(
                        f"     {row['actor_id']} -> {row['to_value']} in {row['issue_id']}: "
                        f"{(row.get('comment_body') or '')[:60]}"
                    )

                _banner("8. jira_get_history  id={}".format(iid))
                history = _payload(
                    await session.call_tool(
                        "jira_get_history", {"auth_token": TOKEN, "id": iid}
                    )
                )
                for row in history or []:
                    print(
                        f"   {row['action']:12s}  field={row['field'] or '-':10s}"
                        f"  {row['from_value']} -> {row['to_value']}"
                    )

                _banner("9. Negative test: illegal transition is reported as a tool error")
                bad = await session.call_tool(
                    "jira_transition_issue",
                    {
                        "auth_token": TOKEN,
                        "id": iid,
                        "to_status": "Banana Republic",
                    },
                )
                if not bad.isError:
                    print("   ERROR: server accepted a bogus transition (bug)")
                    return 1
                msg = bad.content[0].text if bad.content else "(no message)"
                print(f"   OK, server rejected as expected:\n     {msg}")

                _banner("10. New-tool surface walk (workflow, link, watch, clock)")

                # 10a: jira_get_workflow - what statuses exist for PLAT?
                wf = _payload(
                    await session.call_tool(
                        "jira_get_workflow", {"auth_token": TOKEN, "project_key": "PLAT"}
                    )
                )
                names = ", ".join(s["name"] for s in wf["statuses"])
                print(f"    workflow PLAT has {len(wf['statuses'])} statuses: {names}")

                # 10b: jira_link_issues + jira_unlink_issues round-trip on the bug we made
                peer = _payload(
                    await session.call_tool(
                        "jira_search",
                        {"auth_token": TOKEN, "jql": "project = PLAT AND id != \"" + iid + "\"", "limit": 1},
                    )
                )["issues"][0]
                link = _payload(
                    await session.call_tool(
                        "jira_link_issues",
                        {"auth_token": TOKEN, "source": iid, "target": peer["id"], "link_type": "blocks"},
                    )
                )
                print(f"    linked {iid} -[blocks]-> {peer['id']}")
                _payload(
                    await session.call_tool(
                        "jira_unlink_issues",
                        {"auth_token": TOKEN, "source": iid, "target": peer["id"], "link_type": "blocks"},
                    )
                )
                print(f"    unlinked again — link history both ways in jira_get_history")

                # 10c: jira_watch_issue + jira_unwatch_issue (idempotent)
                watched = _payload(
                    await session.call_tool("jira_watch_issue", {"auth_token": TOKEN, "id": iid})
                )
                print(f"    watching: {watched['watchers']}")
                _payload(
                    await session.call_tool("jira_unwatch_issue", {"auth_token": TOKEN, "id": iid})
                )

                # 10d: jira_set_clock (admin only) -> frozen, then back to real
                before = _payload(
                    await session.call_tool("jira_get_clock", {"auth_token": TOKEN})
                )
                _payload(
                    await session.call_tool(
                        "jira_set_clock",
                        {
                            "auth_token": TOKEN,
                            "mode": "frozen",
                            "at": "2030-01-01T00:00:00Z",
                        },
                    )
                )
                frozen = _payload(
                    await session.call_tool("jira_get_clock", {"auth_token": TOKEN})
                )
                print(f"    clock: {before['mode']} ({before['now'][:19]}) -> {frozen['mode']} ({frozen['now'][:19]})")
                _payload(
                    await session.call_tool(
                        "jira_set_clock", {"auth_token": TOKEN, "mode": "real"}
                    )
                )

                _banner("Done. All MCP tool calls round-tripped.")
                return 0

    except BaseException as e:
        # Unwrap ExceptionGroups (TaskGroup wraps sub-exceptions).
        def _flatten(exc):
            if hasattr(exc, "exceptions") and exc.exceptions:
                for sub in exc.exceptions:
                    yield from _flatten(sub)
            else:
                yield exc
        for sub in _flatten(e):
            print(f"\n\033[1;31mFAILED:\033[0m {type(sub).__name__}: {sub}")
        print("Is the server running?  Try: make run  (or: uvicorn ...).")
        return 2


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
