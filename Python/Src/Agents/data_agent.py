"""Data Agent — owns all raw-data acquisition.

Wraps the Phase 1 ``IotDBClient``. Produces the scoring time-series plus
the three defect-identification inputs (inspection-log text /
oil-chromatogram vector / image path) the Diagnosis Agent needs. Runs no
ML inference and makes no LLM calls — pure data plumbing.
"""
from __future__ import annotations

import sys
from pathlib import Path

project_root = str(Path(__file__).resolve().parents[3])
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from Python.Src.Agents.registry import AgentCard
from Python.Src.Agents.state import DiagnosisState, make_message
from Python.Src.Tools.iotdb_tool import IotDBClient

AGENT_NAME = "data"

DATA_CARD = AgentCard(
    name=AGENT_NAME,
    description="从 IoTDB 拉取时序数据并准备三源识别输入",
    skills=["iotdb_query", "sensor_trend", "defect_input_prep"],
    consumes=[],
    produces=["scoring_trends", "log_text", "oil_values", "image_path"],
)

# Demo data preserved from AssessmentService so the multi-agent path and
# the REST path stay consistent.
_DEMO_LOG_TEXTS = {
    "tr01": "变压器近期出现明显温度升高现象。巡检发现套管处由于受热导致周边部件变色，疑似内部过热或起火风险。",
    "tr02": "变压器运行状态良好，但近期巡检发现套管处有轻微渗油痕迹。",
}
_DEMO_LOG_DEFAULT = "设备运行正常，各项指标稳定。"

_OIL_ORDER = ["H2", "CH4", "C2H6", "C2H4", "C2H2", "CO", "CO2"]
_OIL_FALLBACK = [350.0, 40.0, 15.0, 30.0, 5.0, 200.0, 700.0]


def _resolve_demo_image_path(equipment_id: str) -> str:
    """Resolve a demo image path under the sibling ``bysj`` directory."""
    base_bysj = Path(project_root).parent / "bysj"
    if equipment_id == "tr02":
        leak = base_bysj / "test_images" / "oil_leak_demo.jpg"
        if leak.exists():
            return str(leak)
    return str(base_bysj / "downloaded-image.jpg")


def data_node(state: DiagnosisState) -> dict:
    """Data Agent graph node: acquire trends + prepare defect inputs."""
    eid = state.equipment_id
    sub = state.substation
    client = IotDBClient(mode="mock")

    scoring = client.get_all_scoring_data(equipment_id=eid, substation=sub)

    try:
        oil_values = [float(scoring[g].values[-1]) for g in _OIL_ORDER]
    except Exception:
        oil_values = list(_OIL_FALLBACK)

    log_text = _DEMO_LOG_TEXTS.get(eid, _DEMO_LOG_DEFAULT)
    image_path = _resolve_demo_image_path(eid)

    msg = make_message(
        sender=AGENT_NAME,
        receiver="diagnosis",
        intent="result",
        summary=f"已拉取 {eid} 的 {len(scoring)} 个测点趋势, 三源识别输入就绪",
    )
    return {
        "scoring_trends": scoring,
        "oil_values": oil_values,
        "log_text": log_text,
        "image_path": image_path,
        "comm_log": [msg],
    }
