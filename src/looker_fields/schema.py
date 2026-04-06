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


def parse_swagger_explore_schema(swagger: dict[str, Any]) -> list[SwaggerFieldMapping]:
    """Extract field mappings from the Swagger spec for lookml_model_explore.

    Walks the Swagger JSON to find:
    1. The LookmlModelExplore definition
    2. The LookmlModelExploreFieldset definition
    3. The LookmlModelExploreField definition
    4. Maps each API field to our FieldRecord columns
    """
    # TODO: Implement swagger parsing
    raise NotImplementedError("Swagger parsing not yet implemented")


def validate_schema_drift(swagger: dict[str, Any], baseline: list[str]) -> list[str]:
    """Compare current Swagger fields against our baseline.

    Returns list of drift warnings (new fields, removed fields, type changes).
    """
    # TODO: Implement drift detection
    raise NotImplementedError("Drift detection not yet implemented")
