"""DL/T 1685-2017 附录 A 状态量评价规则表（数据）。

本文件把附录 A（A.1 本体、A.2 套管、A.3 冷却系统、A.4 有载分接开关）转写为数据，
供 ``dlt1685.py`` 引擎驱动。每个状态量以唯一 ``key`` 标识；``ITEMS`` 给出其部件、
中文名与可选分组（同组只按最高扣分计一次，如 DGA 各气体）；``RULES`` 给出每个
劣化程度对应的 基本扣分/影响因子/判据。

判据 criterion：
  ("obs",)                    定性项，调用方给劣化程度（"Ⅰ"~"Ⅳ" 或 True=该项最高级）
  ("num", lo, hi)             数值项，lo<=x<hi 命中；hi=None 表示 +∞
  ("numv", {"low":(lo,hi),"high":(lo,hi)})  电压相关，low=110~220kV，high=330kV+
  ("interp", x0, x1, y0, y1)  定量项，x∈[x0,x1) 基本扣分线性插值 y0→y1

说明与简化（已在导则允许范围内，缺失项默认不扣分，条款 6e）：
  · 依赖“产气速率/增长趋势”“多条件组合”等无法由单一数值判定的项，采用 ("obs",)，
    由上游诊断/人工给出劣化程度；
  · 涉及电压等级的阈值用 numv，以 110~220kV 与 330kV+ 两档给出；
  · 油击穿电压、聚合度为“越低越严重”，其 num 区间按“低于阈值命中”。
"""
from __future__ import annotations

from typing import Any, Dict, List

INF = None

# item key -> {component, name, group?}
ITEMS: Dict[str, Dict[str, Any]] = {}
RULES: List[Dict[str, Any]] = []


def _item(key: str, component: str, name: str, group: str | None = None) -> None:
    ITEMS[key] = {"component": component, "name": name}
    if group:
        ITEMS[key]["group"] = group


def _rule(key: str, level: str, factor: int, criterion, basis: str) -> None:
    RULES.append({"key": key, "level": level, "factor": factor,
                  "criterion": criterion, "basis": basis})


# ===========================================================================
# A.1 变压器本体
# ===========================================================================
B = "本体"

_item("b_short_circuit", B, "短路电流、短路次数")
_rule("b_short_circuit", "Ⅰ", 2, ("obs",), "短路冲击电流50%~70%,累计≥6次")
_rule("b_short_circuit", "Ⅱ", 2, ("obs",), "短路冲击电流70%~90%,按次扣分")
_rule("b_short_circuit", "Ⅳ", 2, ("obs",), "短路冲击电流≥90%,按次扣分")

_item("b_overload", B, "变压器过负荷")
_rule("b_overload", "Ⅰ", 2, ("obs",), "达到短期/长期急救负载运行规定")

_item("b_overexcite", B, "过励磁")
_rule("b_overexcite", "Ⅰ", 2, ("obs",), "达到变压器过励磁限值")

_item("b_conservator_seal", B, "储油柜密封元件")
_rule("b_conservator_seal", "Ⅱ", 4, ("obs",), "金属膨胀器卡滞/隔膜式密封面渗油")
_rule("b_conservator_seal", "Ⅳ", 4, ("obs",), "金属膨胀器破裂/胶囊隔膜破损")

_item("b_oil_level", B, "本体储油柜油位")
_rule("b_oil_level", "Ⅱ", 2, ("obs",), "油位异常:过高或过低")

_item("b_seep", B, "渗油")
_rule("b_seep", "Ⅰ", 2, ("obs",), "轻微渗油,未形成油滴,非负压区")

_item("b_leak", B, "漏油")
_rule("b_leak", "Ⅱ", 4, ("obs",), "轻微渗漏(非负压区),慢于每滴5s")
_rule("b_leak", "Ⅳ", 4, ("obs",), "渗漏位于负压区/快于每滴5s/形成油流")

