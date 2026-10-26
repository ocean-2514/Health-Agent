"""Adapter: a remote A2A **agent** looks like one local ``Tool``.

A remote A2A peer is conceptually an *Agent* (it serves its own AgentCard,
runs its own loop). The Supervisor's LLM never talks to it directly —
following the platform rule "the LLM only calls Tools", the remote agent is
*reached through* this Tool wrapper. From the LLM's side it is just another
``transformer_diagnosis``-shaped entry in the tool list.

Input / output deliberately stay generic (``instruction`` in, ``text`` +
optional ``raw_json`` out): A2A messages are typed only at the parts level
(``text`` / ``data`` / ``raw``), so forcing per-remote Pydantic schemas
here would either be a YAML-encoded model (fragile) or an extra Python file
per remote agent (boilerplate). The LLM is comfortable with "natural-
language instruction in, natural-language reply out".
"""
from __future__ import annotations

import json
from typing import Any, Optional

from pydantic import BaseModel, Field

from Python.Src.Supervisor.remote.a2a_client import A2AClient, A2AClientError
from Python.Src.Supervisor.tool import ToolCard


class RemoteA2AInput(BaseModel):
    instruction: str = Field(
        ...,
        description=(
            "Natural-language instruction or query to send to the remote agent. "
            "Include all context the remote needs — it does not see chat history."
        ),
    )


class RemoteA2AOutput(BaseModel):
    text: str = Field(..., description="Remote agent's reply, as plain text.")
    raw_json: Optional[Any] = Field(
        None,
        description=(
            "If the reply text was valid JSON, the parsed object. "
            "None otherwise."
        ),
    )
    success: bool = True
    error: Optional[str] = None


class RemoteA2ATool:
    """Wraps one A2A endpoint as a Tool.

    Failures (transport, no reply, schema) are returned as ``success=False``
    rather than raised — the Supervisor's LangChain tool layer would
    convert raises to opaque ``"Tool error: ..."`` strings, but a typed
    failure result lets the LLM (and the user log) see what happened.
    """

    def __init__(
        self,
        *,
        name: str,
        description: str,
        url: str,
        timeout_s: float = 30.0,
        client: Optional[A2AClient] = None,
    ) -> None:
        self.url = url
        self.timeout_s = timeout_s
        self._client = client or A2AClient(default_timeout_s=timeout_s)
        self.card = ToolCard(
            name=name,
            description=description,
            input_model=RemoteA2AInput,
            output_model=RemoteA2AOutput,
        )

    def run(self, **kwargs: Any) -> RemoteA2AOutput:
        ipt = RemoteA2AInput(**kwargs)
        try:
            text = self._client.send_text(
                self.url, ipt.instruction, timeout_s=self.timeout_s
            )
        except A2AClientError as e:
            return RemoteA2AOutput(text="", success=False, error=str(e))

        parsed: Any = None
        stripped = text.strip()
        if stripped and stripped[0] in "{[":
            try:
                parsed = json.loads(stripped)
            except json.JSONDecodeError:
                parsed = None
        return RemoteA2AOutput(text=text, raw_json=parsed)
