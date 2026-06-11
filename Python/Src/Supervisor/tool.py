"""Tool — the unit the Supervisor's LLM directly calls.

A *Tool* is the only thing the orchestrating LLM invokes directly
(function-calling). Everything else the platform offers is reached
*through* a Tool:

  * a deterministic **Workflow** (the Phase 3-5 diagnosis graph) is wrapped
    as one Tool (``transformer_diagnosis``);
  * a remote **Agent** (A2A protocol) is wrapped as one Tool
    (``RemoteA2ATool``);
  * a pure **primitive** (a SQL lookup, a calculation) is wrapped as one
    Tool (``history_lookup``).

This mirrors how CodeWhale / the Claude Agent SDK draw the line: the LLM
calls Tools; knowledge (Skills, see ``skill.py``) and delegation (Agents)
are surfaced *to* the LLM but are not themselves directly callable units.

IO contracts use **Pydantic models**: a Tool call is function-call
semantics (request / response, JSON Schema directly derivable). This is a
different abstraction from the inner platform's ``ArtifactSpec`` (which
describes slots in a shared blackboard) — different layer, different
contract.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol, Type, runtime_checkable

from langchain_core.tools import StructuredTool
from pydantic import BaseModel


@dataclass(frozen=True)
class ToolCard:
    """Capability manifest for one Tool.

    ``description`` is the field the LLM reads to decide *when* to call the
    tool — be specific about the use case ("用于: ..."). ``input_model`` /
    ``output_model`` are Pydantic classes; the input model's JSON Schema is
    handed to the LLM as the tool's argument spec.
    """

    name: str
    description: str
    input_model: Type[BaseModel]
    output_model: Type[BaseModel]


@runtime_checkable
class Tool(Protocol):
    """A routable, callable unit. Local class, workflow wrapper, or
    remote-agent proxy all qualify."""

    card: ToolCard

    def run(self, **kwargs: Any) -> BaseModel:
        """Validate ``kwargs`` against ``card.input_model`` and return an
        instance of ``card.output_model``."""
        ...


def to_langchain_tool(tool: Tool) -> StructuredTool:
    """Wrap our :class:`Tool` as a LangChain ``StructuredTool`` the
    supervisor's agent can call.

    The LLM sees:
      * ``name`` and ``description`` from the card
      * ``args_schema`` from ``input_model`` (LangChain converts it to the
        JSON Schema the model's tool-calling interface needs)

    The returned function takes the same kwargs the LLM emits, runs the
    tool, and returns its output as a plain dict (LangChain tool results
    must be JSON-serialisable; a Pydantic model's ``model_dump`` does it).
    """
    card = tool.card

    def _invoke(**kwargs: Any) -> dict:
        result = tool.run(**kwargs)
        if isinstance(result, BaseModel):
            return result.model_dump(mode="json")
        return result  # tolerant fallback — tools SHOULD return BaseModel

    return StructuredTool.from_function(
        func=_invoke,
        name=card.name,
        description=card.description,
        args_schema=card.input_model,
    )
