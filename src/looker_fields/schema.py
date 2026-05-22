"""Swagger discovery and Pydantic output models."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Optional

import orjson
from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# Output schema - the contract for extracted field data
# Grain: (project_name, model_name, explore_name, field_name) = unique row
# See docs/FIELD_SPEC.md for full mapping rationale
# ---------------------------------------------------------------------------


class FieldRecord(BaseModel):
    """One extracted field - the fundamental output row."""

    # === Identity (the unique grain) ===
    project_name: str = Field(..., description="LookML project name")
    model_name: str = Field(..., description="LookML model name")
    explore_name: str = Field(..., description="Explore name")
    field_name: str = Field(..., description="Fully-qualified field name (view.field)")

    # === Classification ===
    category: str = Field(..., description="dimension, measure, filter, or parameter")
    field_type: str = Field(..., description="LookML type (string, number, count, date_date, etc)")
    is_numeric: bool = Field(False)
    is_timeframe: bool = Field(False)
    is_fiscal: bool = Field(False)
    is_filter: bool = Field(False)
    dynamic: bool = Field(False, description="True if from dynamic_fields, not the model")

    # === Display ===
    label: str = Field("", description="Fully-qualified human-readable label")
    label_short: str = Field("", description="Label without view prefix")
    description: str = Field("")
    view_name: str = Field("", description="View this field belongs to")
    view_label: str = Field("")
    original_view: str = Field("", description="Where actually defined (differs with from:)")
    group_label: str = Field("", description="Field group label for UI grouping")
    hidden: bool = Field(False)

    # === LookML source ===
    sql: Optional[str] = Field(None, description="SQL expression (requires see_lookml perm)")
    source_file: str = Field("")
    source_file_path: str = Field("")
    dimension_group: Optional[str] = Field(None, description="Dimension group name if member")
    scope: str = Field("")
    primary_key: bool = Field(False)

    # === Formatting ===
    value_format: Optional[str] = Field(None)
    value_format_name: Optional[str] = Field(None)
    sortable: bool = Field(True)
    can_filter: bool = Field(True)

    # === Suggestions ===
    suggest_dimension: str = Field("")
    suggest_explore: str = Field("")
    tags: list[str] = Field(default_factory=list)

    # === Usage ===
    times_used: int = Field(0)

    # === Seen-in enrichment (computed post-extraction) ===
    # Groups by field_name across all models/explores to answer:
    # "Where is this field visible across the instance?"
    seen_in_model_count: int = Field(0, description="Distinct models this field appears in")
    seen_in_explore_count: int = Field(0, description="Distinct explores this field appears in")
    total_times_used: int = Field(0, description="Sum of times_used across all appearances")
    seen_models: list[str] = Field(default_factory=list, description="Model names where visible")
    seen_explores: list[str] = Field(
        default_factory=list, description="model::explore pairs where visible"
    )

    # === Explore context (denormalized for flat output) ===
    explore_label: str = Field("")
    explore_description: Optional[str] = Field(None)
    explore_group_label: Optional[str] = Field(None)
    explore_hidden: bool = Field(False)
    explore_connection: str = Field("")
    explore_view_name: str = Field("", description="Base view of the explore")

    # === Extraction metadata ===
    extracted_at: str = Field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat(),
        description="ISO timestamp of extraction",
    )
    schema_version: str = Field("1.1.0", description="Output schema version")

    def to_jsonl(self) -> bytes:
        """Serialize to a JSONL-ready bytes line."""
        return orjson.dumps(self.model_dump(), option=orjson.OPT_APPEND_NEWLINE)


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
