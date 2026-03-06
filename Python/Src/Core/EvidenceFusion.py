import json
import numpy as np
import os
from pathlib import Path
from typing import Dict, List, Optional, Union, Any
from datetime import datetime


# ===================== 改良D-S证据理论核心配置（适配三个模型的类别映射） =====================
# 统一识别框架Θ（整合所有模型的缺陷+正常，唯一判别维度）
# 框架说明：包含日志/油色谱/图片的所有独缺陷类型 + 正常，共9类
UNIFIED_FRAME = [
    "overheating",  # 过热（BERT/CNN）
    "discharge",  # 放电（BERT/CNN）
    "moisture",  # 受潮（BERT/CNN）
    "solid_aging",  # 固体绝缘老化（BERT/CNN，简写便于处理）
    "fire",  # 起火（BERT/YOLO）
    "oil_leakage",  # 漏油（BERT/YOLO）
    "foreign_body",  # 异物（YOLO独有）
    "damage",  # 破损（YOLO独有）
    "normal"  # 设备正常（所有模型）
]
# 类别中文映射（和原代码一致）
CN_MAPPING = {
    "overheating": "过热",
    "discharge": "放电",
    "moisture": "受潮",
    "solid_aging": "固体绝缘老化",
    "fire": "起火",
    "oil_leakage": "漏油",
    "foreign_body": "异物",
    "damage": "破损",
    "normal": "设备正常"
}
# 三个模型 → 统一框架的映射表（解决各模型类别命名/索引不一致问题）
MODEL_TO_UNIFIED = {
    # BERT（日志）：原7类索引→统一框架名称（对应fault_mapping）
    "bert": {
        0: "overheating", 1: "discharge", 2: "moisture",
        3: "solid_aging", 4: "fire", 5: "oil_leakage", 6: "normal"
    },
    # CNN（油色谱）：原5类索引→统一框架名称（对应defect_mapping）
    "cnn": {
        0: "overheating", 1: "discharge", 2: "moisture",
        3: "solid_aging", 4: "normal"
    },
    # YOLO（图片）：原4类索引→统一框架名称（无检测则为normal）
    "yolo": {
        0: "fire", 1: "oil_leakage", 2: "foreign_body", 3: "damage"
    }
}
# 模型权重（可根据业务调整，比如认为图片YOLO更可靠则权重高，默认等权）
MODEL_WEIGHTS = {"bert": 1.0, "cnn": 1.0, "yolo": 1.0}


