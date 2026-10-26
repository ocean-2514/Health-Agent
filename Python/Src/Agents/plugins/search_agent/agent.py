"""Search agent — retrieves defect-handling knowledge for a fused verdict.

A demonstration plugin for the dynamic platform. It consumes the typed
field ``fusion_result`` (the D-S fusion verdict) and produces the open
artifact ``search_notes``.

``search_defect_knowledge`` is a pure function deliberately kept free of
any LangGraph / platform import — so the *same* logic is reused unchanged
when this agent is exposed as a remote A2A server (see a2a_server.py).
"""
from __future__ import annotations

from typing import Any, Dict, List

from Python.Src.Agents.base import LocalPluginAgent
from Python.Src.Agents.registry import AgentCard
from Python.Src.Agents.state import Artifact, ArtifactSpec, DiagnosisState, make_message

AGENT_NAME = "search"


# ---------------------------------------------------------------------------
# Knowledge base (built-in; keyed by substrings of the Chinese verdict)
# ---------------------------------------------------------------------------

_KNOWLEDGE: Dict[str, List[Dict[str, str]]] = {
    "起火": [
        {"title": "变压器起火应急处置", "standard": "DL/T 572《电力变压器运行规程》",
         "advice": "立即停电隔离并启动消防，禁止带电灭火；火势控制后排查套管、引线接头熔损。"},
        {"title": "油浸式变压器火灾成因", "standard": "GB/T 1094.7",
         "advice": "多因内部电弧或绕组短路引燃油气；结合 DGA 乙炔突增与红外热像定位起火点。"},
    ],
    "漏油": [
        {"title": "渗漏油缺陷分级与处理", "standard": "Q/GDW 1168《输变电设备状态检修试验规程》",
         "advice": "按渗油/滴油/喷油分级；密封圈老化为主因，择期更换密封件并补油。"},
        {"title": "油位异常监视", "standard": "DL/T 572",
         "advice": "持续监视储油柜油位，防止油位过低引发套管进气放电。"},
    ],
    "放电": [
        {"title": "局部放电诊断", "standard": "GB/T 7252《变压器油中溶解气体分析和判断导则》",
         "advice": "用三比值法判别放电类型；C2H2 占比升高提示电弧放电，应安排带电局放检测。"},
        {"title": "放电性故障带电检测", "standard": "Q/GDW 11304",
         "advice": "采用特高频/超声波局放定位，并将油样分析周期缩短至每月一次。"},
    ],
    "过热": [
        {"title": "过热性故障判别", "standard": "GB/T 7252",
         "advice": "CH4、C2H4 比例上升指向过热；区分低温/中温/高温过热，排查铁芯多点接地。"},
        {"title": "热点温度评估", "standard": "GB/T 1094.7《负载导则》",
         "advice": "核算绕组热点温度与负载率，必要时限负荷运行。"},
    ],
    "异物": [
        {"title": "外部异物缺陷处置", "standard": "DL/T 572",
         "advice": "清除本体及套管周边异物，检查是否导致外绝缘距离不足。"},
    ],
    "破损": [
        {"title": "本体破损检查", "standard": "Q/GDW 1168",
         "advice": "评估破损部位对密封与绝缘的影响，安排停电检修。"},
    ],
    "受潮": [
        {"title": "绝缘受潮处理", "standard": "DL/T 572",
         "advice": "微水超标时安排真空滤油与干燥处理，复测击穿电压与介质损耗。"},
    ],
}

_DEFAULT_ENTRIES: List[Dict[str, str]] = [
    {"title": "常规状态监测", "standard": "Q/GDW 1168",
     "advice": "未匹配到特定缺陷知识，建议维持常规巡检频率与定期油样分析。"},
]


def search_defect_knowledge(verdict_cn: str) -> Dict[str, Any]:
    """Pure retrieval: match the verdict against the knowledge base.

    Transport-agnostic — reused verbatim by the A2A server wrapper.
    """
    verdict_cn = verdict_cn or ""
    entries: List[Dict[str, str]] = []
    matched: List[str] = []
    for keyword, items in _KNOWLEDGE.items():
        if keyword in verdict_cn:
            entries.extend(items)
            matched.append(keyword)
    if not entries:
        entries = list(_DEFAULT_ENTRIES)
    return {
        "query": verdict_cn,
        "matched_keywords": matched,
        "entries": entries,
        "source": "内置缺陷识别知识库",
    }


# ---------------------------------------------------------------------------
# Plugin wiring
# ---------------------------------------------------------------------------

# The agent's output contract — written into AgentCard.produces and used at
# the write site so the key / schema_name / version cannot drift.
SEARCH_NOTES = ArtifactSpec(
    key="search_notes",
    schema_name="DefectKnowledge",
    version=1,
    description="按缺陷判定检索到的运维知识 / 标准 / 处理建议条目",
)

SEARCH_CARD = AgentCard(
    name=AGENT_NAME,
    description="检索缺陷识别相关的运维知识、标准与处理规程",
    skills=["defect_knowledge_retrieval"],
    consumes=["fusion_result"],   # typed state field — runs after diagnosis
    produces=[SEARCH_NOTES],      # typed artifact contract (key + schema + version)
)


def search_node(state: DiagnosisState) -> dict:
    """Graph node: read the fused verdict, write a ``search_notes`` artifact."""
    verdict, conf = "未知", None
    if state.fusion_result is not None:
        final = state.fusion_result.final_fusion_result
        verdict, conf = final.final_result_cn, final.final_confidence

    notes = search_defect_knowledge(verdict)
    artifact = Artifact(
        key=SEARCH_NOTES.key,
        producer=AGENT_NAME,
        schema_name=SEARCH_NOTES.schema_name,
        version=SEARCH_NOTES.version,
        payload=notes,
        confidence=conf,
    )
    msg = make_message(
        sender=AGENT_NAME, receiver="coordinator", intent="result",
        summary=f"检索到 {len(notes['entries'])} 条与「{verdict}」相关的运维知识",
        confidence=conf,
    )
    return {"artifacts": {SEARCH_NOTES.key: artifact}, "comm_log": [msg]}


# The object the PluginLoader looks for.
AGENT = LocalPluginAgent(card=SEARCH_CARD, node=search_node)
