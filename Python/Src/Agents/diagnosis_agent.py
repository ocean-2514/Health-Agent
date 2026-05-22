"""Diagnosis Agent — single-source recognition + evidence fusion + DGA.

Five graph nodes make up this logical agent:

  bert_node / cnn_node / yolo_node
      Independent single-source classifiers — run in PARALLEL (LangGraph
      fan-out from the Coordinator). They write disjoint result fields and
      each appends to ``comm_log``, which carries an ``operator.add``
      reducer precisely so concurrent appends are concatenated.

  fusion_node
      Fan-in: D-S Murphy evidence fusion over whichever sources are present.

  dga_node
      DGA gas-trend risk analysis (iTransformer / CATCH-style residuals).

All communication is via ``DiagnosisState`` fields — no node calls another.
"""
from __future__ import annotations

import sys
from pathlib import Path

project_root = str(Path(__file__).resolve().parents[3])
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from Python.Src.Agents.registry import AgentCard
from Python.Src.Agents.state import DiagnosisState, make_message
from Python.Src.Tools.dga_tool import analyze_dga_trends
from Python.Src.Tools.fusion_tool import fuse_evidence
from Python.Src.Tools.inference_tool import (
    infer_image,
    infer_log_text,
    infer_oil_chromatogram,
)

AGENT_NAME = "diagnosis"

DIAGNOSIS_CARD = AgentCard(
    name=AGENT_NAME,
    description="BERT/CNN/YOLO 三源识别 → D-S Murphy 证据融合 → DGA 趋势分析",
    skills=["bert_log_cls", "cnn_oil_cls", "yolo_defect_det", "ds_fusion", "dga_trend"],
    consumes=["log_text", "oil_values", "image_path", "scoring_trends"],
    produces=["fusion_result", "dga_analysis"],
)


# --------------------------------------------------------------- parallel leg

def bert_node(state: DiagnosisState) -> dict:
    """BERT classification of the inspection-log text."""
    result = infer_log_text(state.log_text or "")
    pred = result.fault_prediction_result
    msg = make_message(
        sender="diagnosis.bert", receiver="diagnosis.fusion", intent="result",
        summary=f"BERT 日志分类: {pred.predicted_cn}", confidence=pred.confidence,
    )
    return {"bert_result": result, "comm_log": [msg]}


def cnn_node(state: DiagnosisState) -> dict:
    """CNN classification of the 7-dim oil-chromatogram reading."""
    result = infer_oil_chromatogram(state.oil_values or [])
    pred = result.fault_prediction
    msg = make_message(
        sender="diagnosis.cnn", receiver="diagnosis.fusion", intent="result",
        summary=f"CNN 油色谱分类: {pred.predicted_fault_cn}", confidence=pred.confidence,
    )
    return {"cnn_result": result, "comm_log": [msg]}


def yolo_node(state: DiagnosisState) -> dict:
    """YOLO defect detection on the device image."""
    result = infer_image(state.image_path or "")
    msg = make_message(
        sender="diagnosis.yolo", receiver="diagnosis.fusion", intent="result",
        summary=f"YOLO 图像检测: 识别到 {result.defect_count} 处疑似缺陷",
    )
    return {"yolo_result": result, "comm_log": [msg]}


# ----------------------------------------------------------------- fan-in leg

def fusion_node(state: DiagnosisState) -> dict:
    """D-S Murphy fusion over the three single-source results."""
    fusion = fuse_evidence(
        log_result=state.bert_result,
        oil_result=state.cnn_result,
        image_result=state.yolo_result,
    )
    final = fusion.final_fusion_result
    msg = make_message(
        sender="diagnosis.fusion", receiver="coordinator", intent="result",
        summary=f"三源融合结论: {final.final_result_cn}",
        confidence=final.final_confidence,
    )
    return {"fusion_result": fusion, "comm_log": [msg]}


def dga_node(state: DiagnosisState) -> dict:
    """DGA gas-trend risk analysis over the scoring time-series."""
    analysis = analyze_dga_trends(state.scoring_trends or {})
    msg = make_message(
        sender="diagnosis.dga", receiver="coordinator", intent="result",
        summary=(
            f"DGA 综合风险评分 {analysis.overall_risk_score}, "
            f"主要威胁: {analysis.primary_threat}"
        ),
    )
    return {"dga_analysis": analysis, "comm_log": [msg]}
