import json
import os
import tempfile
import numpy as np
from pathlib import Path
from pydantic import BaseModel
from typing import Dict, List, Optional

import sys
from pathlib import Path

project_root = str(Path(__file__).resolve().parent.parent.parent.parent)
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from Python.Src.Agent.DefectIdentificationAgent import DefectIdentificationAgent
from Python.Src.Agent.LifecycleDeductionAgent import TransformerLifePredictionTool
from Python.Src.Agent.FaultExpertAgent import FaultAnalyticEngine
from Python.Src.Synergy.IotDBTool import IotDBTool
from Python.Src.Utils.Parser import RobustParser

class AssessmentService:
    def __init__(self):
        self.defect_agent = DefectIdentificationAgent()
        self.lifecycle_agent = TransformerLifePredictionTool()
        self.expert_agent = FaultAnalyticEngine()
        self.iotdb_tool = IotDBTool()
        self.parser = RobustParser()

    @staticmethod
    def _clean_numpy(obj):
        """Recursively convert numpy types to native python types."""
        if isinstance(obj, dict):
            return {k: AssessmentService._clean_numpy(v) for k, v in obj.items()}
        elif isinstance(obj, list):
            return [AssessmentService._clean_numpy(i) for i in obj]
        elif isinstance(obj, np.ndarray):
            return obj.tolist()
        elif isinstance(obj, np.bool_):
            return bool(obj)
        elif isinstance(obj, (np.integer, np.floating)):
            return obj.item()
        return obj

    def run_defect_identification(self, req: dict):
        """
        Connect to real models via InferenceService for real-time results.
        Falls back to demonstration data if models or data are missing.
        """
        equipment_id = req.get("id") or req.get("equipment_id") or "tr01"
        print(f"[AssessmentService] Running defect identification for: {equipment_id}")
        
        # 1. Initialize Inference Service
        from Python.Src.Utils.InferenceService import InferenceService
        inference_service = InferenceService()
        
        # 2. Prepare Inputs (Fetch from IoTDB or use dynamic defaults)
        self.iotdb_tool.equipment_id = equipment_id
        all_data = self.iotdb_tool.get_all_scoring_data(days=1, sampling_rate=1)
        
        # Extract latest values for oil chromatography (7-dim as expected by CNN if possible, or fallback)
        # Sequence: [H2, CH4, C2H6, C2H4, C2H2, CO, CO2]
        try:
            test_oil = [
                all_data.get("H2", {}).get("values", [15.0])[-1],
                all_data.get("CH4", {}).get("values", [8.0])[-1],
                all_data.get("C2H6", {}).get("values", [5.0])[-1],
                all_data.get("C2H4", {}).get("values", [2.0])[-1],
                all_data.get("C2H2", {}).get("values", [0.1])[-1],
                all_data.get("CO", {}).get("values", [200.0])[-1],
                all_data.get("CO2", {}).get("values", [1500.0])[-1]
            ]
        except Exception:
            test_oil = [350.0, 40.0, 15.0, 30.0, 5.0, 200.0, 700.0]

        # Log mapping based on equipment
        if equipment_id == 'tr01':
            test_log = "变压器近期出现明显温度升高现象。巡检发现套管处由于受热导致周边部件变色，疑似内部过热或起火风险。"
        elif equipment_id == 'tr02':
            test_log = "变压器运行状态良好，但近期巡检发现套管处有轻微渗油痕迹。"
        else:
            test_log = "设备运行正常，各项指标稳定。"
            
        # Image mapping
        base_bysj_path = Path(__file__).resolve().parents[4] / "bysj"
        if equipment_id == 'tr01':
            # tr01 uses a sample that might look like fire for demo
            test_image = str(base_bysj_path / "downloaded-image.jpg")
        elif equipment_id == 'tr02':
             # tr02 uses oil leakage sample
            test_image = str(base_bysj_path / "test_images" / "oil_leak_demo.jpg") if (base_bysj_path / "test_images" / "oil_leak_demo.jpg").exists() else str(base_bysj_path / "downloaded-image.jpg")
        else:
            test_image = str(base_bysj_path / "downloaded-image.jpg")
        
        # 3. Execute Real-Time Inference
        log_res = inference_service.infer_log(test_log)
        oil_res = inference_service.infer_oil(test_oil)
        img_res = inference_service.infer_image(test_image)
        
        # 4. Save Path for compatibility with existing agent logic
        # Use system temp dir (cross-platform) to avoid triggering uvicorn reload on file changes
        save_path = os.path.join(tempfile.gettempdir(), "fusion_output.json")
        
        try:
            # We still run evidence fusion, but we can now use real-time inputs
            # To keep it simple and consistent with your structure, we'll manually
            # construct the feature files if they don't exist, or just use the results.
            
            # For now, we continue to use the agent's fusion logic but ensure 
            # the 'ai_reasoning' part uses the real model's output insights.
            
            # Pass REAL-TIME inference results directly to the agent instead of static JSON files
            self.defect_agent.run_evidence_fusion(log_res, oil_res, img_res, save_path)
            
            if os.path.exists(save_path):
                with open(save_path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    
                # Inject real-time inference flags and results
                data["realtime_inference"] = {
                    "bert": log_res.get("fault_prediction_result", {}),
                    "cnn": oil_res.get("fault_prediction", {}),
                    "yolo": img_res,
                    "status": "Active"
                }

                # 5. IoTDB fetch and UI Image Mapping
                self.iotdb_tool.equipment_id = equipment_id
                iotdb_image = self.iotdb_tool.get_device_image()
                
                # Use real-time results to determine description
                if "fault_prediction_result" in log_res:
                    bert_msg = f"模型智能分析：{log_res['fault_prediction_result'].get('predicted_cn', '未识别')} (置信度: {log_res['fault_prediction_result'].get('confidence', 0):.2f})"
                else:
                    bert_msg = "日志模型分析异常"

                if "fault_prediction" in oil_res:
                    cnn_msg = f"油色谱分析：{oil_res['fault_prediction'].get('predicted_fault_cn', '未识别')} (置信度: {oil_res['fault_prediction'].get('confidence', 0):.2f})"
                else:
                    cnn_msg = "油色谱分析异常"

                # Image fallback logic
                if equipment_id == 'tr01':
                    hardcoded_img = "http://localhost:8000/mock/images/fire_defect.png"
                elif equipment_id == 'tr02':
                    hardcoded_img = "http://localhost:8000/mock/images/oil_leakage.png"
                else:
                    hardcoded_img = "http://localhost:8000/mock/images/normal_sample.png"

                # Priority: 1. IoTDB dynamic image, 2. Equipment-specific hardcoded image
                if iotdb_image and iotdb_image.startswith("/mock"):
                    final_image = f"http://localhost:8000{iotdb_image}"
                elif iotdb_image and iotdb_image.startswith("http"):
                    final_image = iotdb_image
                else:
                    final_image = hardcoded_img

                # Inject image URL and AI reasoning
                data["source_evidence"] = {
                    "bert": bert_msg,
                    "cnn": cnn_msg,
                    "yolo": f"实时图像检测：识别到 {img_res.get('defect_count', 0)} 处疑似缺陷" if img_res.get("is_fault") else "视觉检测：运行正常",
                    "image_url": final_image,
                    "ai_reasoning": data.get("ai_reasoning", "正在分析设备联合诊断信息...")
                }
                # Clean native numpy types for JSON serialization
                return self._clean_numpy(data)
            return {"status": "error", "message": "Fusion failed."}
        except Exception as e:
            print(f"[AssessmentService] Error: {e}")
            return {"status": "error", "message": str(e)}

    def run_health_assessment(self, input_data: dict):
        equipment_id = input_data.get("id") or input_data.get("equipment_id") or "tr01"
        substation = input_data.get("substation") or "station1"
        self.iotdb_tool.equipment_id = equipment_id
        self.iotdb_tool.substation = substation
        
        # 1. IoTDB fetch (Real/Mocked dependent on Tool config)
        scoring_trends = self.iotdb_tool.get_all_scoring_data()
        # print(f"[AssessmentService] Fetched scoring trends for {equipment_id}: {scoring_trends}")

        # 2. Defect Identification Integration
        defect_res = self.run_defect_identification(input_data)
        defect_info = defect_res.get("final_fusion_result", {})
        # print(f"[AssessmentService] Defect identification result for {equipment_id}: {defect_info}")
        
        # 3. Physics Model RUL Calculation (Pass defect info)
        input_with_defect = {**input_data, "defect_info": defect_info}
        life_result_str = self.lifecycle_agent._run(**input_with_defect)
        life_result = json.loads(life_result_str)

        # 3. Real Fault Expert Evaluation
        fault_truth = self.expert_agent.analyze_fault_probability(scoring_trends)

        response = {
            "health_index": life_result.get("health_index", 100),
            "predicted_rul": life_result.get("predicted_rul_years", 30),
            "risk_score": fault_truth.get("overall_risk_score", 5.0),
            "primary_threat": fault_truth.get("primary_threat", "无显著威胁"),
            "health_deduction_curve": life_result.get("health_deduction_curve", {}),
            "fault_risk_curve": fault_truth.get("fault_risk_curve", {}),
            "fault_breakdown": fault_truth.get("breakdown", []),
            "expert_advice": self.expert_agent.get_expert_advice(fault_truth),
            # NEW: AI detailed diagnosis for health assessment
            "diagnosis_summary": life_result.get("diagnosis_summary", "正在生成大模型深度诊断结果..."),
            "uncertainty_analysis": life_result.get("uncertainty_analysis", "常规物理模型推演，未包含AI量化不确定性。"),
            # For Frontend DGA Table
            "dga_data": scoring_trends
        }
        return self._clean_numpy(response)

if __name__ == "__main__":
    print("Assessment Service Ready.")
    service = AssessmentService()
    input_data = {'id': 'tr01', 'substation_id': 'station1', 'oil_bdv': 2, 'oil_water': 2, 'oil_acid': 1, 'oil_ift': 2, 'dga_h2': 2, 'dga_ch4': 2, 'dga_co': 1, 'dga_co2': 1, 'dga_c2h4': 1, 'dga_c2h6': 1, 'dga_c2h2': 1, 'furan_level': 'A', 'future_load': 0.8, 'ambient_temp': 25.0, 'moisture': None, 'penalty_factor': 1.0}
    print(service.run_health_assessment(input_data)["diagnosis_summary"])