"""Built-in Tools the Supervisor dispatches to.

Each module here defines a Tool class (``ToolCard`` + ``run``). They are
declared in ``Config/tools.yaml`` and instantiated by the loader; nothing
is auto-imported here to keep construction lazy and config-driven.
"""
