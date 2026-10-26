"""YAML-driven Tool loader.

Reads ``Config/tools.yaml``, imports each declared class, instantiates it
(optionally with ``init_kwargs``), validates it satisfies the ``Tool``
protocol, and returns the list. Borrowed in spirit from the earlier
``D:/code/AI/project/agent`` SupervisorAgent's ``register_from_config``,
trimmed to fit the Tool shape.

Disabled entries are skipped silently. A bad ``class_path`` raises loud so
mis-typed config fails immediately.

Default config location: ``<repo>/Config/tools.yaml`` (sibling of the
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

from Python.Src.Supervisor.tool import Tool

DEFAULT_TOOLS_YAML = Path(project_root) / "Config" / "tools.yaml"


class ToolLoadError(RuntimeError):
    """A declared tool failed to import / instantiate / validate."""


def _import_class(class_path: str) -> type:
    module_path, _, class_name = class_path.rpartition(".")
    if not module_path or not class_name:
        raise ToolLoadError(f"invalid class_path {class_path!r} (expected 'pkg.module.Class')")
    try:
        module = importlib.import_module(module_path)
    except Exception as e:
        raise ToolLoadError(f"failed to import module {module_path!r}: {e}") from e
    try:
        return getattr(module, class_name)
    except AttributeError as e:
        raise ToolLoadError(
            f"module {module_path!r} has no class {class_name!r}"
        ) from e


def load_tools(
    yaml_path: Optional[Path] = None,
    remote_yaml_path: Optional[Path] = None,
    include_remote: bool = True,
) -> List[Tool]:
    """Load local tools from YAML, plus (by default) remote A2A tools.

    Local tools come from ``Config/tools.yaml``; remote A2A tools come
    from ``Config/remote_tools.yaml`` (optional file — absent = no
    remotes, not an error). Both lists are concatenated and returned in
    one flat list; the Supervisor doesn't distinguish them once
    constructed.

    YAML shape (local)::

        tools:
          - name: transformer_diagnosis
            class_path: Python.Src.Supervisor.tools.transformer_diagnosis.TransformerDiagnosisTool
            enabled: true
            init_kwargs: {}      # optional, passed to the class constructor

    See ``Python.Src.Supervisor.remote.loader`` for the remote-tool YAML shape.
    """
    path = Path(yaml_path or DEFAULT_TOOLS_YAML)
    if not path.exists():
        raise ToolLoadError(f"tools config not found: {path}")

    with path.open("r", encoding="utf-8") as f:
        config = yaml.safe_load(f) or {}

    entries: List[Dict[str, Any]] = config.get("tools") or []
    if not entries:
        raise ToolLoadError(f"{path} contains no 'tools' entries")

    tools: List[Tool] = []
    for entry in entries:
        if not entry.get("enabled", True):
            continue
        class_path = entry.get("class_path")
        if not class_path:
            raise ToolLoadError(f"tools entry missing class_path: {entry}")

        cls = _import_class(class_path)
        init_kwargs: Dict[str, Any] = entry.get("init_kwargs") or {}
        try:
            tool = cls(**init_kwargs)
        except Exception as e:
            raise ToolLoadError(
                f"failed to instantiate {class_path}: {e}"
            ) from e

        if not (hasattr(tool, "card") and hasattr(tool, "run")):
            raise ToolLoadError(
                f"{class_path} does not satisfy Tool protocol (need card + run)"
            )
        tools.append(tool)

    if not tools:
        raise ToolLoadError(f"{path} declared no enabled tools")

    if include_remote:
        # Import lazily: avoids forcing httpx / a2a-sdk imports on callers
        # that only want local tools (e.g. unit tests for a single tool).
        from Python.Src.Supervisor.remote.loader import load_remote_tools

        tools.extend(load_remote_tools(yaml_path=remote_yaml_path))

    return tools
