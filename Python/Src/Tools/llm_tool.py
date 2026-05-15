"""LLM helper layer.

The MCP server in Phase 2 does **not** expose LLM generation as a tool
(the MCP client itself is already an LLM, so doing so would be circular).
This module exists for *internal* callers like the legacy AssessmentService
which need to enrich pure-tool outputs with an LLM-written narrative for
API back-compat.

Provides:
  * `get_llm()`             - singleton LLMService accessor
  * `is_fallback(text)`     - detect a degraded response so callers can
                              decide whether to surface the placeholder
                              or fall back to a deterministic template
  * `render_defect_prompt`  - reusable prompt for defect summary
  * `render_rul_prompt`     - reusable prompt for RUL diagnosis summary
"""
from __future__ import annotations

import json
import sys
from functools import lru_cache
from pathlib import Path
from typing import Any, Dict, Optional

project_root = str(Path(__file__).resolve().parent.parent.parent.parent)
if project_root not in sys.path:
    sys.path.append(project_root)

from Python.Src.Utils.LLMService import LLMService


@lru_cache(maxsize=1)
def get_llm() -> LLMService:
    """Return the process-wide LLMService instance (cheap to reuse)."""
    return LLMService()


def is_fallback(text: Optional[str]) -> bool:
    """True if the text is a degraded response from LLMService.

    Lets callers do `if is_fallback(text): use_template_instead(...)`.
    """
    if not text:
        return True
    return text.startswith(LLMService.FALLBACK_PREFIX)


# ---------------------------------------------------------------------------
# Reusable prompt builders (kept here so callers don't re-invent the wording)
# ---------------------------------------------------------------------------

def render_defect_prompt(final_result_cn: str, confidence: float) -> str:
    """Prompt used to enrich D-S fusion output with an expert-style summary."""
    return f"""作为一名电力变压器运维专家，请根据以下多源融合检测结果，提供一段专业的技术分析总结。

检测结论：{final_result_cn}
综合置信度：{confidence:.2f}

请按照以下结构输出：
1. 现状评估：简述当前设备状态。
2. 证据链分析：结合多源融合特征（文本日志、油色谱、视觉识别）解释判定依据。
3. 建议措施：给出后续运维建议。

字数控制在200字以内，语言专业严谨。"""


def render_rul_prompt(
    health_index: float,
    predicted_rul_years: float,
    physics_input: Dict[str, Any],
    defect_cn: Optional[str] = None,
) -> str:
    """Prompt used to enrich RUL physics output with a lifecycle narrative."""
    defect_clause = defect_cn or "未检测到明显缺陷"
    return f"""作为电力变压器全寿命周期管理专家，请结合以下物理模型计算指标，进行深度的生命周期推演分析。

核心计算结果：
- 健康指数 (HI): {health_index} (反映当前绝缘老化程度)
- 预测剩余寿命 (RUL): {predicted_rul_years} 年 (基于物理劣化趋势)
- 关键输入参数: {json.dumps(physics_input, ensure_ascii=False)}

请严格按照以下专业维度进行推演：
1. 【缺陷影响评估】：结合缺陷识别结果（{defect_clause}），分析其对绝缘系统和剩余寿命的瞬时影响。
2. 【劣化机理推断】：分析当前 HI 指数对应的物理化学劣化状态（如：纤维素降解、油泥析出风险）。
3. 【演化趋势预测】：预测在当前负载率下，未来 5-10 年的健康状态演变。
4. 【不确定性量化】：指出由于环境载荷波动或测量噪声导致预测结果的潜在偏差范围。

输出要求：保持学术严谨性与运维指导价值。如果存在重大缺陷，必须在结论中首要强调。"""


if __name__ == "__main__":
    llm = get_llm()
    print(f"LLM available: {llm.is_available()}")
    sample = render_defect_prompt("起火", 0.95)
    print(f"Prompt sample (first 80 chars): {sample[:80]}")
