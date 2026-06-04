"""YAML-driven Skill loader.

Reads ``Config/skills.yaml``, imports each declared class, instantiates it
(optionally with ``init_kwargs``), validates it satisfies the ``Skill``
protocol, and returns the list. Borrowed in spirit from the earlier
``D:/code/AI/project/agent`` SupervisorAgent's ``register_from_config``,
trimmed to fit the Phase 6 ``Skill`` shape.

Disabled entries are skipped silently. A bad ``class_path`` raises loud so
mis-typed config fails immediately.

Default config location: ``<repo>/Config/skills.yaml`` (sibling of the
existing ``GlobalConfig.yaml``).
"""
from __future__ import annotations

import importlib
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

import yaml

project_root = str(Path(__file__).resolve().parents[3])
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from Python.Src.Supervisor.skill import Skill

DEFAULT_SKILLS_YAML = Path(project_root) / "Config" / "skills.yaml"


class SkillLoadError(RuntimeError):
    """A declared skill failed to import / instantiate / validate."""


def _import_class(class_path: str) -> type:
    module_path, _, class_name = class_path.rpartition(".")
    if not module_path or not class_name:
        raise SkillLoadError(f"invalid class_path {class_path!r} (expected 'pkg.module.Class')")
    try:
        module = importlib.import_module(module_path)
    except Exception as e:
        raise SkillLoadError(f"failed to import module {module_path!r}: {e}") from e
    try:
        return getattr(module, class_name)
    except AttributeError as e:
        raise SkillLoadError(
            f"module {module_path!r} has no class {class_name!r}"
        ) from e


def load_skills(yaml_path: Optional[Path] = None) -> List[Skill]:
    """Load every enabled skill declared in ``yaml_path`` and return them.

    YAML shape::

        skills:
          - name: transformer_diagnosis
            class_path: Python.Src.Supervisor.skills.transformer_diagnosis.TransformerDiagnosisSkill
            enabled: true
            init_kwargs: {}      # optional, passed to the class constructor
    """
    path = Path(yaml_path or DEFAULT_SKILLS_YAML)
    if not path.exists():
        raise SkillLoadError(f"skills config not found: {path}")

    with path.open("r", encoding="utf-8") as f:
        config = yaml.safe_load(f) or {}

    entries: List[Dict[str, Any]] = config.get("skills") or []
    if not entries:
        raise SkillLoadError(f"{path} contains no 'skills' entries")

    skills: List[Skill] = []
    for entry in entries:
        if not entry.get("enabled", True):
            continue
        class_path = entry.get("class_path")
        if not class_path:
            raise SkillLoadError(f"skills entry missing class_path: {entry}")

        cls = _import_class(class_path)
        init_kwargs: Dict[str, Any] = entry.get("init_kwargs") or {}
        try:
            skill = cls(**init_kwargs)
        except Exception as e:
            raise SkillLoadError(
                f"failed to instantiate {class_path}: {e}"
            ) from e

        if not (hasattr(skill, "card") and hasattr(skill, "run")):
            raise SkillLoadError(
                f"{class_path} does not satisfy Skill protocol (need card + run)"
            )
        skills.append(skill)

    if not skills:
        raise SkillLoadError(f"{path} declared no enabled skills")
    return skills