_item("b_noise", B, "噪声及振动")
_rule("b_noise", "Ⅰ", 4, ("obs",), "噪声振动异常,油中溶解气体正常")
_rule("b_noise", "Ⅱ", 4, ("obs",), "噪声振动异常,油中溶解气体异常")

_item("b_rust", B, "表面锈蚀")
_rule("b_rust", "Ⅰ", 1, ("obs",), "表面漆层破损和轻微锈蚀")
_rule("b_rust", "Ⅲ", 1, ("obs",), "表面锈蚀严重")

_item("b_breather", B, "呼吸器")
_rule("b_breather", "Ⅱ", 2, ("obs",), "吸湿器油封异常/呼吸不畅/硅胶潮解>2/3")
_rule("b_breather", "Ⅳ", 2, ("obs",), "呼吸器无呼吸")

_item("b_oil_temp", B, "运行油温")
_rule("b_oil_temp", "Ⅲ", 3, ("obs",), "顶层油温异常")

_item("b_pressure_relief", B, "压力释放阀")
_rule("b_pressure_relief", "Ⅳ", 4, ("obs",), "动作(周围有油迹)")

_item("b_gas_relay", B, "气体继电器")
_rule("b_gas_relay", "Ⅱ", 4, ("obs",), "轻瓦斯发信,油中气体无异常")
_rule("b_gas_relay", "Ⅳ", 4, ("obs",), "轻瓦斯发信且色谱异常/重瓦斯动作")

_item("b_winding_dcr", B, "绕组直流电阻")
_rule("b_winding_dcr", "Ⅳ", 3, ("obs",), "相间差>2%(无中性点线间>1%)或同相初值差>±2%")

_item("b_winding_tan", B, "绕组介质损耗因数")
_rule("b_winding_tan", "Ⅰ", 3, ("obs",), "未超限值但有显著性差异")
_rule("b_winding_tan", "Ⅲ", 3, ("obs",), "介损超标、电容量无明显变化")

_item("b_capacitance", B, "绕组电容量")
# 变化 3%~5% 线性插值 4→10；≥5% 取 10。影响因子 4。
_rule("b_capacitance", "Ⅱ", 4, ("interp", 3.0, 5.0, 4.0, 10.0), "绕组电容量变化3%~5%")
_rule("b_capacitance", "Ⅳ", 4, ("num", 5.0, INF), "绕组电容量变化>5%")

_item("b_core_ground", B, "铁芯接地电流")
_rule("b_core_ground", "Ⅰ", 2, ("num", 0.0, 0.1), "多点接地但接地电流≤0.1A")
_rule("b_core_ground", "Ⅱ", 2, ("interp", 0.1, 0.3, 2.0, 10.0), "接地电流0.1A~0.3A")
_rule("b_core_ground", "Ⅳ", 2, ("num", 0.3, INF), "接地电流>0.3A")

_item("b_freq_response", B, "绕组频率响应")
_rule("b_freq_response", "Ⅳ", 3, ("obs",), "频响反映绕组变形")

_item("b_short_impedance", B, "短路阻抗")
_rule("b_short_impedance", "Ⅰ", 3, ("num", 0.0, 2.0), "与原始值偏差<2%")
_rule("b_short_impedance", "Ⅱ", 3, ("interp", 2.0, 3.0, 4.0, 10.0), "偏差2%~3%")
_rule("b_short_impedance", "Ⅳ", 3, ("num", 3.0, INF), "偏差>3%")

_item("b_leakage_current", B, "泄漏电流")
_rule("b_leakage_current", "Ⅱ", 1, ("interp", 30.0, 50.0, 4.0, 10.0), "历次变化30%~50%")
_rule("b_leakage_current", "Ⅳ", 1, ("num", 50.0, INF), "历次变化>50%")

_item("b_insulation_r", B, "绕组绝缘电阻/吸收比/极化指数")
_rule("b_insulation_r", "Ⅳ", 2, ("obs",), "绝缘电阻不满足规程要求")

