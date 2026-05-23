"""Plugin registry — entry-points discovery."""

from __future__ import annotations

from importlib.metadata import entry_points

from looker_extractor_sdk import Plugin

PLUGIN_ENTRY_POINT_GROUP = "looker_extractor.plugins"


def discover_plugins() -> dict[str, type[Plugin]]:
    """Walk the ``looker_extractor.plugins`` entry-points group.

    Returns name -> Plugin subclass (class, not instance — callers instantiate
    per-invocation so plugin state stays request-scoped).
    """
    found: dict[str, type[Plugin]] = {}
    for ep in entry_points(group=PLUGIN_ENTRY_POINT_GROUP):
        plugin_cls = ep.load()
        if not (isinstance(plugin_cls, type) and issubclass(plugin_cls, Plugin)):
            raise TypeError(
                f"Plugin {ep.name!r} (from {ep.value!r}) does not subclass "
                f"looker_extractor_sdk.Plugin"
            )
        found[ep.name] = plugin_cls
    return found


def get_plugin(name: str) -> type[Plugin]:
    """Look up a single plugin by name, raising ValueError if not found."""
    plugins = discover_plugins()
    if name not in plugins:
        available = ", ".join(sorted(plugins)) or "(none installed)"
        raise ValueError(f"Plugin {name!r} not found. Available: {available}")
    return plugins[name]
