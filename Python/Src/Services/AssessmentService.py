"""FastAPI compatibility layer over the Phase 1 tool layer.

Preserves the exact response shape consumed by ``/api/assess/defect`` and
``/api/assess/health`` so the React frontend keeps working unchanged.
Algorithm work now flows through ``Python/Src/Tools/*`` (no CrewAI
BaseTool, no hardcoded LLM responses); LLM enrichment of ``ai_reasoning``
and ``diagnosis_summary`` happens here, gated by ``is_fallback`` so
degraded Ollama responses do not masquerade as expert text.
"""
from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path
from typing import Any

import numpy as np

project_root = str(Path(__file__).resolve().parent.parent.parent.parent)
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from Python.Src.Tools.dga_tool import analyze_dga_trends, render_expert_advice
from Python.Src.Tools.fusion_tool import fuse_evidence
from Python.Src.Tools.inference_tool import (
    infer_image,
    infer_log_text,
    infer_oil_chromatogram,
)
from Python.Src.Tools.iotdb_tool import IotDBClient
from Python.Src.Tools.llm_tool import (
    get_llm,
    is_fallback,
    render_defect_prompt,
    render_rul_prompt,
)
from Python.Src.Tools.rul_tool import (
    DGAScores,
    DefectInfo,
    OilScores,
    RULInput,
    compute_rul,
)


# Equipment-specific demo data (preserved from legacy)
_DEMO_LOG_TEXTS = {
    "tr01": "变压器近期出现明显温度升高现象。巡检发现套管处由于受热导致周边部件变色，疑似内部过热或起火风险。",
    "tr02": "变压器运行状态良好，但近期巡检发现套管处有轻微渗油痕迹。",
}
_DEMO_LOG_DEFAULT = "设备运行正常，各项指标稳定。"

_HARDCODED_IMAGE_URLS = {
    "tr01": "http://localhost:8000/mock/images/fire_defect.png",
    "tr02": "http://localhost:8000/mock/images/oil_leakage.png",
}
_HARDCODED_IMAGE_DEFAULT = "http://localhost:8000/mock/images/normal_sample.png"