_item("b_oil_tan", B, "油介质损耗因数")
_rule("b_oil_tan", "Ⅱ", 3, ("numv", {"low": (4.0, INF), "high": (2.0, INF)}),
      "110~220kV tanδ≥4%；330kV+ ≥2%")

_item("b_oil_breakdown", B, "油击穿电压")
# 越低越严重：低于阈值命中（用 (-inf, thr) 表示 x<thr）
_rule("b_oil_breakdown", "Ⅱ", 3, ("numv", {"low": (0.0, 35.0), "high": (0.0, 50.0)}),
      "110~220kV ≤35kV；330kV+ ≤50kV")

_item("b_moisture", B, "水分")
_rule("b_moisture", "Ⅱ", 3, ("numv", {"low": (25.0, INF), "high": (15.0, INF)}),
      "220kV ≥25mg/L；330kV+ ≥15mg/L(110kV ≥35)")

_item("b_gas_content", B, "油中含气量")
_rule("b_gas_content", "Ⅱ", 2, ("num", 3.0, INF), "500kV油中含气量>3%")

_item("b_paper_dp", B, "绝缘纸聚合度")
_rule("b_paper_dp", "Ⅳ", 3, ("num", 0.0, 250.0), "聚合度≤250")

_item("b_furfural", B, "糠醛含量")
_rule("b_furfural", "Ⅳ", 3, ("obs",), "糠醛含量异常(参见DL/T 984)")

_item("b_infrared", B, "红外测温")
_rule("b_infrared", "Ⅱ", 3, ("obs",), "油箱红外测温异常")

# DGA 气体（同组只按最高扣分计一次）
_item("b_dga_hydrocarbon", B, "油中溶解气体-总烃", group="b_dga")
_rule("b_dga_hydrocarbon", "Ⅱ", 3, ("num", 150.0, INF), "总烃>150μL/L(产气速率低)")
_item("b_dga_c2h2", B, "油中溶解气体-C2H2", group="b_dga")
_rule("b_dga_c2h2", "Ⅱ", 3, ("numv", {"low": (5.0, INF), "high": (1.0, INF)}),
      "C2H2>注意值(330kV+1;其他5μL/L)无增长")  # 基本扣分8见下
_rule("b_dga_c2h2", "Ⅳ", 3, ("obs",), "C2H2>注意值且有增长趋势/伴CO明显增长")
_item("b_dga_h2", B, "油中溶解气体-H2", group="b_dga")
_rule("b_dga_h2", "Ⅱ", 2, ("num", 150.0, INF), "H2>150μL/L")
_item("b_dga_co", B, "油中溶解气体-CO/CO2", group="b_dga")
_rule("b_dga_co", "Ⅱ", 2, ("obs",), "CO含量有明显增长")

_item("b_neutral_dc", B, "中性点直流电流")
_rule("b_neutral_dc", "Ⅰ", 3, ("interp", 1.0, 3.0, 2.0, 8.0), "中性点直流电流1A~3A")
_rule("b_neutral_dc", "Ⅲ", 3, ("num", 3.0, INF), "中性点直流电流>3A")

_item("b_pd", B, "局部放电")
_rule("b_pd", "Ⅳ", 4, ("obs",), "异常放电信号或典型放电图谱")

_item("b_family_defect", B, "家族缺陷/同厂同型同期故障")
_rule("b_family_defect", "Ⅱ", 3, ("obs",), "一般缺陷未整改")
_rule("b_family_defect", "Ⅳ", 3, ("obs",), "重大缺陷未整改")

_item("b_short_capability", B, "抗短路能力校核")
_rule("b_short_capability", "Ⅲ", 2, ("obs",), "校核结果不满足当前电网最大短路电流")

_item("b_lv_bus", B, "低压母线绝缘化")
_rule("b_lv_bus", "Ⅲ", 2, ("obs",), "35kV及以下低压母线未绝缘化")

