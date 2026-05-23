"""Plugin registry: entry-points discovery + plugin lookup."""

from .discover import PLUGIN_ENTRY_POINT_GROUP, discover_plugins, get_plugin

__all__ = ["PLUGIN_ENTRY_POINT_GROUP", "discover_plugins", "get_plugin"]