class AssessmentService:
    def __init__(self, mode: str = "mock"):
        self.iotdb = IotDBClient(mode=mode)
        self.llm = get_llm()

    # ------------------------------------------------------------- helpers

    @staticmethod
    def _clean_numpy(obj: Any) -> Any:
        if isinstance(obj, dict):
            return {k: AssessmentService._clean_numpy(v) for k, v in obj.items()}
        if isinstance(obj, list):
            return [AssessmentService._clean_numpy(i) for i in obj]
        if isinstance(obj, np.ndarray):
            return obj.tolist()
        if isinstance(obj, np.bool_):
            return bool(obj)
        if isinstance(obj, (np.integer, np.floating)):
            return obj.item()
        return obj

    @staticmethod
    def _resolve_demo_image_path(equipment_id: str) -> str:
        base_bysj = Path(project_root).parent / "bysj"
        if equipment_id == "tr02":
            leak = base_bysj / "test_images" / "oil_leak_demo.jpg"
            if leak.exists():
                return str(leak)
        return str(base_bysj / "downloaded-image.jpg")

    @staticmethod
    def _resolve_image_url(equipment_id: str, iotdb_image: str) -> str:
        if iotdb_image and iotdb_image.startswith("/mock"):
            return f"http://localhost:8000{iotdb_image}"
        if iotdb_image and iotdb_image.startswith("http"):
            return iotdb_image
        return _HARDCODED_IMAGE_URLS.get(equipment_id, _HARDCODED_IMAGE_DEFAULT)

    # ---------------------------------------------------- public endpoints

    def run_defect_identification(self, req: dict) -> dict:
        equipment_id = req.get("id") or req.get("equipment_id") or "tr01"
        substation = req.get("substation") or "station1"
        print(f"[AssessmentService] Running defect identification for: {equipment_id}")

        try:
            scoring = self.iotdb.get_all_scoring_data(
                equipment_id=equipment_id, substation=substation,
                days=1, sampling_rate=1,
            )
            try:
                oil_values = [
                    scoring["H2"].values[-1],
                    scoring["CH4"].values[-1],
                    scoring["C2H6"].values[-1],
                    scoring["C2H4"].values[-1],
                    scoring["C2H2"].values[-1],
                    scoring["CO"].values[-1],
                    scoring["CO2"].values[-1],
                ]
            except Exception:
                oil_values = [350.0, 40.0, 15.0, 30.0, 5.0, 200.0, 700.0]

            log_text = _DEMO_LOG_TEXTS.get(equipment_id, _DEMO_LOG_DEFAULT)
            image_path = self._resolve_demo_image_path(equipment_id)

            log_res = infer_log_text(log_text)
            oil_res = infer_oil_chromatogram(oil_values)
            img_res = infer_image(image_path)

            save_path = os.path.join(tempfile.gettempdir(), "fusion_output.json")
            fusion = fuse_evidence(
                log_result=log_res,
                oil_result=oil_res,
                image_result=img_res,
                save_path=save_path,
            )
            data = dict(fusion.raw)

            # LLM enrichment for ai_reasoning
            prompt = render_defect_prompt(
                fusion.final_fusion_result.final_result_cn,
                fusion.final_fusion_result.final_confidence,
            )
            reasoning = self.llm.generate_response(prompt)
            if is_fallback(reasoning):
                reasoning = "联合诊断分析正在生成中（LLM 服务暂不可用，请稍后再试）。"
            data["ai_reasoning"] = reasoning

            data["realtime_inference"] = {
                "bert": log_res.fault_prediction_result.model_dump(),
                "cnn": oil_res.fault_prediction.model_dump(),
                "yolo": img_res.model_dump(),
                "status": "Active",
            }

            bert_pred = log_res.fault_prediction_result
            oil_pred = oil_res.fault_prediction
            iotdb_image = self.iotdb.get_device_image_url(equipment_id, substation)
            image_url = self._resolve_image_url(equipment_id, iotdb_image)

            data["source_evidence"] = {
                "bert": f"模型智能分析：{bert_pred.predicted_cn} (置信度: {bert_pred.confidence:.2f})",
                "cnn": f"油色谱分析：{oil_pred.predicted_fault_cn} (置信度: {oil_pred.confidence:.2f})",
                "yolo": (
                    f"实时图像检测：识别到 {img_res.defect_count} 处疑似缺陷"
                    if img_res.is_fault
                    else "视觉检测：运行正常"
                ),
                "image_url": image_url,
                "ai_reasoning": data["ai_reasoning"],
            }

            return self._clean_numpy(data)
        except Exception as e:
            print(f"[AssessmentService] Defect identification error: {e}")
            return {"status": "error", "message": str(e)}

    def run_health_assessment(self, input_data: dict) -> dict:
        equipment_id = input_data.get("id") or input_data.get("equipment_id") or "tr01"
        substation = input_data.get("substation") or "station1"

        scoring_trends = self.iotdb.get_all_scoring_data(
            equipment_id=equipment_id, substation=substation,
        )

        defect_res = self.run_defect_identification(input_data)
        defect_dict = defect_res.get("final_fusion_result", {})
        defect_info = None
        if isinstance(defect_dict, dict) and defect_dict.get("final_result_cn"):
            defect_info = DefectInfo(
                final_result_cn=defect_dict["final_result_cn"],
                final_confidence=float(defect_dict.get("final_confidence", 0.0)),
            )

        rul_input = RULInput(
            oil=OilScores(
                bdv=input_data["oil_bdv"], water=input_data["oil_water"],
                acid=input_data["oil_acid"], ift=input_data["oil_ift"],
            ),
            dga=DGAScores(
                H2=input_data["dga_h2"], CH4=input_data["dga_ch4"],
                CO=input_data["dga_co"], CO2=input_data["dga_co2"],
                C2H4=input_data["dga_c2h4"], C2H6=input_data["dga_c2h6"],
                C2H2=input_data["dga_c2h2"],
            ),
            furan_level=input_data["furan_level"],
            future_load=input_data["future_load"],
            ambient_temp=input_data["ambient_temp"],
            moisture=input_data.get("moisture"),
            penalty_factor=input_data.get("penalty_factor"),
            defect_info=defect_info,
        )
        rul = compute_rul(rul_input)
        dga = analyze_dga_trends(scoring_trends)

        rul_prompt = render_rul_prompt(
            health_index=rul.health_index,
            predicted_rul_years=rul.predicted_rul_years,
            physics_input={
                "future_load": rul_input.future_load,
                "ambient_temp": rul_input.ambient_temp,
                "applied_penalty_factor": rul.applied_penalty_factor,
            },
            defect_cn=defect_info.final_result_cn if defect_info else None,
        )
        diagnosis = self.llm.generate_response(rul_prompt)
        if is_fallback(diagnosis):
            diagnosis = (
                f"健康指数 {rul.health_index}, 预测剩余寿命 "
                f"{rul.predicted_rul_years} 年。(LLM 服务暂不可用, 当前为物理模型推演结果。)"
            )

        response = {
            "health_index": rul.health_index,
            "predicted_rul": rul.predicted_rul_years,
            "risk_score": dga.overall_risk_score,
            "primary_threat": dga.primary_threat,
            "health_deduction_curve": rul.health_deduction_curve or {},
            "fault_risk_curve": dga.fault_risk_curve.model_dump(),
            "fault_breakdown": [fp.model_dump() for fp in dga.breakdown],
            "expert_advice": render_expert_advice(dga),
            "diagnosis_summary": diagnosis,
            "uncertainty_analysis": rul.uncertainty_analysis or {},
            "dga_data": {k: v.model_dump() for k, v in scoring_trends.items()},
        }
        return self._clean_numpy(response)


if __name__ == "__main__":
    service = AssessmentService()
    sample = {
        "id": "tr01", "substation_id": "station1",
        "oil_bdv": 2, "oil_water": 2, "oil_acid": 1, "oil_ift": 2,
        "dga_h2": 2, "dga_ch4": 2, "dga_co": 1, "dga_co2": 1,
        "dga_c2h4": 1, "dga_c2h6": 1, "dga_c2h2": 1,
        "furan_level": "A", "future_load": 0.8, "ambient_temp": 25.0,
        "moisture": None, "penalty_factor": 1.0,
    }
    out = service.run_health_assessment(sample)
    print("Top-level keys:", sorted(out.keys()))
    print(f"HI={out['health_index']}  RUL={out['predicted_rul']}  risk={out['risk_score']}")
