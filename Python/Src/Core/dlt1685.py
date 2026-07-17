"""DL/T 1685-2017《油浸式变压器（电抗器）状态评价导则》扣分制状态评价引擎。

标准是**状态评价导则**：对每个状态量按“劣化程度→基本扣分”乘以“重要程度→影响
因子”得到扣分，按部件汇总（单项扣分 + 合计扣分）映射为部件状态（正常/注意/异常/
严重），整体取最严重部件（第 7、8 章 + 附录 A、表 1/2/3）。

  · 表1 重要程度→影响因子：1/2/3/4 级 → 1/2/3/4
  · 表2 劣化程度→基本扣分：Ⅰ/Ⅱ/Ⅲ/Ⅳ → 2/4/8/10
  · 定量状态量在两级之间线性插值基本扣分：y=(x-x0)(y1-y0)/(x1-x0)+y0
  · 表3 部件评价阈值（合计/单项）；本体合计<30 为正常，其余部件<20；单项 <12 正常、
    [12,20) 注意、[20,30) 异常、≥30 严重
  · 条款 6e：状态量缺失可默认不扣分

本模块只实现**标准所定义**的评价（扣分→状态）。健康指数（HI）、剩余寿命（RUL）
不是标准内容，由 ``deduction_to_hi`` 等作为工程外延单独给出并显式声明为非标准定义。

数据来源：接**原始实测值**。数值型状态量由本模块按判断依据阈值判定劣化程度；
定性型状态量由调用方提供劣化程度（Ⅰ~Ⅳ 或 None）——因其判断本身依赖人工/上游诊断。

注：涉及电压等级的阈值（乙炔注意值、tanδ、击穿电压、水分等）以 110~220kV 为基准，
``voltage_kv`` 可切换到 330kV 及以上；规则以 ``rules_dlt1685.py`` 数据表给出。
"""
from __future__ import annotations

import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

project_root = str(Path(__file__).resolve().parents[3])
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from Python.Src.Core.rules_dlt1685 import RULES, ITEMS

# 表1：重要程度→影响因子
IMPORTANCE_FACTOR = {1: 1, 2: 2, 3: 3, 4: 4}
# 表2：劣化程度→基本扣分
BASE_DEDUCTION = {"Ⅰ": 2, "Ⅱ": 4, "Ⅲ": 8, "Ⅳ": 10}
LEVEL_ORDER = {"Ⅰ": 1, "Ⅱ": 2, "Ⅲ": 3, "Ⅳ": 4}

# 五个部件（第 3.2 条）
COMPONENTS = ["本体", "套管", "冷却系统", "分接开关", "非电量保护和在线监测装置"]

# 表3：部件评价阈值。合计扣分阈值本体为 30，其余为 20；单项扣分阈值统一。
_HEJI_ATTENTION = {"本体": 30, "套管": 20, "冷却系统": 20, "分接开关": 20,
                   "非电量保护和在线监测装置": 20}
# 单项扣分：<12 正常，[12,20) 注意，[20,30) 异常，≥30 严重
_DANXIANG = [(12, "正常"), (20, "注意"), (30, "异常"), (float("inf"), "严重")]

STATE_ORDER = {"正常": 0, "注意": 1, "异常": 2, "严重": 3}


# ---------------------------------------------------------------------------
# 结果结构
# ---------------------------------------------------------------------------

@dataclass
class ItemDeduction:
    key: str
    component: str
    item: str
    level: Optional[str]
    base: float
    factor: int
    deduction: float
    basis: str          # 判断依据（可审计）


@dataclass
class ComponentResult:
    component: str
    total_deduction: float          # 合计扣分
    max_single: float               # 单项最大扣分
    state: str
    items: List[ItemDeduction] = field(default_factory=list)


@dataclass
class EvaluationResult:
    overall_state: str
    total_deduction: float          # 全部部件合计扣分之和（供 HI 桥接参考）
    components: Dict[str, ComponentResult]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "overall_state": self.overall_state,
            "total_deduction": round(self.total_deduction, 2),
            "components": {
                c: {
                    "state": r.state,
                    "total_deduction": round(r.total_deduction, 2),
                    "max_single": round(r.max_single, 2),
                    "items": [
                        {
                            "item": it.item, "level": it.level,
                            "deduction": round(it.deduction, 2), "basis": it.basis,
                        }
                        for it in r.items if it.deduction > 0
                    ],
                }
                for c, r in self.components.items()
            },
        }


# ---------------------------------------------------------------------------
# 单项扣分计算
# ---------------------------------------------------------------------------

def _interp(x: float, x0: float, x1: float, y0: float, y1: float) -> float:
    if x1 == x0:
        return y1
    return (x - x0) * (y1 - y0) / (x1 - x0) + y0


