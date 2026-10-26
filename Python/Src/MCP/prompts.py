"""MCP prompt registrations — guided diagnostic workflows.

Prompts are reusable conversation templates the MCP client can invoke
("give me the diagnosis prompt for tr01") to bootstrap a structured
analysis conversation. They tell the LLM *which tools to call in what
order* — this is how we encode domain workflows without writing a
dedicated agent layer (that comes in Phase 3).
"""
from __future__ import annotations

from Python.Src.MCP.server import mcp


@mcp.prompt()
def diagnose_transformer(equipment_id: str = "tr01") -> str:
    """完整的变压器故障诊断决策树, 引导 LLM 按顺序调用所有工具."""
    return f"""请对变压器 **{equipment_id}** 完成完整故障诊断, 严格按以下步骤:

1. 调用 `get_dga_trends({equipment_id})` 获取 7 个 DGA 气体最近 7 天趋势.
2. 调用 `analyze_dga(trends)` 计算综合风险评分与主要威胁类型.
3. 调用 `classify_inspection_log` 对该设备最近的巡检日志做 BERT 分类.
   (若无可用日志, 跳过此步.)
4. 从步骤 1 的最新一组气体值取出 [H2,CH4,C2H6,C2H4,C2H2,CO,CO2], 调用
   `classify_oil_chromatogram(values)` 做 CNN 分类.
5. 若步骤 3、4 都成功, 调用 `fuse_three_sources(log_result, oil_result, None)` 做证据融合.
6. 综合上述结果, 给出:
   - 当前设备状态评估 (健康 / 异常 / 故障)
   - 主要风险来源 (过热 / 放电 / 受潮 / 老化 / 起火 / 漏油 / 其它)
   - 各证据链的置信度对比
   - 推荐的运维措施

请用中文, 结构化输出, 引用每一步工具的关键数字."""


@mcp.prompt()
def quick_health_screen(equipment_id: str = "tr01") -> str:
    """30 秒快速健康筛查, 一次工具调用拿完整结果."""
    return f"""请对变压器 **{equipment_id}** 做一次快速健康筛查:

1. 直接调用 `assess_full_health(equipment_id="{equipment_id}")` 获取一站式诊断.
2. 用以下 4 行格式向用户汇报:
   - 健康指数: <HI>%
   - 剩余寿命: <RUL> 年
   - 主要威胁: <primary_threat>
   - 一句话建议: <expert_advice>

完成后简要解释 `diagnosis_summary` 的核心结论 (不要复述全文)."""


@mcp.prompt()
def explain_dga_anomaly(equipment_id: str = "tr01") -> str:
    """专门聚焦于 DGA 气体异常的解释和成因分析."""
    return f"""请聚焦于变压器 **{equipment_id}** 的油中溶解气体 (DGA) 异常分析:

1. 调用 `get_dga_trends({equipment_id})` 获取趋势.
2. 调用 `analyze_dga(trends)` 拿到风险评分.
3. 重点讨论:
   - 哪些气体最近 24 小时内有异常上升趋势?
   - 这些气体的组合特征指向何种典型故障 (过热 / 放电 / 局部放电)?
   - 引用 IEC 60599 / DL/T 722 等标准的判据 (若有相关知识).
4. 给出后续监测频率建议 (每周 / 每日 / 立即取样).

请用工程师能直接采取行动的语言, 避免抽象描述."""
