"""YAML-driven loader for remote A2A skills.

Reads ``Config/remote_skills.yaml``, builds one ``RemoteA2ASkill`` per
enabled entry, and returns the list. Companion to
``Python.Src.Supervisor.loader`` (which loads local skills); the upper
``load_skills`` function in that module concatenates the two.

**Relaxed probe**: at load time we try to fetch each remote's agent card
to enrich the local ``description`` (which is what the LLM reads to decide
when to call). If discovery fails we **still register the skill** with
the description supplied in YAML — remote services often start later
than this process, and failing-loud here would block the whole CLI just
because one remote isn't up yet. Failures emit a warning instead. The
call itself will fail at run time with ``success=False``, which the LLM
sees and can report or retry.

YAML shape::

    remote_skills:
      - name: defect_kb_search
        description: "Look up defect knowledge entries by symptom."
        url: http://localhost:9001
        timeout_s: 30
        enabled: true
        probe: true                 # default true; set false to skip card fetch
"""
from __future__ import annotations

import logging
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

import yaml

project_root = str(Path(__file__).resolve().parents[4])
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from Python.Src.Supervisor.remote.a2a_client import A2AClient, A2AClientError
from Python.Src.Supervisor.remote.remote_skill import RemoteA2ASkill

logger = logging.getLogger(__name__)

DEFAULT_REMOTE_SKILLS_YAML = Path(project_root) / "Config" / "remote_skills.yaml"


def _enrich_description(
    client: A2AClient, base_description: str, url: str, timeout_s: float
) -> str:
    """If the remote card has a longer description, prefer it; otherwise
    keep the locally-declared one. Either way, append the URL so the LLM
    knows it's a remote agent (useful debug context in tool-call traces)."""
    try:
        card = client.discover_card(url, timeout_s=timeout_s)
    except A2AClientError as e:
        logger.warning("A2A probe failed for %s: %s — registering anyway", url, e)
        return f"{base_description} [remote: {url}, unreachable at startup]"

    remote_name = card.get("name", "?")
    remote_desc = card.get("description") or ""
    if remote_desc and len(remote_desc) > len(base_description):
        chosen = remote_desc
    else:
        chosen = base_description
    return f"{chosen} [remote A2A agent: {remote_name} @ {url}]"


def load_remote_skills(
    yaml_path: Optional[Path] = None,
    client: Optional[A2AClient] = None,
) -> List[RemoteA2ASkill]:
    """Load every enabled remote skill from YAML. Missing file → empty list.

    A missing file is *not* an error — remote agents are optional in this
    deployment. The local skills loader is separately required to declare
    at least one skill.
    """
    path = Path(yaml_path or DEFAULT_REMOTE_SKILLS_YAML)
    if not path.exists():
        logger.info("no remote skills config at %s, skipping", path)
        return []

    with path.open("r", encoding="utf-8") as f:
        config = yaml.safe_load(f) or {}

    entries: List[Dict[str, Any]] = config.get("remote_skills") or []
    if not entries:
        return []

    shared_client = client or A2AClient()
    skills: List[RemoteA2ASkill] = []
    for entry in entries:
        if not entry.get("enabled", True):
            continue
        name = entry.get("name")
        url = entry.get("url")
        description = entry.get("description", "")
        if not (name and url and description):
            logger.warning("remote_skills entry missing name/url/description: %r", entry)
            continue
        timeout_s = float(entry.get("timeout_s", 30.0))
        probe = bool(entry.get("probe", True))

        if probe:
            description = _enrich_description(
                shared_client, description, url, timeout_s
            )

        skills.append(
            RemoteA2ASkill(
                name=name,
                description=description,
                url=url,
                timeout_s=timeout_s,
                client=shared_client,
            )
        )
    return skills
