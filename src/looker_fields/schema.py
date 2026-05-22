"""Swagger discovery + FieldRecord re-export.

FieldRecord lives in ``_fieldrecord/types.py`` (generated from
``manifest/fields.yaml``). It is re-exported here so existing
``from .schema import FieldRecord`` imports across the codebase remain stable
(see cli.py, output.py, extract.py, verify.py).

The Swagger drift detector (SwaggerFieldMapping + REQUIRED_* +
parse_swagger_explore_schema + validate_schema_drift) remains in this module:
the manifest IS the *output* contract; the swagger machinery guards the
*input* contract (what the Looker API ships).
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from ._fieldrecord.types import FieldRecord

__all__ = [
    "FieldRecord",
    "SwaggerFieldMapping",
    "REQUIRED_FIELD_PROPERTIES",
    "REQUIRED_EXPLORE_PROPERTIES",
    "parse_swagger_explore_schema",
    "validate_schema_drift",
]


# ---------------------------------------------------------------------------
# Swagger schema discovery
# ---------------------------------------------------------------------------


class SwaggerFieldMapping(BaseModel):
    """Mapping from Swagger spec field to our output column."""

    api_path: str = Field(
        ..., description="Dot-path in API response (e.g., fields.dimensions[].name)"
    )
    output_column: str = Field(..., description="Our output column name")
    api_type: str = Field(..., description="Type from Swagger spec")
    required: bool = Field(False)


# ---------------------------------------------------------------------------
# Baseline: API paths our extractor (extract.flatten_field) depends on.
# Drift warnings fire when these go missing from a fresh swagger.
# Keep in sync with extract.flatten_field — these are the contract.
# ---------------------------------------------------------------------------

REQUIRED_FIELD_PROPERTIES: frozenset[str] = frozenset({
    "name", "type", "category", "label", "label_short",
    "description", "view", "view_label", "original_view",
    "sql", "source_file", "source_file_path",
    "dimension_group", "scope", "primary_key", "hidden",
    "value_format", "value_format_name", "sortable", "can_filter",
    "is_numeric", "is_fiscal", "is_timeframe", "is_filter",
    "suggest_dimension", "suggest_explore", "tags", "times_used",
    "group_label",
})
REQUIRED_EXPLORE_PROPERTIES: frozenset[str] = frozenset({
    "name", "project_name", "label", "description", "group_label",
    "hidden", "connection_name", "view_name", "fields",
})


def _spec_schemas(swagger: dict[str, Any]) -> dict[str, Any]:
    """Get the schemas dict whether the spec is OpenAPI 3 (components.schemas)
    or Swagger 2 (definitions). Bundled baseline is OpenAPI 3."""
    return (
        swagger.get("components", {}).get("schemas")
        or swagger.get("definitions")
        or {}
    )


def _swagger_type(prop: dict[str, Any]) -> str:
    """Best-effort type label from a Swagger/OAS property schema."""
    if "$ref" in prop:
        return prop["$ref"].split("/")[-1]
    t = prop.get("type", "unknown")
    if t == "array":
        items = prop.get("items", {}) or {}
        return f"array<{_swagger_type(items)}>"
    return t


def parse_swagger_explore_schema(swagger: dict[str, Any]) -> list[SwaggerFieldMapping]:
    """Enumerate every Explore/Fieldset/Field property promised by the spec.

    Returns a flat list — caller filters/compares as needed (see
    ``validate_schema_drift``). The output is THE source of truth for what the
    API ships; the mapping FROM these API paths TO our FieldRecord columns
    lives in ``extract.flatten_field``.
    """
    schemas = _spec_schemas(swagger)
    out: list[SwaggerFieldMapping] = []

    for kind, prefix in [
        ("LookmlModelExplore", "explore"),
        ("LookmlModelExploreFieldset", "explore.fields"),
        ("LookmlModelExploreField", "explore.fields.<category>[]"),
    ]:
        schema = schemas.get(kind, {})
        required = set(schema.get("required") or [])
        for name, prop in (schema.get("properties") or {}).items():
            out.append(
                SwaggerFieldMapping(
                    api_path=f"{prefix}.{name}",
                    output_column=name,
                    api_type=_swagger_type(prop),
                    required=name in required,
                )
            )
    return out


def validate_schema_drift(
    swagger: dict[str, Any],
    baseline: list[str] | None = None,
) -> list[str]:
    """Return human-readable drift warnings; empty list = clean.

    Compares the spec's LookmlModelExplore + LookmlModelExploreField properties
    against the hardcoded ``REQUIRED_*`` sets (the contract that
    ``extract.flatten_field`` relies on). Pass ``baseline`` to additionally
    require named paths (useful for project-specific extensions).
    """
    schemas = _spec_schemas(swagger)
    warnings: list[str] = []

    explore_props = set(
        (schemas.get("LookmlModelExplore", {}).get("properties") or {}).keys()
    )
    field_props = set(
        (schemas.get("LookmlModelExploreField", {}).get("properties") or {}).keys()
    )

    for req in sorted(REQUIRED_EXPLORE_PROPERTIES - explore_props):
        warnings.append(
            f"LookmlModelExplore: required property '{req}' missing from spec"
        )
    for req in sorted(REQUIRED_FIELD_PROPERTIES - field_props):
        warnings.append(
            f"LookmlModelExploreField: required property '{req}' missing from spec"
        )

    if baseline:
        for req in baseline:
            if req not in field_props and req not in explore_props:
                warnings.append(
                    f"baseline path '{req}' not found in either Explore or Field properties"
                )

    return warnings
