"""MCP resource registrations.

Resources expose read-only data the LLM can subscribe to or fetch by URI.
We surface IoTDB time-series snapshots as resources so the client can pull
device state without explicitly invoking a tool.

URIs:
    iotdb://{equipment_id}/scoring  - all scoring metrics (DGA + oil indicators)
    iotdb://{equipment_id}/dga      - 7 DGA gas trends only
"""
from __future__ import annotations

import json
from typing import Dict

from Python.Src.MCP.server import mcp
from Python.Src.MCP.tools import _iotdb


@mcp.resource("iotdb://{equipment_id}/scoring")
def iotdb_scoring_snapshot(equipment_id: str) -> str:
    """该变压器最近 7 天的全部健康评分指标 (10 个测点) 快照, JSON 格式."""
    bundle = _iotdb().get_all_scoring_data(equipment_id=equipment_id, days=7)
    payload: Dict[str, dict] = {k: v.model_dump() for k, v in bundle.items()}
    return json.dumps(payload, ensure_ascii=False, indent=2)


@mcp.resource("iotdb://{equipment_id}/dga")
def iotdb_dga_snapshot(equipment_id: str) -> str:
    """该变压器最近 7 天的 7 个 DGA 气体趋势快照, JSON 格式."""
    bundle = _iotdb().get_all_dga_trends(equipment_id=equipment_id, days=7)
    payload: Dict[str, dict] = {k: v.model_dump() for k, v in bundle.items()}
    return json.dumps(payload, ensure_ascii=False, indent=2)
