"""Pytest base classes for looker-extractor plugin conformance tests."""

from .contract import (
    PLUGIN_ENTRY_POINT_GROUP,
    BasePluginContract,
    assert_lineage_envelope,
)

__version__ = "0.1.0a0"
__all__ = [
    "BasePluginContract",
    "PLUGIN_ENTRY_POINT_GROUP",
    "assert_lineage_envelope",
]
