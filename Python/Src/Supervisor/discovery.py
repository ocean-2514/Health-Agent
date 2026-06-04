"""Directory-based skill discovery.

Mirrors the inner platform's ``Python.Src.Agents.loader.PluginLoader``
(which scans ``plugins/*/agent.py`` for ``AGENT = ...``). At the outer
Skill layer the analogue is a Python file that declares either:

  * ``SKILL = SomeSkillSubclass(...)``    — single skill, or
  * ``SKILLS = [SomeSkill(...), Other(...)]`` — list

The module convention is explicit and side-effect-free at scan time —
no reflection, no subclass walking. A module without either symbol is
ignored.

Used by ``Supervisor.register_skills_from_path`` for runtime loading
(e.g. ``/load_dir <path>`` in the CLI), and could also back a
filesystem-watching auto-reloader in the future.
"""
from __future__ import annotations

import importlib.util
import logging
from pathlib import Path
from typing import Iterable, List

from Python.Src.Supervisor.skill import Skill

logger = logging.getLogger(__name__)


def discover_skills_from_path(
    directory: str | Path, recursive: bool = True
) -> List[Skill]:
    """Walk ``directory`` for ``.py`` files exporting ``SKILL`` / ``SKILLS``.

    Returns Skill instances in module-load order. Modules that fail to
    import are skipped with a warning rather than raised — one bad
    plugin shouldn't block the rest. Hidden / dunder filenames
    (``__init__.py``, ``_smoke.py``) are skipped.
    """
    root = Path(directory)
    if not root.exists():
        raise FileNotFoundError(f"directory does not exist: {directory}")
    if not root.is_dir():
        raise NotADirectoryError(f"not a directory: {directory}")

    pattern = "**/*.py" if recursive else "*.py"
    out: List[Skill] = []
    for py in sorted(root.glob(pattern)):
        if py.name.startswith("_"):
            continue
        out.extend(_load_module_skills(py))
    return out


def _load_module_skills(py_file: Path) -> List[Skill]:
    try:
        spec = importlib.util.spec_from_file_location(py_file.stem, py_file)
        if spec is None or spec.loader is None:
            logger.warning("cannot build module spec for %s", py_file)
            return []
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
    except Exception as e:  # noqa: BLE001
        logger.warning("failed to import %s: %s", py_file, e)
        return []

    found: List[Skill] = []
    if hasattr(module, "SKILL"):
        item = module.SKILL
        if _looks_like_skill(item):
            found.append(item)
        else:
            logger.warning(
                "%s exports SKILL but it has no card / run attribute", py_file
            )
    if hasattr(module, "SKILLS"):
        items = module.SKILLS
        if not isinstance(items, Iterable):
            logger.warning("%s SKILLS is not iterable, skipping", py_file)
        else:
            for item in items:
                if _looks_like_skill(item):
                    found.append(item)
                else:
                    logger.warning(
                        "%s SKILLS contains non-Skill item %r, skipping", py_file, item
                    )
    return found


def _looks_like_skill(obj: object) -> bool:
    """Duck-check for the Skill protocol — we don't use ``isinstance``
    because ``Skill`` is a ``runtime_checkable`` Protocol that only
    verifies attribute presence anyway, and importing it here would
    create a tighter circular-dep risk."""
    return hasattr(obj, "card") and hasattr(obj, "run") and hasattr(obj.card, "name")
