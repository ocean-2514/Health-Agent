from typing import Dict, Optional, Union, List, Any
import os
import json
from pathlib import Path

# Adjusting python path to make internal imports work well
import sys
project_root = str(Path(__file__).resolve().parent.parent.parent.parent)
if project_root not in sys.path:
    sys.path.append(project_root)

from Python.Src.Core.EvidenceFusion import transformer_three_source_fusion
from Python.Src.Middleware.GlobalConfig import GlobalConfig
from Python.Src.Utils.LLMService import LLMService

class DefectIdentificationAgent:
    """
    Agent responsible for taking multiple sources of features 
    (log, oil, image) and performing D-S Evidence Theory 
    based fusion to output a concrete defect identification result.
    """
    def __init__(self):
        # Read from Global Config
        self.config = GlobalConfig.config.get("Defects", {})
        self.conf_thresh = self.config.get("ConfidenceThreshold", 0.5)
        self.unknown_thresh = self.config.get("UnknownThreshold", 0.3)
        self.model_weights = self.config.get("ModelWeights", {"bert": 1.0, "cnn": 1.0, "yolo": 1.0})
        self.llm_service = LLMService()

    def run_evidence_fusion(
        self, 
        bert_data: Union[str, Dict], 
        cnn_data: Union[str, Dict], 
        yolo_data: Union[str, Dict], 
        save_path: str
    ) -> Optional[str]:
        """
        Executes the three-source fusion algorithms directly.
        Returns the path to the combined result JSON.
        """
        result_path = transformer_three_source_fusion(
            bert_input=bert_data,
            cnn_input=cnn_data,
            yolo_input=yolo_data,
            save_path=save_path,
            conf_thresh=self.conf_thresh,
            unknown_thresh=self.unknown_thresh
        )

        # Enhance with LLM Reasoning
        if result_path and os.path.exists(result_path):
            try:
                with open(result_path, 'r', encoding='utf-8') as f:
                    result_data = json.load(f)
                
                final_result = result_data.get("final_fusion_result", {}).get("final_result_cn", "未知")
                confidence = result_data.get("final_fusion_result", {}).get("final_confidence", 0)
                
                prompt = f"""
                作为一名电力变压器运维专家，请根据以下多源融合检测结果，提供一段专业的技术分析总结。
                
                检测结论：{final_result}
                综合置信度：{confidence:.2f}
                
                请按照以下结构输出：
                1. 现状评估：简述当前设备状态。
                2. 证据链分析：结合多源融合特征（文本日志、油色谱、视觉识别）解释判定依据。
                3. 建议措施：给出后续运维建议。
                
                字数控制在200字以内，语言专业严谨。
                """
                
                reasoning = self.llm_service.generate_response(prompt)
                result_data["ai_reasoning"] = reasoning
                
                with open(result_path, 'w', encoding='utf-8') as f:
                    json.dump(result_data, f, ensure_ascii=False, indent=2)
                    
            except Exception as e:
                print(f"Error enhancing with LLM reasoning: {e}")

        return result_path

if __name__ == "__main__":
    agent = DefectIdentificationAgent()
    print("Testing DefectIdentificationAgent loaded successfully.")
