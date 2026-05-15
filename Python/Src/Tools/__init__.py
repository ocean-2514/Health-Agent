"""Pure tool functions for transformer condition monitoring.

Each module exposes deterministic, side-effect-free callables (or thin
stateless clients) that the FastAPI compatibility layer, the MCP server,
and the future Agent layer all consume. Tools never call the LLM directly
— LLM reasoning is added by callers (LegacyService / Coordinator agent).
"""
