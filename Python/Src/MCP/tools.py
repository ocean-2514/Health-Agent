"""MCP tool registrations.

These are thin wrappers over ``Python.Src.Tools.*`` and ``Python.Src.Services``.
Docstrings are intentionally rich because the MCP client (Claude Desktop /
Claude Code) reads them to decide *when* to call each tool.

All wrappers return Pydantic models or plain JSON-serializable dicts; FastMCP
handles the schema conversion automatically.
"""
from __future__ import annotations

from functools import lru_cache
from typing import Any, Dict, List, Optional

from Python.Src.MCP.server import mcp
from Python.Src.Tools.dga_tool import (
    DGAAnalysisResult,
    analyze_dga_trends,
    render_expert_advice,
)
from Python.Src.Tools.fusion_tool import FusionResult, fuse_evidence
from Python.Src.Tools.inference_tool import (
    ImageInferenceResult,
    LogInferenceResult,
    OilInferenceResult,
    infer_image,
    infer_log_text,
    infer_oil_chromatogram,
)
from Python.Src.Tools.iotdb_tool import IotDBClient, SensorTrend
from Python.Src.Tools.rul_tool import (
    DGAScores,
    DefectInfo,
    OilScores,
    RULInput,
    RULResult,
    compute_rul,
)


# ---------------------------------------------------------------------------
# Singletons (avoid re-instantiating on every call)
# ---------------------------------------------------------------------------

@lru_cache(maxsize=1)
def _iotdb() -> IotDBClient:
    return IotDBClient(mode="mock")


@lru_cache(maxsize=1)
def _assessment_service():
    from Python.Src.Services.AssessmentService import AssessmentService
    return AssessmentService(mode="mock")


# ---------------------------------------------------------------------------
# IoTDB time-series tools
# ---------------------------------------------------------------------------

@mcp.tool()
def get_sensor_trend(
    sensor_name: str,
    equipment_id: str = "tr01",
    substation: str = "station1",
    days: int = 7,
    sampling_rate: int = 1,
) -> SensorTrend:
    """获取单个测点的历史时序趋势。

    支持的测点: H2, CH4, C2H6, C2H4, C2H2, CO, CO2 (DGA 七气体),
    oil_bdv (击穿电压), oil_water (含水量), furan (糠醛).

    用于: 当用户询问某个具体气体或油质指标的变化趋势时。
    """
    return _iotdb().get_historical_trend(
        sensor_name=sensor_name,
        equipment_id=equipment_id,
        substation=substation,
        days=days,
        sampling_rate=sampling_rate,
    )


@mcp.tool()
def get_dga_trends(
    equipment_id: str = "tr01",
    substation: str = "station1",
    days: int = 7,
) -> Dict[str, SensorTrend]:
    """获取该变压器的全部 7 个 DGA 气体的历史趋势 (H2 / CH4 / C2H6 / C2H4 / C2H2 / CO / CO2).

    用于: 准备调用 analyze_dga 前的数据获取, 或用户想看完整 DGA 气体走势时.
    """
    return _iotdb().get_all_dga_trends(
        equipment_id=equipment_id, substation=substation, days=days
    )


@mcp.tool()
def get_scoring_data(
    equipment_id: str = "tr01",
    substation: str = "station1",
    days: int = 7,
    sampling_rate: int = 4,
) -> Dict[str, SensorTrend]:
    """获取健康评估所需的全部测点数据 (7 DGA 气体 + oil_bdv + oil_water + furan).

    用于: 准备调用 compute_remaining_useful_life 或 analyze_dga 前的数据采集.
    """
    return _iotdb().get_all_scoring_data(
        equipment_id=equipment_id,
        substation=substation,
        days=days,
        sampling_rate=sampling_rate,
    )


# ---------------------------------------------------------------------------
# DGA analysis
# ---------------------------------------------------------------------------

@mcp.tool()
def analyze_dga(trends: Dict[str, SensorTrend]) -> DGAAnalysisResult:
    """对 DGA 气体趋势做综合风险分析, 输出风险评分、主要威胁类型、未来 8 年风险曲线.

    输入应为 get_dga_trends 或 get_scoring_data 返回的字典.
    算法基于 iTransformer 残差分析 + CATCH 风格的多通道联动检测.
    """
    return analyze_dga_trends(trends)


@mcp.tool()
def get_dga_expert_advice(analysis: DGAAnalysisResult) -> str:
    """根据 DGA 分析结果给出一句话维护建议 (确定性模板, 不调用 LLM)."""
    return render_expert_advice(analysis)


# ---------------------------------------------------------------------------
# ML inference (BERT / CNN / YOLO)
# ---------------------------------------------------------------------------

@mcp.tool()
def classify_inspection_log(text: str) -> LogInferenceResult:
    """用 BERT 模型对巡检日志文本做故障类型分类.

    输入: 自然语言巡检日志, 例如 "套管处发现严重过热并冒烟".
    输出: 分类结果 + 置信度 + 全类别概率分布.
    若模型权重缺失会自动走关键词降级路径.
    """
    return infer_log_text(text)


@mcp.tool()
def classify_oil_chromatogram(values: List[float]) -> OilInferenceResult:
    """用 CNN 模型对油色谱 7 维读数做故障类型分类.

    输入顺序固定: [H2, CH4, C2H6, C2H4, C2H2, CO, CO2] (单位 ppm).
    输出: 五类故障概率 (overheating / discharge / moisture / solid_aging / normal).
    """
    return infer_oil_chromatogram(values)


@mcp.tool()
def detect_image_defects(image_path: str) -> ImageInferenceResult:
    """用 YOLO 模型对变压器图像做缺陷检测.

    输入: 服务器本地的图像绝对路径.
    输出: 检测到的缺陷列表 (fire / oil_leakage / foreign_body / damage) + 置信度.
    """
    return infer_image(image_path)