_item("b_conservator_age", B, "储油柜密封件运行年限")
_rule("b_conservator_age", "Ⅲ", 2, ("obs",), "胶囊/隔膜且运行超15年")

_item("b_winding_material", B, "绕组材质及工艺")
_rule("b_winding_material", "Ⅲ", 2, ("obs",), "薄绝缘铝线圈且运行超20年")


# ===========================================================================
# A.2 套管
# ===========================================================================
T = "套管"

_item("t_ext_insulation", T, "外绝缘")
_rule("t_ext_insulation", "Ⅳ", 3, ("obs",), "外绝缘爬距不满足且未采取措施")

_item("t_appearance", T, "外观")
_rule("t_appearance", "Ⅰ", 4, ("obs",), "瓷件微小脱釉或轻微渗漏")
_rule("t_appearance", "Ⅳ", 4, ("obs",), "套管严重渗漏")

_item("t_oil_level", T, "油位指示")
_rule("t_oil_level", "Ⅳ", 3, ("obs",), "油位异常")

_item("t_insulation_r", T, "绝缘电阻")
_rule("t_insulation_r", "Ⅰ", 3, ("obs",), "主屏<10000MΩ或末屏<1000MΩ")

_item("t_tan", T, "介质损耗因数")
_rule("t_tan", "Ⅲ", 3, ("obs",), "介损达标准限值70%且变化>30%")
_rule("t_tan", "Ⅳ", 3, ("obs",), "介损超过标准要求")

_item("t_capacitance", T, "电容量")
_rule("t_capacitance", "Ⅱ", 4, ("num", 4.0, 5.0), "与出厂/前值偏差>4%")
_rule("t_capacitance", "Ⅲ", 4, ("num", 5.0, INF), "与出厂/前值偏差>5%")

# 套管 DGA（同组只计一次）
_item("t_dga_c2h2", T, "气体分析-C2H2", group="t_dga")
_rule("t_dga_c2h2", "Ⅱ", 3, ("obs",), "C2H2含量大于注意值")  # 基本扣分8
_item("t_dga_ch4", T, "气体分析-CH4", group="t_dga")
_rule("t_dga_ch4", "Ⅱ", 3, ("num", 100.0, INF), "CH4>100μL/L")
_item("t_dga_h2", T, "气体分析-H2", group="t_dga")
_rule("t_dga_h2", "Ⅱ", 3, ("num", 500.0, INF), "H2>500μL/L")

_item("t_infrared", T, "红外测温")
_rule("t_infrared", "Ⅰ", 3, ("obs",), "柱头热点温度异常,温差≤10K")
_rule("t_infrared", "Ⅱ", 3, ("obs",), "柱头热点>55°C或相对温差>80%")
_rule("t_infrared", "Ⅲ", 3, ("obs",), "柱头热点>80°C或相对温差>95%/套管发热")

_item("t_pd", T, "局部放电")
_rule("t_pd", "Ⅳ", 3, ("obs",), "异常放电信号或典型放电图谱")


# ===========================================================================
# A.3 冷却（散热）器系统
# ===========================================================================
C = "冷却系统"

_item("c_motor", C, "电机运行")
_rule("c_motor", "Ⅰ", 2, ("obs",), "风机运行异常")
_rule("c_motor", "Ⅳ", 2, ("obs",), "油泵/水泵/油流继电器工作异常")

_item("c_control", C, "冷却装置控制系统")
_rule("c_control", "Ⅳ", 2, ("obs",), "冷却器控制系统异常")

_item("c_heat_dissipation", C, "散热效果")
_rule("c_heat_dissipation", "Ⅰ", 3, ("obs",), "表面积污但影响较小")
_rule("c_heat_dissipation", "Ⅳ", 3, ("obs",), "表面积污严重,影响明显")

_item("c_water_cooler", C, "水冷却器")
_rule("c_water_cooler", "Ⅳ", 4, ("obs",), "冷却水管有渗漏")

