import re
import json
import logging

class RobustParser:
    """
    高精度解析器：支持标签提取、数值纠平与类型强制转换。
    旨在摆脱 LLM 对 JSON 格式的依赖，同时通过“真理层”校验确保数值准确性。
    """
    
    @staticmethod
    def extract_tag(text, tag_name, default=""):
        pattern = rf"\[\[{tag_name}\]\](.*?)\[\[/{tag_name}\]\]"
        match = re.search(pattern, text, re.DOTALL | re.IGNORECASE)
        if match:
            return match.group(1).strip()
        return default

    @staticmethod
    def extract_float(text, tag_name, truth_value=None, tolerance=0.01):
        raw_val = RobustParser.extract_tag(text, tag_name)
        try:
            numbers = re.findall(r"[-+]?\d*\.\d+|\d+", raw_val)
            if not numbers:
                return float(truth_value) if truth_value is not None else 0.0
            
            val = float(numbers[0])
            
            if truth_value is not None:
                diff = abs(val - truth_value)
                if diff > abs(truth_value * tolerance):
                    logging.warning(f"检测到数值幻觉: {tag_name} AI输出={val}, 真理值={truth_value}. 已强制回正。")
                    return float(truth_value)
            return val
        except Exception:
            return float(truth_value) if truth_value is not None else 0.0

    @classmethod
    def parse_full_report(cls, raw_text, truth_data=None):
        truth_data = truth_data or {}
        
        result = {
            "health_index": cls.extract_float(raw_text, "HEALTH_INDEX", truth_data.get("health_index")),
            "predicted_rul": cls.extract_float(raw_text, "PREDICTED_RUL", truth_data.get("predicted_rul")),
            "detailed_diagnosis_report": cls.extract_tag(raw_text, "DIAGNOSIS_REPORT"),
            "fault_mechanism_analysis": cls.extract_tag(raw_text, "FAULT_MECHANISM"),
            "maintenance_suggestion": cls.extract_tag(raw_text, "MAINTENANCE_SUGGESTION"),
            "overall_risk_score": cls.extract_float(raw_text, "RISK_SCORE", truth_data.get("risk_score")),
            "fault_threat": cls.extract_tag(raw_text, "FAULT_THREAT", "暂无显著威胁")
        }
        
        curve_json_hi = cls.extract_tag(raw_text, "HI_CURVE")
        try:
            result["health_deduction_curve"] = json.loads(curve_json_hi)
        except:
            result["health_deduction_curve"] = truth_data.get("health_deduction_curve", {})

        curve_json_risk = cls.extract_tag(raw_text, "RISK_CURVE")
        try:
            result["fault_risk_curve"] = json.loads(curve_json_risk)
        except:
            result["fault_risk_curve"] = truth_data.get("fault_risk_curve", {})
            
        return result
