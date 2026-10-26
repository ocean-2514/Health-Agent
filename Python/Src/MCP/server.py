"""FastMCP server instance for HealthAgent transformer condition monitoring.

Importing this module registers all tools, resources, and prompts onto
the singleton ``mcp`` object. Callers (e.g. ``Python/MCPMain.py``) then
just call ``mcp.run()`` to start the stdio transport.
"""
from __future__ import annotations

import sys
from pathlib import Path

project_root = str(Path(__file__).resolve().parent.parent.parent.parent)
if project_root not in sys.path:
    sys.path.append(project_root)

from fastmcp import FastMCP

mcp = FastMCP(
    name="HealthAgent",
    version="0.1.0",
    instructions=(
        "电力变压器健康管控 MCP 服务。提供 DGA 趋势分析、油色谱/日志/图像故障识别、"
        "D-S 证据融合、剩余寿命估算、IoTDB 时序数据访问等工具。"
        "适用于状态监测、故障诊断、维护决策辅助等场景。"
    ),
)

# Side-effect imports: register tools / resources / prompts onto mcp
from Python.Src.MCP import tools as _tools  # noqa: E402,F401
from Python.Src.MCP import resources as _resources  # noqa: E402,F401
from Python.Src.MCP import prompts as _prompts  # noqa: E402,F401


__all__ = ["mcp"]
