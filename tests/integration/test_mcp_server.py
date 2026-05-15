"""Integration tests for the MCP server.

These tests do not require a running stdio transport — they invoke the
FastMCP API surface directly (the same code path the stdio bridge uses).
That confirms tools/resources/prompts are correctly registered AND that
calls round-trip through Pydantic validation.
"""
from __future__ import annotations

import json

import pytest


@pytest.fixture(scope="module")
def mcp():
    from Python.Src.MCP.server import mcp as instance
    return instance


# ---------- Registration ----------

@pytest.mark.asyncio
async def test_expected_tools_registered(mcp):
    tools = await mcp.list_tools()
    names = {t.name for t in tools}
    expected = {
        "get_sensor_trend", "get_dga_trends", "get_scoring_data",
        "analyze_dga", "get_dga_expert_advice",
        "classify_inspection_log", "classify_oil_chromatogram", "detect_image_defects",
        "fuse_three_sources",
        "compute_remaining_useful_life",
        "assess_full_health", "assess_defect_only",
    }
    missing = expected - names
    assert not missing, f"missing tools: {missing}"


@pytest.mark.asyncio
async def test_expected_resource_templates_registered(mcp):
    rt = await mcp.list_resource_templates()
    uris = {r.uri_template for r in rt}
    assert "iotdb://{equipment_id}/scoring" in uris
    assert "iotdb://{equipment_id}/dga" in uris


@pytest.mark.asyncio
async def test_expected_prompts_registered(mcp):
    prompts = await mcp.list_prompts()
    names = {p.name for p in prompts}
    assert {"diagnose_transformer", "quick_health_screen", "explain_dga_anomaly"} <= names


# ---------- Tool call round-trips ----------

@pytest.mark.asyncio
async def test_get_sensor_trend_returns_structured(mcp):
    result = await mcp.call_tool(
        "get_sensor_trend",
        {"sensor_name": "H2", "equipment_id": "tr01", "days": 1, "sampling_rate": 4},
    )
    assert result.structured_content["sensor"] == "H2"
    assert len(result.structured_content["timestamps"]) == len(result.structured_content["values"])


@pytest.mark.asyncio
async def test_compute_rul_via_mcp(mcp):
    result = await mcp.call_tool(
        "compute_remaining_useful_life",
        {
            "oil_bdv": 2, "oil_water": 2, "oil_acid": 1, "oil_ift": 2,
            "dga_h2": 2, "dga_ch4": 2, "dga_co": 1, "dga_co2": 1,
            "dga_c2h4": 1, "dga_c2h6": 1, "dga_c2h2": 1,
            "furan_level": "A",
            "future_load": 0.8, "ambient_temp": 25.0,
        },
    )
    sc = result.structured_content
    assert 0.0 <= sc["health_index"] <= 100.0
    assert sc["predicted_rul_years"] > 0


@pytest.mark.asyncio
async def test_compute_rul_with_fire_defect_forces_zero(mcp):
    result = await mcp.call_tool(
        "compute_remaining_useful_life",
        {
            "oil_bdv": 2, "oil_water": 2, "oil_acid": 1, "oil_ift": 2,
            "dga_h2": 2, "dga_ch4": 2, "dga_co": 1, "dga_co2": 1,
            "dga_c2h4": 1, "dga_c2h6": 1, "dga_c2h2": 1,
            "furan_level": "A",
            "future_load": 0.8, "ambient_temp": 25.0,
            "defect_result_cn": "起火", "defect_confidence": 0.85,
        },
    )
    assert result.structured_content["predicted_rul_years"] == 0.0


# ---------- Resource read ----------

@pytest.mark.asyncio
async def test_iotdb_dga_resource_returns_json(mcp):
    result = await mcp.read_resource("iotdb://tr01/dga")
    text = result.contents[0].content
    payload = json.loads(text)
    assert "H2" in payload
    assert "values" in payload["H2"]


# ---------- Prompt rendering ----------

@pytest.mark.asyncio
async def test_diagnose_prompt_rendered(mcp):
    rendered = await mcp.render_prompt("diagnose_transformer", {"equipment_id": "tr05"})
    assert "tr05" in rendered.messages[0].content.text
    assert "get_dga_trends" in rendered.messages[0].content.text
