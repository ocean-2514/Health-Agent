"""HealthAgent MCP server entry point (stdio transport).

Run with the project's conda env:

    conda run -n healthAgent python Python/MCPMain.py

Or in Claude Desktop's claude_desktop_config.json:

    {
      "mcpServers": {
        "healthagent": {
          "command": "D:\\\\Users\\\\<you>\\\\anaconda3\\\\envs\\\\healthAgent\\\\python.exe",
          "args": ["D:\\\\code\\\\AI\\\\project\\\\HealthAgent\\\\Python\\\\MCPMain.py"]
        }
      }
    }
"""
from __future__ import annotations

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from Python.Src.MCP.server import mcp


def main() -> None:
    # Default transport is stdio (None == stdio in FastMCP 3.x).
    # For HTTP/SSE deployment, change to mcp.run(transport="http", host="0.0.0.0", port=8765)
    mcp.run()


if __name__ == "__main__":
    main()
