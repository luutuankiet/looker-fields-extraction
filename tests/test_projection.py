"""Unit tests for the manifest-driven projection layer.

Builds synthetic raw API responses, runs flatten_explore (which uses
project_field internally), and asserts each FieldRecord's column values.

Critical paths covered:
    * Direct attribute mapping (field.X -> record.X)
    * Renames (field.view -> record.view_name; field.field_group_label
      -> record.group_label; field.type -> record.field_type;
      explore.connection_name -> record.explore_connection)
    * Fallback chains (project_name: field -> explore)
    * Context injection (model_name from extraction loop, NOT from API)
    * Default values when API returns None
    * model_extra fallback for undocumented attrs (value_format_name)
    * Explicit False / 0 / [] kept (not falsy-coerced)
"""

from __future__ import annotations

from typing import Any

from looker_fields.extract import flatten_explore


def _make_raw_field(**overrides: Any) -> dict[str, Any]:
    base: dict[str, Any] = {
        "name": "users.email",
        "category": "dimension",
        "type": "string",
        "is_numeric": False,
        "is_timeframe": False,
        "is_fiscal": False,
        "is_filter": False,
        "dynamic": False,
        "label": "Users Email",
        "label_short": "Email",
        "description": "User email address",
        "view": "users",
        "view_label": "Users",
        "original_view": "users",
        "field_group_label": None,
        "hidden": False,
        "sql": "${TABLE}.email",
        "source_file": "views/users.view.lkml",
        "source_file_path": "default_project/views/users.view.lkml",
        "dimension_group": None,
        "scope": "users",
        "primary_key": False,
        "value_format": None,
        "value_format_name": None,
        "sortable": True,
        "can_filter": True,
        "suggest_dimension": "",
        "suggest_explore": "",
        "tags": [],
        "times_used": 0,
        "project_name": "default_project",
    }
    base.update(overrides)
    return base


def _make_raw_explore(**overrides: Any) -> dict[str, Any]:
    base: dict[str, Any] = {
        "name": "test_explore",
        "label": "Test Explore",
        "description": "synthetic fixture",
        "group_label": None,
        "hidden": False,
        "connection_name": "test_conn",
        "view_name": "users",
        "project_name": "default_project",
        "model_name": "WRONG_API_VALUE",
        "fields": {
            "dimensions": [],
            "measures": [],
            "filters": [],
            "parameters": [],
        },
    }
    base.update(overrides)
    return base


def _explore_with_one_dim(field_overrides: dict | None = None, **explore_overrides) -> dict:
    field = _make_raw_field(**(field_overrides or {}))
    return _make_raw_explore(
        fields={"dimensions": [field], "measures": [], "filters": [], "parameters": []},
        **explore_overrides,
    )


# --------------------------------------------------------------------------
# Context injection -- THE duplication fix
# --------------------------------------------------------------------------

def test_model_name_uses_context_not_api():
    raw = _explore_with_one_dim(model_name="WRONG_API_VALUE")
    records = flatten_explore(raw, model_name="correct_model")
    assert len(records) == 1
    assert records[0].model_name == "correct_model"


# --------------------------------------------------------------------------
# Renames
# --------------------------------------------------------------------------

def test_view_rename():
    raw = _explore_with_one_dim({"view": "customers"})
    records = flatten_explore(raw, model_name="m")
    assert records[0].view_name == "customers"


def test_field_type_rename():
    raw = _explore_with_one_dim({"type": "number"})
    records = flatten_explore(raw, model_name="m")
    assert records[0].field_type == "number"


def test_field_group_label_rename_with_none_default():
    raw = _explore_with_one_dim({"field_group_label": None})
    records = flatten_explore(raw, model_name="m")
    assert records[0].group_label == ""


def test_field_group_label_explicit_value():
    raw = _explore_with_one_dim({"field_group_label": "Demographics"})
    records = flatten_explore(raw, model_name="m")
    assert records[0].group_label == "Demographics"


def test_explore_connection_rename():
    raw = _explore_with_one_dim(connection_name="warehouse_prod")
    records = flatten_explore(raw, model_name="m")
    assert records[0].explore_connection == "warehouse_prod"


# --------------------------------------------------------------------------
# Fallback chains
# --------------------------------------------------------------------------

def test_project_name_fallback_to_explore_when_field_missing():
    field = _make_raw_field()
    del field["project_name"]
    raw = _make_raw_explore(
        project_name="explore_project",
        fields={"dimensions": [field], "measures": [], "filters": [], "parameters": []},
    )
    records = flatten_explore(raw, model_name="m")
    assert records[0].project_name == "explore_project"


def test_project_name_field_wins_when_present():
    raw = _explore_with_one_dim({"project_name": "field_project"}, project_name="explore_project")
    records = flatten_explore(raw, model_name="m")
    assert records[0].project_name == "field_project"


# --------------------------------------------------------------------------
# model_extra fallback (extra="allow")
# --------------------------------------------------------------------------

def test_value_format_name_picked_up_from_model_extra():
    """value_format_name isn't declared on LookmlModelExploreField; extra=allow stores it."""
    raw = _explore_with_one_dim({"value_format_name": "usd"})
    records = flatten_explore(raw, model_name="m")
    assert records[0].value_format_name == "usd"


# --------------------------------------------------------------------------
# Defaults
# --------------------------------------------------------------------------

def test_sortable_defaults_true_when_api_null():
    raw = _explore_with_one_dim({"sortable": None})
    records = flatten_explore(raw, model_name="m")
    assert records[0].sortable is True


def test_can_filter_defaults_true_when_api_null():
    raw = _explore_with_one_dim({"can_filter": None})
    records = flatten_explore(raw, model_name="m")
    assert records[0].can_filter is True


def test_explicit_sortable_false_kept():
    raw = _explore_with_one_dim({"sortable": False})
    records = flatten_explore(raw, model_name="m")
    assert records[0].sortable is False


def test_sql_nullable_preserved_as_none():
    raw = _explore_with_one_dim({"sql": None})
    records = flatten_explore(raw, model_name="m")
    assert records[0].sql is None


# --------------------------------------------------------------------------
# All fieldsets iterated
# --------------------------------------------------------------------------

def test_all_four_fieldsets_iterated():
    raw = _make_raw_explore(fields={
        "dimensions": [_make_raw_field(name="d1", category="dimension")],
        "measures": [_make_raw_field(name="m1", category="measure", type="count")],
        "filters": [_make_raw_field(name="f1", category="filter")],
        "parameters": [_make_raw_field(name="p1", category="parameter")],
    })
    records = flatten_explore(raw, model_name="m")
    assert len(records) == 4
    assert {r.field_name for r in records} == {"d1", "m1", "f1", "p1"}
    assert {r.category for r in records} == {"dimension", "measure", "filter", "parameter"}


def test_empty_fieldsets_returns_empty_list():
    raw = _make_raw_explore()
    records = flatten_explore(raw, model_name="m")
    assert records == []
