"""History lookup Tool — past diagnosis records for one equipment.

Queries the ``diagnosis_records`` table the :class:`TransformerDiagnosisTool`
writes after each successful run. Returns the recent records plus a tiny
trend summary (HI / RUL deltas vs. the previous run) so the supervisor LLM
can directly answer "之前诊断过吗 / 上次结果如何 / HI 趋势怎么样".

Cheap, deterministic, no LLM call — pure SQL. A textbook example of a Tool
that wraps a primitive (vs. transformer_diagnosis, which wraps a Workflow).
"""
from __future__ import annotations

import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field

project_root = str(Path(__file__).resolve().parents[4])
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from Python.Src.Supervisor.session import SessionStore, default_store
from Python.Src.Supervisor.tool import ToolCard


# ---------------------------------------------------------------------------
# IO contracts
# ---------------------------------------------------------------------------

class HistoryLookupInput(BaseModel):
    equipment_id: str = Field(..., description="变压器设备 ID, 如 'tr01'.")
    limit: int = Field(
        5, ge=1, le=50,
        description="最多返回多少条历史记录 (按时间倒序; 默认 5).",
    )


class HistoryRecord(BaseModel):
    run_at: str = Field(..., description="诊断时间 'YYYY-MM-DD HH:MM:SS'")
    health_index: Optional[float] = None
    predicted_rul_years: Optional[float] = None
    fusion_verdict_cn: Optional[str] = None
    fusion_confidence: Optional[float] = None
    dga_risk_score: Optional[float] = None
    primary_threat: Optional[str] = None
    forced_override: Optional[str] = None


class TrendDelta(BaseModel):
    """How the latest run compares to the immediately previous one."""
    health_index_delta: Optional[float] = None
    predicted_rul_years_delta: Optional[float] = None
    verdict_changed: Optional[bool] = None
    note: str = ""


class HistoryLookupOutput(BaseModel):
    equipment_id: str
    record_count: int
    records: List[HistoryRecord] = Field(default_factory=list)
    trend: Optional[TrendDelta] = Field(
        None, description="仅在至少有 2 条记录时填充; 比对最近两次."
    )
    summary: str = Field(..., description="一句话给 LLM 直接引用.")


# ---------------------------------------------------------------------------
# Tool
# ---------------------------------------------------------------------------

class HistoryLookupTool:
    """Look up persisted diagnosis records for one equipment id."""

    card = ToolCard(
        name="history_lookup",
        description=(
            "查询某台变压器过去的诊断记录(健康指数 / 剩余寿命 / 缺陷判定 / "
            "DGA 风险). 用于: 用户问'这台设备之前诊断过吗 / 上次结果是什么 / "
            "HI/RUL 怎么变化的'. 不重新跑诊断, 仅查历史. 若没有任何历史记录会"
            "明确告知."
        ),
        input_model=HistoryLookupInput,
        output_model=HistoryLookupOutput,
    )

    def __init__(self, session_store: SessionStore = default_store) -> None:
        self._store = session_store

    def run(self, **kwargs: Any) -> HistoryLookupOutput:
        inp = HistoryLookupInput(**kwargs)
        rows = self._store.get_diagnosis_records(inp.equipment_id, limit=inp.limit)
        records = [self._row_to_record(r) for r in rows]
        trend = self._compute_trend(records)
        summary = self._render_summary(inp.equipment_id, records, trend)
        return HistoryLookupOutput(
            equipment_id=inp.equipment_id,
            record_count=len(records),
            records=records,
            trend=trend,
            summary=summary,
        )

    # ----------------------------------------------------------- helpers

    @staticmethod
    def _row_to_record(row: Dict[str, Any]) -> HistoryRecord:
        return HistoryRecord(
            run_at=row["run_at"],
            health_index=row.get("health_index"),
            predicted_rul_years=row.get("predicted_rul_years"),
            fusion_verdict_cn=row.get("fusion_verdict_cn"),
            fusion_confidence=row.get("fusion_confidence"),
            dga_risk_score=row.get("dga_risk_score"),
            primary_threat=row.get("primary_threat"),
            forced_override=row.get("forced_override"),
        )

    @staticmethod
    def _compute_trend(records: List[HistoryRecord]) -> Optional[TrendDelta]:
        if len(records) < 2:
            return None
        latest, prev = records[0], records[1]  # records are newest-first

        def _delta(a, b):
            if a is None or b is None:
                return None
            return round(float(a) - float(b), 2)

        hi_delta = _delta(latest.health_index, prev.health_index)
        rul_delta = _delta(latest.predicted_rul_years, prev.predicted_rul_years)
        verdict_changed = None
        if latest.fusion_verdict_cn and prev.fusion_verdict_cn:
            verdict_changed = latest.fusion_verdict_cn != prev.fusion_verdict_cn

        notes: List[str] = []
        if hi_delta is not None:
            direction = "下降" if hi_delta < 0 else ("上升" if hi_delta > 0 else "持平")
            notes.append(f"HI {direction} {abs(hi_delta)}")
        if rul_delta is not None:
            direction = "缩短" if rul_delta < 0 else ("延长" if rul_delta > 0 else "持平")
            notes.append(f"RUL {direction} {abs(rul_delta)} 年")
        if verdict_changed:
            notes.append(f"缺陷判定由 '{prev.fusion_verdict_cn}' 变为 '{latest.fusion_verdict_cn}'")

        return TrendDelta(
            health_index_delta=hi_delta,
            predicted_rul_years_delta=rul_delta,
            verdict_changed=verdict_changed,
            note="; ".join(notes) if notes else "最近两次结果一致",
        )

    @staticmethod
    def _render_summary(
        equipment_id: str,
        records: List[HistoryRecord],
        trend: Optional[TrendDelta],
    ) -> str:
        if not records:
            return f"{equipment_id} 暂无历史诊断记录"
        latest = records[0]
        parts = [
            f"{equipment_id} 共 {len(records)} 条历史记录, "
            f"最近一次 {latest.run_at}"
        ]
        if latest.health_index is not None:
            parts.append(f"HI={latest.health_index}")
        if latest.predicted_rul_years is not None:
            parts.append(f"RUL={latest.predicted_rul_years}年")
        if latest.fusion_verdict_cn:
            parts.append(f"判定={latest.fusion_verdict_cn}")
        head = ", ".join(parts)
        if trend and trend.note:
            return f"{head}. 趋势: {trend.note}."
        return f"{head}."
