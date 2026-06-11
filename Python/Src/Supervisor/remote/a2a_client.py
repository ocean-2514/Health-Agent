"""Sync wrapper around ``a2a-sdk``'s async client.

The Supervisor and LangChain tools are synchronous (``Skill.run``); the
A2A SDK is async-first. Rather than push asyncio into the whole call
chain, we keep one short-lived event loop here and expose two blocking
methods:

  * ``discover_card(url)`` — fetch ``/.well-known/agent-card.json`` and
    return it as a dict. Used at platform startup for relaxed probing.
  * ``send_text(url, text)`` — full request/response round-trip; returns
    the concatenated text of all reply parts.

Failure modes are normalised to a single ``A2AClientError`` so callers
(``RemoteA2ASkill.run``) can map them to a Skill-level error message
instead of leaking transport details to the LLM.
"""
from __future__ import annotations

import asyncio
import json
import uuid
from typing import Any, Dict, Optional

import httpx

from a2a.client.card_resolver import A2ACardResolver
from a2a.client.client_factory import create_client
from a2a.types import Message, Part, Role, SendMessageRequest

AGENT_CARD_PATH = "/.well-known/agent-card.json"


class A2AClientError(RuntimeError):
    """Anything that goes wrong during an A2A call (transport, decode, no reply)."""


class A2AClient:
    """One blocking method per A2A interaction, no event loop bleed.

    Each call spins its own ``asyncio.run`` — fine for our throughput
    (single-user CLI, a few calls per LLM turn). If we ever want
    concurrency, switch to a persistent loop in a background thread.
    """

    def __init__(self, default_timeout_s: float = 30.0) -> None:
        self.default_timeout_s = default_timeout_s

    def discover_card(
        self, base_url: str, timeout_s: Optional[float] = None
    ) -> Dict[str, Any]:
        """Fetch the agent card; returns the raw JSON dict. Raises ``A2AClientError`` on failure."""
        timeout = timeout_s or self.default_timeout_s

        async def _go() -> Dict[str, Any]:
            async with httpx.AsyncClient(timeout=timeout) as http:
                resolver = A2ACardResolver(
                    httpx_client=http,
                    base_url=base_url,
                    agent_card_path=AGENT_CARD_PATH,
                )
                card = await resolver.get_agent_card()
                # protobuf message → dict
                from google.protobuf.json_format import MessageToDict
                return MessageToDict(card)

        try:
            return asyncio.run(_go())
        except Exception as e:
            raise A2AClientError(f"discover_card({base_url}) failed: {e}") from e

    def send_text(
        self,
        base_url: str,
        text: str,
        timeout_s: Optional[float] = None,
    ) -> str:
        """Send a single text message; return the joined text of all reply parts."""
        timeout = timeout_s or self.default_timeout_s

        async def _go() -> str:
            client = await create_client(
                base_url,
                resolver_http_kwargs={"timeout": timeout},
            )
            try:
                req = SendMessageRequest(
                    message=Message(
                        message_id=uuid.uuid4().hex,
                        role=Role.ROLE_USER,
                        parts=[Part(text=text)],
                    )
                )
                chunks = []
                async for resp in client.send_message(req):
                    if resp.HasField("message"):
                        for p in resp.message.parts:
                            if p.text:
                                chunks.append(p.text)
                    elif resp.HasField("task"):
                        for art in resp.task.artifacts:
                            for p in art.parts:
                                if p.text:
                                    chunks.append(p.text)
                if not chunks:
                    raise A2AClientError("remote returned no text parts")
                return "\n".join(chunks)
            finally:
                await client.close()

        try:
            return asyncio.run(_go())
        except A2AClientError:
            raise
        except Exception as e:
            raise A2AClientError(f"send_text({base_url}) failed: {e}") from e

if __name__ == "__main__":
    client = A2AClient()
    url = "http://localhost:9001"
    print(f"Discovering card at {url}...")
    try:
        card = client.discover_card(url)
        # print("Card discovered:")
        # print(json.dumps(card, indent=2))
        print(client.send_text(url, "Hello, agent!"))
        print("Message sent successfully.")
    except A2AClientError as e:
        print(f"Error: {e}")
        exit(1)