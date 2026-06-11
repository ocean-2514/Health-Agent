"""Trivial echo tool — exercises the TOOL convention used by
``discover_tools_from_path``.

Drop more files like this next to it; the loader picks any that export
``TOOL`` or ``TOOLS`` at module level.
"""
from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from Python.Src.Supervisor.tool import ToolCard


class EchoIn(BaseModel):
    text: str = Field(..., description="What to echo back.")


class EchoOut(BaseModel):
    echoed: str


class EchoTool:
    card = ToolCard(
        name="echo",
        description="Returns whatever text you pass in. Useful only for testing.",
        input_model=EchoIn,
        output_model=EchoOut,
    )

    def run(self, **kwargs: Any) -> EchoOut:
        return EchoOut(echoed=EchoIn(**kwargs).text)


TOOL = EchoTool()