# ===================== 改良D-S证据理论核心实现（Murphy平均法，解决冲突问题） =====================
class DSEvidenceFusion:
    def __init__(
            self,
            unified_frame: List[str] = UNIFIED_FRAME,
            model_weights: Dict[str, float] = MODEL_WEIGHTS,
            conf_thresh: float = 0.5,  # 融合后置信度阈值，低于则模糊
            unknown_thresh: float = 0.3  # 不确定度阈值，高于则模糊
    ):
        """
        改良D-S证据理论融合器（Murphy平均法），适配变压器三源数据融合
        :param unified_frame: 统一识别框架Θ
        :param model_weights: 各模型权重（等权/加权）
        :param conf_thresh: 融合后最终结果置信度阈值
        :param unknown_thresh: 不确定度mass(Θ)阈值
        """
        self.frame = unified_frame
        self.frame_idx = {cls: i for i, cls in enumerate(self.frame)}  # 框架→索引
        self.n = len(self.frame)
        self.model_weights = model_weights
        self.conf_thresh = conf_thresh
        self.unknown_thresh = unknown_thresh
        self.total_weight = sum(model_weights.values())  # 权重和，用于归一化

    def _normalize_bpa(self, bpa: np.ndarray) -> np.ndarray:
        """归一化BPA，保证所有焦元mass和为1"""
        bpa_sum = np.sum(bpa)
        if bpa_sum == 0:
            return np.zeros_like(bpa)
        return bpa / bpa_sum

    def _dempster_combination(self, bpa1: np.ndarray, bpa2: np.ndarray) -> np.ndarray:
        """
        原始D-S合成规则（两两融合）
        :param bpa1: 证据1的BPA（含普通焦元+不确定焦元，最后一位为mass(Θ)）
        :param bpa2: 证据2的BPA
        :return: 融合后的BPA
        """
        # 初始化融合结果（n个普通焦元 + 1个不确定焦元Θ）
        fused_bpa = np.zeros(self.n + 1)
        # 计算冲突系数K
        K = 0.0
        for i in range(self.n):
            for j in range(self.n):
                if i != j:  # 互斥焦元，冲突
                    K += bpa1[i] * bpa2[j]
        if K == 1:  # 完全冲突，无法融合，返回等概率
            return np.ones(self.n + 1) / (self.n + 1)

        # 合成普通焦元
        for i in range(self.n):
            # 情况1：a∩b=a（b包含a）
            same_cls = bpa1[i] * bpa2[i]
            # 情况2：a∩Θ=a
            with_unknown = bpa1[i] * bpa2[-1] + bpa1[-1] * bpa2[i]
            fused_bpa[i] = (same_cls + with_unknown) / (1 - K)

        # 合成不确定焦元Θ：Θ∩Θ=Θ
        fused_bpa[-1] = (bpa1[-1] * bpa2[-1]) / (1 - K)
        return self._normalize_bpa(fused_bpa)

    def murphy_fusion(self, bpa_list: List[np.ndarray], model_names: List[str]) -> np.ndarray:
        """
        Murphy改良融合法（核心：解决原始D-S冲突问题）
        步骤：1. 动态自适应加权平均 2. 用原始D-S规则融合n-1次
        :param bpa_list: 各模型的BPA列表
        :param model_names: 对应模型名称
        :return: 最终融合后的BPA
        """
        if len(bpa_list) == 0:
            raise ValueError("无有效BPA证据，无法融合")
        if len(bpa_list) == 1:
            return bpa_list[0]

        # 1. 动态自适应计算各模型权重
        # 逻辑：权重 = 基础权重 * exp(10 * 最大置信度) -> 指数级放大高置信度模型的影响力
        # 这种方式能让 0.9 置信度的模型权重比 0.5 置信度的模型高出约 50 多倍，比 0.2 模型多出约 1000 倍
        dynamic_weights = []
        for bpa, model in zip(bpa_list, model_names):
            base_w = self.model_weights.get(model, 1.0)
            max_conf = np.max(bpa[:-1])
            dynamic_w = base_w * np.exp(10 * max_conf)
            dynamic_weights.append(dynamic_w)
        
        total_dyn_weight = sum(dynamic_weights)
        if total_dyn_weight == 0:
            # 如果所有模型置信度极低，回退到等权
            dynamic_weights = [1.0] * len(bpa_list)
            total_dyn_weight = sum(dynamic_weights)

        # 2. 按动态权重加权平均所有BPA
        avg_bpa = np.zeros_like(bpa_list[0])
        for bpa, weight in zip(bpa_list, dynamic_weights):
            avg_bpa += bpa * (weight / total_dyn_weight)
        avg_bpa = self._normalize_bpa(avg_bpa)

        # 3. 用原始D-S规则融合n-1次（Murphy法核心）
        fused_bpa = avg_bpa
        for _ in range(len(bpa_list) - 1):
            fused_bpa = self._dempster_combination(fused_bpa, avg_bpa)

        return self._normalize_bpa(fused_bpa)

    def generate_bpa(self, model_type: str, model_conf: Dict[str, float], is_fuzzy: bool = False) -> np.ndarray:
        """
        将单个模型的置信度转换为BPA（基本概率赋值）
        :param model_type: 模型类型（bert/cnn/yolo）
        :param model_conf: 模型对统一框架的置信度字典 {cls: conf}
        :param is_fuzzy: 模型是否为模糊/疑似样本（是则增加不确定度）
        :return: BPA数组 [mass(c1), mass(c2), ..., mass(cn), mass(Θ)]
        """
        # 前n位：各缺陷/正常，最后1位：不确定度mass(Θ)
        bpa = np.zeros(self.n + 1)  
        
        # 1. 累积分放射量
        # 重要：这里直接使用模型给出的置信度作为 mass 基础，不再立即归一化
        total_assigned_mass = 0.0
        for cls, conf in model_conf.items():
            if cls in self.frame_idx:
                mass_val = conf * self.model_weights.get(model_type, 1.0)
                bpa[self.frame_idx[cls]] = mass_val
                total_assigned_mass += mass_val

        # 2. 如果分配的总质量超过1.0（由于权重或原始数据），则进行强制归约
        if total_assigned_mass > 1.0:
            bpa[:-1] /= total_assigned_mass
            total_assigned_mass = 1.0

        # 3. 处理模糊样本：置信度衰减，剩余部分全部归入不确定度
        if is_fuzzy:
            fuzzy_reduce = 0.5  # 模糊衰减系数
            bpa[:-1] *= fuzzy_reduce
            total_assigned_mass *= fuzzy_reduce

        # 4. [核心修复]：未被分配的置信度剩余部分，全部归入不确定度 mass(Θ)
        # 这保证了 100% 置信度的模型产生 Θ=0 的强证据，而 60% 置信度产生 Θ=0.4 的弱证据
        bpa[-1] = max(0.0, 1.0 - total_assigned_mass)

        # 5. 最终校验：若所有 mass (含Θ) 为0，分配等概率（防极端除0）
        if np.sum(bpa) == 0:
            bpa[:] = 1.0 / (self.n + 1)
            
        return bpa

    def fusion_decision(self, fused_bpa: np.ndarray) -> Dict:
        """
        融合后决策：根据BPA和阈值判定最终结果，包含模糊/无法判定逻辑
        :param fused_bpa: 融合后的BPA数组
        :return: 结构化决策结果
        """
        # 提取各焦元的mass值
        cls_mass = fused_bpa[:-1]
        unknown_mass = fused_bpa[-1]  # mass(Θ) 不确定度
        # 找到最大mass的类别索引和值
        max_mass_idx = np.argmax(cls_mass)
        max_mass_cls = self.frame[max_mass_idx]
        max_mass_val = cls_mass[max_mass_idx]

        # 计算总故障 mass (排除 normal)
        normal_idx = self.frame_idx.get("normal")
        fault_masses = [cls_mass[i] for i in range(self.n) if i != normal_idx]
        total_fault_mass = sum(fault_masses)
        normal_mass = cls_mass[normal_idx] if normal_idx is not None else 0.0

        # [第四阶段重构] 故障严选与多风险预警逻辑
        # 核心哲学：正常项作为兜底，任何实质性的故障倾向必须优先报举
        
        is_definite = True
        decision_note = "判别结果明确"
        
        # 1. 识别所有显著故障项 (置信度 > 0.1 或 总量级显著)
        fault_indices = [i for i in range(self.n) if i != normal_idx]
        significant_faults = [(self.frame[i], float(cls_mass[i])) for i in fault_indices if cls_mass[i] > 0.001]
        significant_faults.sort(key=lambda x: x[1], reverse=True)
        
        current_max_cls = max_mass_cls
        current_max_val = float(max_mass_val)

        # 3. 故障绝对优先判别逻辑 (极度悲观视角，保障绝对安全)
        # 逻辑：只要有显著故障项（置信度 > 0.1），不论总体的 normal 有多高，绝对覆盖正常判断
        if total_fault_mass > 0.05 and len(significant_faults) > 0:
            if current_max_cls == "normal":
                current_max_cls, current_max_val = significant_faults[0]
                decision_note = f"【故障高度警惕】正常项仍被单项显著故障强制覆盖，最高故障质量({total_fault_mass:.4f})，严防漏报。"
                is_definite = False # 这种覆盖的情况多数是因为本身有冲突
            else:
                 decision_note = f"判别结果明确，故障累计概率较大。"
        elif current_max_cls == "normal":
            # 只有在此区间（几乎没有任何实质故障 mass）才允许判定正常
            if total_fault_mass > 0.01 or current_max_val < 0.8:
                is_definite = False
                decision_note = f"【疑似异常】正常项置信度不足或存在微量扰动，无法完全排除故障风险"
            else:
                decision_note = f"设备运行平稳，无显著异常特征"
        
        # 5. 多重风险预警逻辑：收集所有置信度 > 0.15 的故障
        warnings = [f for f, v in significant_faults if v > 0.15]
        if len(warnings) > 1:
            # 如果存在多个显著风险，在说明中特别报出
            decision_note += f" [多重风险预警: {', '.join([CN_MAPPING.get(w, w) for w in warnings])}]"

        # 6. 置信度阈值检查 (保留真实值，仅加注)
        if current_max_val < self.conf_thresh:
            is_definite = False
            decision_note += f" (置信度 {current_max_val:.4f} 低于阈值 {self.conf_thresh})"
            
        if float(unknown_mass) > self.unknown_thresh:
            is_definite = False
            decision_note += f" [证据冲突/不确定度高:{unknown_mass:.4f}]"

        final_cls = current_max_cls
        final_conf = round(current_max_val, 4)
        
        # 构建各类别置信度字典 (中文)
        all_mass_cn = {}
        for i, cls in enumerate(self.frame):
            all_mass_cn[CN_MAPPING.get(cls, cls)] = round(float(cls_mass[i]), 4)
        
        # 降序排列的中文结果
        sorted_mass_cn = dict(sorted(all_mass_cn.items(), key=lambda x: x[1], reverse=True))

        return {
            "final_result_en": final_cls,
            "final_result_cn": CN_MAPPING.get(final_cls, final_cls),
            "final_confidence": final_conf,
            "is_definite": is_definite,
            "is_normal": final_cls == "normal",
            "is_fault": final_cls != "normal",
            "unknown_mass": round(float(unknown_mass), 4),
            "decision_note": decision_note,
            "warnings": [CN_MAPPING.get(w, w) for w in warnings],
            "all_mass_en": {cls: round(float(cls_mass[i]), 4) for i, cls in enumerate(self.frame)},
            "all_mass_cn": all_mass_cn,
            "sorted_mass_cn": sorted_mass_cn,
            "fusion_config": {
                "confidence_threshold": self.conf_thresh,
                "unknown_threshold": self.unknown_thresh
            }
        }


