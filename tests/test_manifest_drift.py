"""Tests for the manifest-vs-swagger drift detector (v2)."""

from __future__ import annotations

import json
from importlib import resources

from looker_fields.manifest import ColumnSpec, ManifestSpec, load_manifest
from looker_fields.manifest.drift import validate_manifest_drift


def _swagger(field_props: list[str], explore_props: list[str]) -> dict:
    return {
        "components": {
            "schemas": {
                "LookmlModelExploreField": {
                    "properties": {p: {} for p in field_props},
                },
                "LookmlModelExplore": {
                    "properties": {p: {} for p in explore_props},
                },
            }
        }
    }


def _manifest(columns_data: list[dict]) -> ManifestSpec:
    return ManifestSpec(
        schema_version="1.0.0",
        entity="field",
        output_grain=["model_name"],
        columns=[ColumnSpec(**c) for c in columns_data],
    )


def test_clean_when_all_paths_exist():
    swagger = _swagger(field_props=["name", "type"], explore_props=["label"])
    manifest = _manifest([
        {"name": "field_name", "type": "str", "api_source": "field.name", "default": ""},
        {"name": "field_type", "type": "str", "api_source": "field.type", "default": ""},
        {"name": "explore_label", "type": "str", "api_source": "explore.label", "default": ""},
    ])
    assert validate_manifest_drift(manifest, swagger) == []


def test_warns_on_unknown_field_attr():
    swagger = _swagger(field_props=["name"], explore_props=[])
    manifest = _manifest([
        {"name": "wrong", "type": "str", "api_source": "field.nonexistent", "default": ""},
    ])
    warnings = validate_manifest_drift(manifest, swagger)
    assert len(warnings) == 1
    assert "nonexistent" in warnings[0]


def test_context_attr_known_passes():
    swagger = _swagger(field_props=[], explore_props=[])
    manifest = _manifest([
        {"name": "model_name", "type": "str", "api_source": "context.model_name", "default": ""},
    ])
    assert validate_manifest_drift(manifest, swagger) == []


def test_context_attr_unknown_warns():
    swagger = _swagger(field_props=[], explore_props=[])
    manifest = _manifest([
        {"name": "bad", "type": "str", "api_source": "context.bogus", "default": ""},
    ])
    warnings = validate_manifest_drift(manifest, swagger)
    assert any("bogus" in w for w in warnings)


def test_value_format_name_tolerated_via_known_extras():
    swagger = _swagger(field_props=["name"], explore_props=[])
    manifest = _manifest([
        {"name": "vfn", "type": "str", "api_source": "field.value_format_name", "default": ""},
    ])
    assert validate_manifest_drift(manifest, swagger) == []


def test_fallback_source_also_checked():
    swagger = _swagger(field_props=["name"], explore_props=[])
    manifest = _manifest([{
        "name": "proj",
        "type": "str",
        "api_source": "field.name",
        "fallback_source": "explore.bogus",
        "default": "",
    }])
    warnings = validate_manifest_drift(manifest, swagger)
    assert any("bogus" in w and "fallback" in w for w in warnings)


def test_bundled_manifest_drift_against_bundled_swagger():
    """Real-world drift check: bundled manifest must align with bundled swagger.

    If this fails, regenerate one or the other (scripts/regen_schema.py
    or scripts/parse_field_spec_to_manifest.py).
    """
    swagger_dir = resources.files("looker_fields._swagger")
    candidates = [f for f in swagger_dir.iterdir() if f.name.endswith(".json")]
    assert candidates, "no bundled swagger json found in _swagger/"
    swagger = json.loads(candidates[0].read_text())

    manifest = ManifestSpec.model_validate(load_manifest())
    warnings = validate_manifest_drift(manifest, swagger)
    assert warnings == [], "bundled manifest drift:\n  " + "\n  ".join(warnings)