_item("c_seep", C, "渗油")
_rule("c_seep", "Ⅰ", 2, ("obs",), "轻微渗油,未形成油滴,非负压区")

_item("c_leak", C, "漏油")
_rule("c_leak", "Ⅰ", 4, ("obs",), "轻微渗油,未形成油滴,非负压区")
_rule("c_leak", "Ⅳ", 4, ("obs",), "渗漏位于负压区/快于每滴5s/形成油流")

_item("c_power", C, "电源")
_rule("c_power", "Ⅲ", 2, ("obs",), "未配三相电压监测/独立电源未自动切换")
_rule("c_power", "Ⅳ", 2, ("obs",), "强油循环未配2个相互独立电源")

_item("c_water_pressure", C, "水冷却器油水压")
_rule("c_water_pressure", "Ⅲ", 2, ("obs",), "单铜管水冷却油压小于水压")


# ===========================================================================
# A.4 有载分接开关
# ===========================================================================
S = "分接开关"

_item("s_oil_level", S, "油位指示")
_rule("s_oil_level", "Ⅱ", 3, ("obs",), "油位异常")
_rule("s_oil_level", "Ⅳ", 3, ("obs",), "油位异常")

_item("s_breather", S, "呼吸器")
_rule("s_breather", "Ⅱ", 2, ("obs",), "吸湿器油封异常/呼吸不畅/硅胶潮解>2/3")
_rule("s_breather", "Ⅳ", 2, ("obs",), "呼吸器无呼吸")

_item("s_tap_position", S, "分接位置")
_rule("s_tap_position", "Ⅳ", 4, ("obs",), "有载分接开关分接位置异常")

_item("s_leak", S, "渗漏")
_rule("s_leak", "Ⅰ", 3, ("obs",), "有轻微渗漏")
_rule("s_leak", "Ⅳ", 3, ("obs",), "渗漏严重")

_item("s_switch_count", S, "切换次数")
_rule("s_switch_count", "Ⅲ", 3, ("obs",), "切换次数超厂家规定检修次数未检修")

_item("s_maint_interval", S, "与前次检修间隔")
_rule("s_maint_interval", "Ⅲ", 3, ("obs",), "超出制造厂规定检修时间间隔")

_item("s_online_filter", S, "在线滤油装置")
_rule("s_online_filter", "Ⅱ", 3, ("obs",), "在线滤油装置压力异常")
_rule("s_online_filter", "Ⅲ", 3, ("obs",), "未按制造厂规定维护")

_item("s_drive", S, "传动机构")
_rule("s_drive", "Ⅳ", 4, ("obs",), "电动机运行异常或传动机构卡涩")

_item("s_limit", S, "限位装置")
_rule("s_limit", "Ⅳ", 4, ("obs",), "限位装置失灵")

_item("s_slip", S, "滑挡")
_rule("s_slip", "Ⅳ", 3, ("obs",), "滑挡")

_item("s_control_loop", S, "控制回路")
_rule("s_control_loop", "Ⅳ", 3, ("obs",), "控制回路失灵,过电流闭锁异常")

_item("s_action_char", S, "动作特性")
_rule("s_action_char", "Ⅳ", 4, ("obs",), "动作特性试验不合格")

_item("s_oil_withstand", S, "油耐压")
_rule("s_oil_withstand", "Ⅳ", 3, ("obs",), "油耐压不合格")

_item("s_winding_dcr", S, "绕组直流电阻")
_rule("s_winding_dcr", "Ⅳ", 3, ("obs",), "相间差>2%(无中性点线间>1%)或同相初值差>±2%")


# 特例基本扣分覆盖：C2H2 的 Ⅱ 级基本扣分为 8（非表2默认4），见附录A。
for _r in RULES:
    if _r["key"] in ("b_dga_c2h2", "t_dga_c2h2") and _r["level"] == "Ⅱ":
        _r["base_override"] = 8