# ===================== 三源JSON文件解析与置信度映射 =====================
class TransformerDataParser:
    def __init__(self, bert_input: Union[str, Dict, None], cnn_input: Union[str, Dict, None], yolo_input: Union[str, Dict, None]):
        """
        变压器三源数据解析器，解析各模型置信度并映射到统一框架
        支持文件路径 (str) 或 直接的数据字典 (Dict)
        :param bert_input: BERT日志数据或路径
        :param cnn_input: CNN油色谱数据或路径
        :param yolo_input: YOLO图片数据或路径
        """
        self.bert_data = self._load_data(bert_input, "bert")
        self.cnn_data = self._load_data(cnn_input, "cnn")
        self.yolo_data = self._load_data(yolo_input, "yolo")

    def _load_data(self, input_val: Union[str, Dict, None], model_type: str) -> Optional[Dict]:
        """加载并校验数据，支持Dict或Path"""
        if input_val is None:
            return None
        if isinstance(input_val, dict):
            return input_val
        
        json_path = Path(input_val)
        if not json_path.exists():
            print(f"【{model_type}】JSON文件不存在：{json_path.absolute()}")
            return None
        try:
            with open(json_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            print(f"【{model_type}】JSON文件解析成功：{json_path.absolute()}")
            return data
        except Exception as e:
            print(f"【{model_type}】JSON解析失败：{str(e)}")
            return None

    def _parse_bert_conf(self) -> (Dict[str, float], bool):
        """解析BERT日志JSON的置信度，映射到统一框架，返回{cls: conf} + 是否模糊"""
        if not self.bert_data:
            return {cls: 0.0 for cls in UNIFIED_FRAME}, True
        # 提取BERT原始置信度（英文键）
        bert_conf = self.bert_data["fault_prediction_result"]["all_probs_en"]
        is_fuzzy = self.bert_data["fault_prediction_result"]["is_fuzzy"]
        # 映射到统一框架
        unified_conf = {cls: 0.0 for cls in UNIFIED_FRAME}
        for bert_idx, frame_cls in MODEL_TO_UNIFIED["bert"].items():
            # 从BERT的all_probs_en中取对应置信度
            for en_cls, conf in bert_conf.items():
                if en_cls == MODEL_TO_UNIFIED["bert"][bert_idx]:
                    unified_conf[frame_cls] = conf
        return unified_conf, is_fuzzy

    def _parse_cnn_conf(self) -> (Dict[str, float], bool):
        """解析CNN油色谱JSON的置信度，映射到统一框架，返回{cls: conf} + 是否模糊"""
        if not self.cnn_data:
            return {cls: 0.0 for cls in UNIFIED_FRAME}, True
        # 提取CNN原始置信度（英文键）
        # Handle both 'all_class_probabilities' (from JSON) and 'all_probs' (from InferenceService)
        cnn_conf = self.cnn_data["fault_prediction"].get("all_class_probabilities") or self.cnn_data["fault_prediction"].get("all_probs")
        is_fuzzy = self.cnn_data["fault_prediction"].get("is_suspected") or self.cnn_data["fault_prediction"].get("is_fuzzy", False)
        # 映射到统一框架
        unified_conf = {cls: 0.0 for cls in UNIFIED_FRAME}
        for cnn_idx, frame_cls in MODEL_TO_UNIFIED["cnn"].items():
            unified_conf[frame_cls] = cnn_conf.get(frame_cls, 0.0)
        return unified_conf, is_fuzzy

    def _parse_yolo_conf(self) -> (Dict[str, float], bool):
        """解析YOLO图片JSON的置信度，映射到统一框架，返回{cls: conf} + 是否模糊"""
        if not self.yolo_data:
            return {cls: 0.0 for cls in UNIFIED_FRAME}, True
        # YOLO逻辑：有缺陷取最高置信度，无缺陷则normal=1.0
        is_fuzzy = False
        unified_conf = {cls: 0.0 for cls in UNIFIED_FRAME}
        
        # Determine status: from InferenceService (is_fault) or from JSON (image_status)
        is_fault = self.yolo_data.get("is_fault")
        if is_fault is None:
            is_fault = self.yolo_data.get("image_status") != "normal"
            
        if not is_fault:
            unified_conf["normal"] = 1.0
        else:
            # 提取所有缺陷的置信度，取最高的作为该类置信度
            defects = self.yolo_data.get("defects", [])
            if not defects:
                # 标记有故障但没明细，返回模糊
                unified_conf["normal"] = 0.2
                is_fuzzy = True
            else:
                defect_confs = {}
                for defect in defects:
                    cls_name = defect.get("class_name")
                    conf = defect.get("confidence", 0.0)
                    if cls_name and (cls_name not in defect_confs or conf > defect_confs[cls_name]):
                        defect_confs[cls_name] = conf
                # 映射到统一框架
                # 如果有故障，normal 分配一个极低的基础分（例如 0.05），避免完全清零导致的冲突放大
                unified_conf["normal"] = 0.05
                remaining_mass = 0.95
                conf_sum = sum(defect_confs.values())
                for cls_name, conf in defect_confs.items():
                    if cls_name in unified_conf:
                        unified_conf[cls_name] = (conf / conf_sum * remaining_mass) if conf_sum > 0 else 0.0
        # YOLO无模糊逻辑，若无检测结果则为模糊
        if self.yolo_data.get("defect_count", 0) == 0 and not (self.yolo_data.get("image_status") == "normal" or not self.yolo_data.get("is_fault", True)):
            is_fuzzy = True
        return unified_conf, is_fuzzy

    def parse_all(self) -> Dict[str, Dict]:
        """解析所有模型的置信度，返回结构化结果"""
        bert_conf, bert_fuzzy = self._parse_bert_conf()
        cnn_conf, cnn_fuzzy = self._parse_cnn_conf()
        yolo_conf, yolo_fuzzy = self._parse_yolo_conf()
        return {
            "bert": {"conf": bert_conf, "is_fuzzy": bert_fuzzy, "valid": self.bert_data is not None},
            "cnn": {"conf": cnn_conf, "is_fuzzy": cnn_fuzzy, "valid": self.cnn_data is not None},
            "yolo": {"conf": yolo_conf, "is_fuzzy": yolo_fuzzy, "valid": self.yolo_data is not None}
        }


# ===================== 主融合流程：解析JSON → 生成BPA → D-S融合 → 决策 → 保存结果 =====================
def transformer_three_source_fusion(
        bert_input: Union[str, Dict, None],
        cnn_input: Union[str, Dict, None],
        yolo_input: Union[str, Dict, None],
        save_path: str,
        conf_thresh: float = 0.5,
        unknown_thresh: float = 0.3
) -> Optional[str]:
    """
    变压器三源数据（日志/油色谱/图片）D-S证据理论联合判别主函数
    :param bert_input: BERT生成的JSON文件路径或数据内容
    :param cnn_input: CNN生成的JSON文件路径或数据内容
    :param yolo_input: YOLO生成的JSON文件路径或数据内容
    :param save_path: 融合结果保存路径
    :param conf_thresh: 融合置信度阈值
    :param unknown_thresh: 不确定度阈值
    :return: 保存路径（失败返回None）
    """
    print("===== 开始变压器三源数据D-S证据理论联合判别 =====")
    # 1. 解析三源数据
    parser = TransformerDataParser(bert_input, cnn_input, yolo_input)
    model_data = parser.parse_all()
    # 过滤无效模型（JSON解析失败的模型）
    valid_models = [m for m in model_data if model_data[m]["valid"]]
    if not valid_models:
        print("所有模型JSON文件均无效，无法融合")
        return None
    print(f"有效证据源：{valid_models}（共{len(valid_models)}个）")

    # 2. 初始化D-S融合器
    dse = DSEvidenceFusion(
        unified_frame=UNIFIED_FRAME,
        model_weights=MODEL_WEIGHTS,
        conf_thresh=conf_thresh,
        unknown_thresh=unknown_thresh
    )

    # 3. 为每个有效模型生成BPA
    bpa_list = []
    model_names = []
    for model in valid_models:
        conf = model_data[model]["conf"]
        is_fuzzy = model_data[model]["is_fuzzy"]
        bpa = dse.generate_bpa(model, conf, is_fuzzy)
        bpa_list.append(bpa)
        model_names.append(model)
        print(f"【{model}】BPA生成完成：{dict(zip(UNIFIED_FRAME + ['未知(Θ)'], [round(float(x), 4) for x in bpa]))}")

    # 4. 改良D-S融合（Murphy法）
    fused_bpa = dse.murphy_fusion(bpa_list, model_names)
    print(f"融合后总BPA：{dict(zip(UNIFIED_FRAME + ['未知(Θ)'], [round(float(x), 4) for x in fused_bpa]))}")

    # 5. 融合后决策
    fusion_result = dse.fusion_decision(fused_bpa)

    # 6. 构造结构化融合结果（和原JSON格式统一）
    structured_result = {
        "fusion_basic_info": {
            "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "evidence_sources": valid_models,
            "model_weights": MODEL_WEIGHTS,
            "unified_frame": UNIFIED_FRAME,
            "file_paths": {
                "bert": bert_input if isinstance(bert_input, str) else "direct_input",
                "cnn": cnn_input if isinstance(cnn_input, str) else "direct_input",
                "yolo": yolo_input if isinstance(yolo_input, str) else "direct_input"
            }
        },
        "original_model_data": {  # 保留各模型原始结果，便于溯源
            model: {
                "confidence_unified": {k: float(v) for k, v in model_data[model]["conf"].items()},
                "is_fuzzy": bool(model_data[model]["is_fuzzy"]),
                "valid": bool(model_data[model]["valid"])
            } for model in model_data
        },
        "bpa_info": {  # BPA信息，便于分析证据质量
            "each_model_bpa": {
                model: dict(zip(UNIFIED_FRAME + ['未知(Θ)'], [round(float(x), 4) for x in bpa]))
                for model, bpa in zip(model_names, bpa_list)
            },
            "fused_bpa": dict(zip(UNIFIED_FRAME + ['未知(Θ)'], [round(float(x), 4) for x in fused_bpa])),
            "unknown_mass": float(fusion_result["unknown_mass"])
        },
        "final_fusion_result": fusion_result,  # 最终融合决策结果
        "cn_mapping": CN_MAPPING,  # 中文映射
        "version": "v1.0_DS_Murphy_Transformer"
    }

    # 7. 保存融合结果到JSON文件
    try:
        # 创建保存目录
        save_dir = Path(os.path.dirname(save_path))
        if save_dir and not save_dir.exists():
            save_dir.mkdir(parents=True, exist_ok=True)
        # 保存JSON（中文正常显示）
        with open(save_path, "w", encoding="utf-8") as f:
            json.dump(structured_result, f, ensure_ascii=False, indent=2)
        print(f"三源数据融合完成，结果保存至：{save_path}")
        # 打印核心融合结果（友好展示）
        print("\n" + "=" * 60)
        print("===== 变压器三源数据联合判别核心结果 =====")
        print("=" * 60)
        print(f"最终判定结果：{structured_result['final_fusion_result']['final_result_cn']}")
        print(f"最终置信度：{structured_result['final_fusion_result']['final_confidence']:.4f}")
        print(f"是否明确判定：{structured_result['final_fusion_result']['is_definite']}")
        print(f"是否设备正常：{structured_result['final_fusion_result']['is_normal']}")
        print(f"是否存在缺陷：{structured_result['final_fusion_result']['is_fault']}")
        print(f"证据不确定度：{structured_result['final_fusion_result']['unknown_mass']:.4f}")
        print(f"判定说明：{structured_result['final_fusion_result']['decision_note']}")
        print("=" * 60)
        return save_path
    except Exception as e:
        print(f"保存融合结果失败：{str(e)}")
        return None


# ===================== 主函数（直接运行，修改路径即可） =====================
if __name__ == "__main__":
    # -------------------------- 配置你的三个JSON文件路径和保存路径 --------------------------
    BERT_JSON = r"D:\bysj\data\features\transformer_log_features.json"  # BERT日志JSON
    CNN_JSON = r"D:\bysj\data\features\transformer_oil_features.json"  # CNN油色谱JSON
    YOLO_JSON = r"D:\bysj\data\features\transformer_image_features.json"  # YOLO图片JSON
    FUSION_SAVE_PATH = r"D:\bysj\data\features\transformer_three_source_fusion.json"  # 融合结果保存路径
    # ------------------------------------------------------------------------------------------

    # 执行三源数据融合
    transformer_three_source_fusion(
        bert_json_path=BERT_JSON,
        cnn_json_path=CNN_JSON,
        yolo_json_path=YOLO_JSON,
        save_path=FUSION_SAVE_PATH,
        conf_thresh=0.5,  # 可根据业务调整
        unknown_thresh=0.3
    )