# ---------------------------------------------------------------------------
# Evidence fusion
# ---------------------------------------------------------------------------

@mcp.tool()
def fuse_three_sources(
    log_result: Optional[LogInferenceResult] = None,
    oil_result: Optional[OilInferenceResult] = None,
    image_result: Optional[ImageInferenceResult] = None,
    conf_threshold: float = 0.5,
    unknown_threshold: float = 0.3,
) -> FusionResult:
    """对日志/油色谱/图像三个来源的故障判定做 D-S Murphy 证据融合.

    至少需要一个来源, 缺失的源传 null. 输出包括最终融合判定、各类别 mass、
    冲突警告等. 用于: 把多个 classify_* 工具的结果合成成一个最终结论.
    """
    return fuse_evidence(
        log_result=log_result,
        oil_result=oil_result,
        image_result=image_result,
        conf_threshold=conf_threshold,
        unknown_threshold=unknown_threshold,
    )


# ---------------------------------------------------------------------------
# Remaining useful life (physics)
# ---------------------------------------------------------------------------

@mcp.tool()
def compute_remaining_useful_life(
    oil_bdv: int, oil_water: int, oil_acid: int, oil_ift: int,
    dga_h2: int, dga_ch4: int, dga_co: int, dga_co2: int,
    dga_c2h4: int, dga_c2h6: int, dga_c2h2: int,
    furan_level: str,
    future_load: float,
    ambient_temp: float,
    moisture: Optional[float] = None,
    penalty_factor: Optional[float] = None,
    defect_result_cn: Optional[str] = None,
    defect_confidence: Optional[float] = None,
) -> RULResult:
    """基于物理机理计算变压器健康指数 (HI) 与剩余寿命 (RUL, 年).

    评分约定:
      - oil_*: 1-3 (1 最好, 3 最差)
      - dga_*: 1-6 (1 最好, 6 最差)
      - furan_level: A-E (A 最好, E 最差)
      - future_load: 预测负载率 0.0-1.5
      - ambient_temp: 环境温度 °C

    可选 defect_result_cn / defect_confidence 用于把缺陷识别结果叠加到 RUL:
      - "起火" + conf>0.6  → 强制 RUL=0, HI=10
      - "漏油" + conf>0.5  → 加速老化系数 ≤ 0.7
      - "异常" + conf>0.5  → 加速老化系数 ≤ 0.8
    """
    defect_info = None
    if defect_result_cn and defect_confidence is not None:
        defect_info = DefectInfo(
            final_result_cn=defect_result_cn,
            final_confidence=defect_confidence,
        )
    rul_input = RULInput(
        oil=OilScores(bdv=oil_bdv, water=oil_water, acid=oil_acid, ift=oil_ift),
        dga=DGAScores(
            H2=dga_h2, CH4=dga_ch4, CO=dga_co, CO2=dga_co2,
            C2H4=dga_c2h4, C2H6=dga_c2h6, C2H2=dga_c2h2,
        ),
        furan_level=furan_level,
        future_load=future_load,
        ambient_temp=ambient_temp,
        moisture=moisture,
        penalty_factor=penalty_factor,
        defect_info=defect_info,
    )
    return compute_rul(rul_input)


# ---------------------------------------------------------------------------
# High-level pipelines (one-shot convenience)
# ---------------------------------------------------------------------------

@mcp.tool()
def assess_full_health(
    equipment_id: str = "tr01",
    substation: str = "station1",
    oil_bdv: int = 2, oil_water: int = 2, oil_acid: int = 1, oil_ift: int = 2,
    dga_h2: int = 2, dga_ch4: int = 2, dga_co: int = 1, dga_co2: int = 1,
    dga_c2h4: int = 1, dga_c2h6: int = 1, dga_c2h2: int = 1,
    furan_level: str = "A",
    future_load: float = 0.8,
    ambient_temp: float = 25.0,
    moisture: Optional[float] = None,
    penalty_factor: Optional[float] = None,
) -> Dict[str, Any]:
    """一键完整健康评估: 拉取 IoTDB 数据 → 三源融合识别缺陷 → 物理 RUL 计算 →
    DGA 趋势分析 → LLM 生成专家意见. 返回与 /api/assess/health 完全一致的响应.

    用于: 用户只想要一个综合诊断结果, 不关心中间过程.
    若想看分步诊断细节, 改用各个原子工具组合调用.
    """
    payload = {
        "id": equipment_id, "substation_id": substation,
        "oil_bdv": oil_bdv, "oil_water": oil_water,
        "oil_acid": oil_acid, "oil_ift": oil_ift,
        "dga_h2": dga_h2, "dga_ch4": dga_ch4,
        "dga_co": dga_co, "dga_co2": dga_co2,
        "dga_c2h4": dga_c2h4, "dga_c2h6": dga_c2h6, "dga_c2h2": dga_c2h2,
        "furan_level": furan_level,
        "future_load": future_load, "ambient_temp": ambient_temp,
        "moisture": moisture, "penalty_factor": penalty_factor,
    }
    return _assessment_service().run_health_assessment(payload)


@mcp.tool()
def assess_defect_only(
    equipment_id: str = "tr01",
    substation: str = "station1",
) -> Dict[str, Any]:
    """只跑缺陷识别 (拉数据 → 三源推理 → D-S 融合 → LLM 解释), 不算 RUL.

    返回与 /api/assess/defect 完全一致的响应.
    """
    return _assessment_service().run_defect_identification(
        {"id": equipment_id, "substation_id": substation}
    )
