"""Two-in-one: demonstrates the ``TOOLS = [...]`` plural form."""
from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field

from Python.Src.Supervisor.tool import ToolCard


class _NoInput(BaseModel):
    pass


class _TimeOut(BaseModel):
    iso: str = Field(..., description="Current local time, ISO 8601.")
    weekday: str


class CurrentTimeTool:
    card = ToolCard(
        name="current_time",
        description="Returns the agent host's current local time.",
        input_model=_NoInput,
        output_model=_TimeOut,
    )

    def run(self, **kwargs: Any) -> _TimeOut:
        now = datetime.now()
        return _TimeOut(iso=now.isoformat(timespec="seconds"), weekday=now.strftime("%A"))


class _YearOut(BaseModel):
    year: int


class CurrentYearTool:
    card = ToolCard(
        name="current_year",
        description="Returns the agent host's current year as an integer.",
        input_model=_NoInput,
        output_model=_YearOut,
    )

    def run(self, **kwargs: Any) -> _YearOut:
        return _YearOut(year=datetime.now().year)


TOOLS = [CurrentTimeTool(), CurrentYearTool()]
