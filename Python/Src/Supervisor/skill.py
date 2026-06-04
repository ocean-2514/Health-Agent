"""Skill — the unit the SupervisorAgent dispatches to.

A *Skill* in the outer layer is the analogue of an *Agent* in the inner
LangGraph: it has a card (name / description / IO schema) and a ``run``
method. The supervisor surfaces every registered skill as a LangChain
tool, and the tool-calling LLM picks which to invoke per user request.

IO contracts use **Pydantic models** rather than the inner
``ArtifactSpec``: Skill IO is function-call semantics (request / response,
JSON Schema directly derivable), whereas ``ArtifactSpec`` describes slots
in a shared blackboard. Different layer, different abstraction.

A future remote A2A agent slots in by simply being wrapped as a Skill —
the supervisor and the rest of the package see one uniform interface.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol, Type, runtime_checkable

from langchain_core.tools import StructuredTool
from pydantic import BaseModel


@dataclass(frozen=True)
class SkillCard:
    """Capability manifest for one Skill.

    ``description`` is the field the LLM reads to decide *when* to call the
    skill — be specific about the use case ("用于: ..."). ``input_model`` /
    ``output_model`` are Pydantic classes; the input model's JSON Schema is
    handed to the LLM as the tool's argument spec.
    """

    name: str
    description: str
    input_model: Type[BaseModel]
    output_model: Type[BaseModel]


@runtime_checkable
class Skill(Protocol):
    """A routable, callable unit. Local class or remote-agent proxy both qualify."""

    card: SkillCard

    def run(self, **kwargs: Any) -> BaseModel:
        """Validate ``kwargs`` against ``card.input_model`` and return an
        instance of ``card.output_model``."""
        ...


def skill_to_tool(skill: Skill) -> StructuredTool:
    """Wrap a Skill as a LangChain ``StructuredTool`` the supervisor can call.

    The LLM sees:
      * ``name`` and ``description`` from the card
      * ``args_schema`` from ``input_model`` (LangChain converts it to the
        JSON Schema the model's tool-calling interface needs)

    The returned function takes the same kwargs the LLM emits, runs the
    skill, and returns its output as a plain dict (LangChain tool results
    must be JSON-serialisable; a Pydantic model's ``model_dump`` does it).
    """
    card = skill.card

    def _invoke(**kwargs: Any) -> dict:
        result = skill.run(**kwargs)
        if isinstance(result, BaseModel):
            return result.model_dump(mode="json")
        return result  # tolerant fallback — skills SHOULD return BaseModel

    return StructuredTool.from_function(
        func=_invoke,
        name=card.name,
        description=card.description,
        args_schema=card.input_model,
    )
