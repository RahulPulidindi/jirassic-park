"""Service layer - the single source of truth for state mutations.

REST API routes and MCP tools both delegate to these functions. This is what
makes `UI == API == MCP` provable rather than aspirational.
"""