def _eval_item(item_key: str, measurements: Dict[str, Any], voltage_kv: float) -> ItemDeduction:
    """对一个状态量计算扣分。缺失或不满足任何判据 → 扣分 0（条款 6e）。"""
    meta = ITEMS[item_key]
    comp, name = meta["component"], meta["name"]
    rules = [r for r in RULES if r["key"] == item_key]
    value = measurements.get(item_key)

    best: Optional[ItemDeduction] = None
    for r in rules:
        crit = r["criterion"]
        kind = crit[0]
        level = r["level"]
        factor = r["factor"]
        base: Optional[float] = None
        base_default = r.get("base_override", BASE_DEDUCTION[level])

        if kind == "obs":
            # 定性项：调用方直接给劣化程度（Ⅰ~Ⅳ 或 True）
            if value is None:
                continue
            provided = value if isinstance(value, str) else ("Ⅳ" if value is True else None)
            if provided == level:
                base = base_default
        elif kind == "num":
            # ("num", lo, hi[, vclass])：lo<=x<hi 命中该等级；hi=None 为 +inf
            if value is None:
                continue
            lo, hi = crit[1], crit[2]
            hi = float("inf") if hi is None else hi
            if lo <= float(value) < hi:
                base = base_default
        elif kind == "numv":
            # 电压相关：("numv", {"low":(lo,hi),"high":(lo,hi)})，low=110~220kV, high=330kV+
            if value is None:
                continue
            band = crit[1]["high"] if voltage_kv >= 330 else crit[1]["low"]
            lo, hi = band
            hi = float("inf") if hi is None else hi
            if lo <= float(value) < hi:
                base = base_default
        elif kind == "interp":
            # ("interp", x0, x1, y0, y1)：x∈[x0,x1) 基本扣分线性插值 y0→y1
            if value is None:
                continue
            x0, x1, y0, y1 = crit[1], crit[2], crit[3], crit[4]
            if x0 <= float(value) < x1:
                base = _interp(float(value), x0, x1, y0, y1)

        if base is None:
            continue
        ded = round(base * factor, 4)   # 规避插值浮点误差(如 0.8/0.2)
        cand = ItemDeduction(item_key, comp, name, level, base, factor, ded, r["basis"])
        # 取“劣化程度最高”的命中；同级取扣分更大者
        if best is None or (LEVEL_ORDER.get(level, 0), ded) > (LEVEL_ORDER.get(best.level, 0), best.deduction):
            best = cand

    if best is None:
        return ItemDeduction(item_key, comp, name, None, 0.0, 0, 0.0, "无扣分/数据缺失")
    return best


def _component_state(component: str, total: float, max_single: float) -> str:
    # 先按单项扣分判等级（异常/严重只看单项）
    single_state = "正常"
    for thr, st in _DANXIANG:
        if max_single < thr:
            single_state = st
            break
    # 合计扣分：达到注意阈值即为“注意”
    heji_state = "注意" if total >= _HEJI_ATTENTION[component] else "正常"
    # 取较严重者
    return single_state if STATE_ORDER[single_state] >= STATE_ORDER[heji_state] else heji_state


# ---------------------------------------------------------------------------
# 公开 API
# ---------------------------------------------------------------------------

def evaluate(measurements: Dict[str, Any], voltage_kv: float = 220.0) -> EvaluationResult:
    """按 DL/T 1685-2017 对给定状态量测量做整体状态评价。

    ``measurements`` 以状态量 key → 值：数值型给原始实测值（按判断依据阈值判劣化
    程度），定性型给劣化程度字符串（"Ⅰ"~"Ⅳ"）或 True（取该项最高等级）。缺失即不扣分。
    """
    comp_results: Dict[str, ComponentResult] = {}
    for comp in COMPONENTS:
        keys = [k for k, m in ITEMS.items() if m["component"] == comp]
        raw_items = [_eval_item(k, measurements, voltage_kv) for k in keys]

        # 分组折叠：同组（如 DGA 各气体）"按最高扣分只扣一次"（附录 A 备注）。
        group_best: Dict[str, ItemDeduction] = {}
        counted: List[ItemDeduction] = []
        for it in raw_items:
            g = ITEMS[it.key].get("group")
            if g:
                if g not in group_best or it.deduction > group_best[g].deduction:
                    group_best[g] = it
            elif it.deduction > 0:
                counted.append(it)
        counted.extend(group_best.values())

        total = sum(it.deduction for it in counted)
        max_single = max((it.deduction for it in counted), default=0.0)
        state = _component_state(comp, total, max_single)
        comp_results[comp] = ComponentResult(comp, total, max_single, state, counted)

    overall = max((r.state for r in comp_results.values()),
                  key=lambda s: STATE_ORDER[s], default="正常")
    total_all = sum(r.total_deduction for r in comp_results.values())
    return EvaluationResult(overall, total_all, comp_results)


# ---------------------------------------------------------------------------
# 工程外延：扣分 → 健康指数（HI）。**非 DL/T 1685 定义**，仅用于桥接物理 RUL。
# 映射原则：按整体状态分档（正常 85-100 / 注意 70-85 / 异常 50-70 / 严重 0-50），
# 档内按“最严重部件的单项扣分”在档区间内线性下降，保证与标准状态自洽、可解释。
# ---------------------------------------------------------------------------

_HI_BANDS = {"正常": (85.0, 100.0), "注意": (70.0, 85.0),
             "异常": (50.0, 70.0), "严重": (0.0, 50.0)}
# 各状态下“单项扣分”的参考区间（用于档内插值），依表3边界：<12 / 12-20 / 20-30 / 30-40+
_HI_SINGLE_REF = {"正常": (0.0, 12.0), "注意": (12.0, 20.0),
                  "异常": (20.0, 30.0), "严重": (30.0, 40.0)}


def deduction_to_hi(result: EvaluationResult) -> float:
    """将标准评价结果映射为 0-100 的健康指数（工程外延，非标准定义）。"""
    st = result.overall_state
    hi_lo, hi_hi = _HI_BANDS[st]
    ref_lo, ref_hi = _HI_SINGLE_REF[st]
    worst_single = max((r.max_single for r in result.components.values()), default=0.0)
    x = max(ref_lo, min(ref_hi, worst_single))
    # 扣分越大 HI 越低（档内从上界线性降到下界）
    frac = 0.0 if ref_hi == ref_lo else (x - ref_lo) / (ref_hi - ref_lo)
    hi = hi_hi - frac * (hi_hi - hi_lo)
    return round(max(0.0, min(100.0, hi)), 2)
