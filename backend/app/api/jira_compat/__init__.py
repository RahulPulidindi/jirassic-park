"""Atlassian-shaped REST API at /rest/api/3/*.

This module exists so a tool-using agent (Claude with MCP, custom agents
talking to /rest/api/3) trained on Jirassic Park can drop into a real Jira
Cloud instance without rewriting its request/response handlers.

The shape decisions follow Atlassian's published REST v3 spec:
    https://developer.atlassian.com/cloud/jira/platform/rest/v3/

We do NOT vendor any Atlassian code; we only mirror the over-the-wire
contract (URLs, JSON keys, error envelope, pagination convention).

What's here:
    shapes.py   - to_jira_* projection functions + ADF helpers + error envelope
    ids.py      - deterministic numeric-id and accountId mappings
    router.py   - the FastAPI router mounted at /rest/api/3
    errors.py   - Jira-shape exception handler

Documented gaps live in backend/tests/fixtures/real_jira/expected_diffs.yaml.
"""

from app.api.jira_compat.router import router  # noqa: F401
