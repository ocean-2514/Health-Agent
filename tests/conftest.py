"""Shared pytest configuration: add project root to sys.path so tests can
import `Python.Src.*` directly without package install."""
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))
