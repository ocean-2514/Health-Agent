"""Supervisor — the outer-layer LLM tool-calling orchestrator.

Builds a LangGraph ReAct-style agent over a list of registered ``Skill``s.
On each ``chat()`` turn it loads the session history from
:class:`SessionStore`, runs the agent (which may invoke 0+ skills in
sequence as the LLM decides), persists the new exchange, and returns the
LLM's final answer.

LangChain 1.x reorganised its agent API; the simplest portable choice is
``langgraph.prebuilt.create_react_agent``, which compiles a tool-calling
loop into a LangGraph StateGraph. The supervisor itself contains no domain
logic — every action is either a direct LLM response or a tool call into
one of the Skills.
"""
from __future__ import annotations

import sys
from pathlib import Path
from typing import List, Optional, Sequence

from langchain_core.messages import AIMessage, BaseMessage, HumanMessage
from langchain_ollama import ChatOllama
from langgraph.prebuilt import create_react_agent

project_root = str(Path(__file__).resolve().parents[3])
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from Python.Src.Middleware.GlobalConfig import GlobalConfig
from Python.Src.Supervisor.session import SessionStore, default_store
from Python.Src.Supervisor.skill import Skill, skill_to_tool


_SYSTEM_PROMPT = (
    "你是变压器健康管控领域的助理。你可以调用下列工具来完成实际诊断、检索、"
    "历史查询等具体任务,也可以直接对用户的概念性 / 闲聊问题作答。\n\n"
    "调用工具的判断原则:\n"
    "  - 用户明确要求'诊断 / 体检 / 评估 / 查 RUL / 查健康指数' → 调 transformer_diagnosis\n"
    "  - 用户问'某缺陷怎么处理 / 某规程怎么规定' → 调 knowledge_qa(若已注册)\n"
    "  - 用户问'这台设备上次诊断结果 / 历史趋势' → 调 history_lookup(若已注册)\n"
    "  - 纯概念解释 / 寒暄 / follow-up(上一轮已给出的指标) → 直接作答, 不要重复调用工具\n"
    "  - 一次请求可以同时调多个独立工具, 提高效率\n\n"
    "工具返回结构化结果后, 用自然语言简洁回答用户; 数值类指标请直接引用, "
    "不要瞎编。"
)


class Supervisor:
    """Multi-turn chat orchestrator over a fixed set of Skills."""

    def __init__(
        self,
        skills: Sequence[Skill],
        *,
        session_store: SessionStore = default_store,
        model_name: Optional[str] = None,
        base_url: Optional[str] = None,
        temperature: float = 0.0,
    ) -> None:
        if not skills:
            raise ValueError("Supervisor requires at least one Skill")

        cfg = GlobalConfig.config.get("LLM", {}).get("Local", {})
        self._model_name = model_name or cfg.get("ModelName", "gpt-oss:120b-cloud")
        self._base_url = base_url or cfg.get("BaseURL", "http://localhost:11434")

        self._store = session_store
        self._tools = [skill_to_tool(s) for s in skills]

        llm = ChatOllama(
            model=self._model_name,
            base_url=self._base_url,
            temperature=temperature,
        )
        self._agent = create_react_agent(
            model=llm,
            tools=self._tools,
            prompt=_SYSTEM_PROMPT,
        )

    # ------------------------------------------------------------- public

    def chat(self, session_id: str, user_input: str) -> str:
        """Run one chat turn against ``session_id`` and return the answer."""
        messages: List[BaseMessage] = self._load_history(session_id)
        messages.append(HumanMessage(content=user_input))

        try:
            result = self._agent.invoke({"messages": messages})
        except Exception as e:  # noqa: BLE001
            answer = f"[supervisor 内部错误] {e}"
        else:
            answer = self._extract_final_answer(result.get("messages", []))

        if not answer:
            answer = "(模型未返回有效内容)"

        self._store.save_message(session_id, "user", user_input)
        self._store.save_message(session_id, "assistant", answer)
        return answer

    def new_session(self) -> str:
        """Create a fresh session id."""
        return self._store.create_session()

    @property
    def skill_names(self) -> List[str]:
        return [t.name for t in self._tools]

    # ------------------------------------------------------------- helpers

    def _load_history(self, session_id: str) -> List[BaseMessage]:
        msgs: List[BaseMessage] = []
        for row in self._store.get_history(session_id):
            role, content = row["role"], row["content"]
            if role == "user":
                msgs.append(HumanMessage(content=content))
            elif role == "assistant":
                msgs.append(AIMessage(content=content))
        return msgs

    @staticmethod
    def _extract_final_answer(messages: Sequence[BaseMessage]) -> str:
        """Pull the last natural-language assistant message out of the agent
        trace. Skips tool-call / tool-result frames."""
        for msg in reversed(messages):
            kind = getattr(msg, "type", "")
            if kind == "tool":
                continue
            content = getattr(msg, "content", None)
            if not content:
                continue
            if isinstance(content, list):
                # Some chat models return content as a list of parts.
                parts = [p.get("text", "") for p in content if isinstance(p, dict)]
                joined = "".join(parts).strip()
                if joined:
                    return joined
                continue
            text = str(content).strip()
            if text:
                return text
        return ""
