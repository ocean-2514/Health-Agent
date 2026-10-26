"""MCP (Model Context Protocol) server exposing the transformer condition
monitoring toolset to MCP clients (Claude Desktop, Claude Code, etc.).

Layout:
    server.py     - FastMCP instance with metadata
    tools.py      - @mcp.tool() registrations (thin wrappers over Tools/*)
    resources.py  - @mcp.resource() definitions (IoTDB time-series snapshots)
    prompts.py    - @mcp.prompt() guided diagnostic workflows

Entry point: ``Python/MCPMain.py`` (stdio transport by default).
"""
