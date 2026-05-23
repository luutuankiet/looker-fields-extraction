"""Pin entry_points-based plugin discovery + in-tree lookml_fields visibility."""

import pytest

from looker_extractor.plugins.lookml_fields.plugin import LookmlFieldsPlugin
from looker_extractor.registry import discover_plugins, get_plugin


def test_lookml_fields_discovered() -> None:
    found = discover_plugins()
    assert "lookml_fields" in found
    assert found["lookml_fields"] is LookmlFieldsPlugin


def test_lookml_fields_class_attrs() -> None:
    cls = get_plugin("lookml_fields")
    assert cls.name == "lookml_fields"
    assert cls.version == "0.3.0a0"
    assert cls.description.startswith("One row per LookML explore field")
    assert "LookmlModelExplore" in cls.swagger_seeds
    assert len(cls.swagger_seeds) == 12


def test_missing_plugin_raises() -> None:
    with pytest.raises(ValueError, match="not found"):
        get_plugin("nonexistent_plugin")


def test_get_plugin_lists_available_in_error() -> None:
    with pytest.raises(ValueError, match="lookml_fields"):
        get_plugin("definitely_not_a_plugin")
