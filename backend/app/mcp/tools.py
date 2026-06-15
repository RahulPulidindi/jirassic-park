"""MCP tools. Populated during the MCP phase."""

from __future__ import annotations


def register_tools(mcp) -> None:  # noqa: ANN001 - typed by caller
    """Register all jira_* tools on the given FastMCP instance.

    Two tool families are registered:

    1. **jira_*** — our canonical, descriptively-named tools (e.g.
       `jira_get_issue`, `jira_transition_issue`). These take Jirassic Park's
       native types (snake_case args, user ids like 'user_sarah_kim',
       priority names like 'Medium').

    2. **camelCase aliases** matching Atlassian's official MCP server
       (`getJiraIssue`, `editJiraIssue`, `transitionJiraIssue`, ...). These
       exist so an agent that learned to call those exact tool names against
       a real Atlassian MCP can call ours unchanged. Aliases share underlying
       impls and add minimal arg-shape adaptation (e.g. `issueIdOrKey` ->
       internal `id`, `accountId` reverse-lookup -> user id).
    """
    from app.mcp import tools_impl, tools_atlassian_aliases

    tools_impl.register(mcp)
    tools_atlassian_aliases.register(mcp)
