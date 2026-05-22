"""Generated FieldRecord - DO NOT EDIT.

Regenerate via: .venv/bin/python scripts/regen_fieldrecord.py
           or: looker-fields regen-types (writes to XDG cache)
Source:         src/looker_fields/manifest/fields.yaml

The manifest is the contract; this file projects it into a typed
Pydantic v2 BaseModel for downstream consumers (cli, output, verify).
"""

from __future__ import annotations

from datetime import datetime, timezone

import orjson
from pydantic import BaseModel, ConfigDict, Field


class FieldRecord(BaseModel):
    """One extracted field - the fundamental output row.

    Grain: (project_name, model_name, explore_name, field_name) = unique row.
    Generated from manifest/fields.yaml; do not hand-edit.
    """

    model_config = ConfigDict(extra="forbid")

    project_name: str = Field(..., description='Field-level preferred; falls back to explore-level')
    model_name: str = Field(..., description='Always from explore context — THE fix for duplication')
    explore_name: str = Field(..., description='Explore name within the model')
    field_name: str = Field(..., description='Fully-qualified: `view_name.field_name` (e.g., `order_items.total_revenue`)')
    category: str = Field(..., description='`"dimension"`, `"measure"`, `"filter"`, `"parameter"` — more reliable than array membership')
    field_type: str = Field(..., description='LookML type: `string`, `number`, `yesno`, `date_date`, `date_month`, `count`, `sum`, `average`, etc.')
    is_numeric: bool = Field(False, description='True for numeric types')
    is_timeframe: bool = Field(False, description='True for date/time types — dim group members have this set')
    is_fiscal: bool = Field(False, description='True for fiscal calendar variants')
    is_filter: bool = Field(False, description='True for filter-only fields')
    dynamic: bool = Field(False, description='True if created via `dynamic_fields`, not in the LookML model')
    label: str = Field('', description='Fully-qualified: includes view label (e.g., `"Order Items Total Revenue"`)')
    label_short: str = Field('', description='Without view prefix (e.g., `"Total Revenue"`)')
    description: str = Field('', description='LookML `description` parameter; empty string if unset')
    view_name: str = Field('', description='View this field appears under (may be join alias)')
    view_label: str = Field('', description='Human-readable view label for UI grouping')
    original_view: str = Field('', description='Where field is actually defined — differs from `view` when `from:` join alias is used')
    group_label: str = Field('', description='UI field group label; null mapped to empty string')
    hidden: bool = Field(False, description='True if hidden from explore UI (still extracted)')
    sql: str | None = Field(None, description='SQL expression from LookML (e.g., `${TABLE}.date`). **Requires `see_lookml` permission** — null without it')
    source_file: str = Field('', description='Relative file path (e.g., `views/order_items.view.lkml`)')
    source_file_path: str = Field('', description='Fully-qualified path: `project_name/views/file.lkml`')
    dimension_group: str | None = Field(None, description='Group name if this field is a dimension group member (e.g., `order_items.created`). Null for non-grouped fields')
    scope: str = Field('', description='LookML scope, typically the view name')
    primary_key: bool = Field(False, description='True if declared as `primary_key: yes`')
    value_format: str | None = Field(None, description='Explicit LookML `value_format` string')
    value_format_name: str | None = Field(None, description='Named format (e.g., `decimal_2`, `usd`)')
    sortable: bool = Field(True, description='Whether field can be sorted in queries')
    can_filter: bool = Field(True, description='Whether field can be used in filters')
    suggest_dimension: str = Field('', description='Dimension used for suggest queries')
    suggest_explore: str = Field('', description='Explore used for suggest queries')
    tags: list[str] = Field(default_factory=list, description='Arbitrary string tags from LookML `tags` parameter. Serialized as JSON array in JSONL/CSV')
    times_used: int = Field(0, description='Count of query usage. Valuable for identifying dead fields')
    explore_label: str = Field('', description='Human-readable explore label')
    explore_description: str | None = Field(None, description='Explore description; null if unset')
    explore_group_label: str | None = Field(None, description='Navigation menu grouping')
    explore_hidden: bool = Field(False, description='Whether explore is hidden in nav')
    explore_connection: str = Field('', description='Database connection name')
    explore_view_name: str = Field('', description='Base view of the explore')

    extracted_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat(), description='ISO 8601 UTC timestamp of extraction')
    schema_version: str = Field("1.1.0", description='`"1.1.0"` — incremented on breaking changes')
    seen_in_model_count: int = Field(0, description='1 = single model, >1 = shared across models')
    seen_in_explore_count: int = Field(0, description='How many explores expose this field')
    total_times_used: int = Field(0, description='Aggregate usage across all appearances')
    seen_models: list[str] = Field(default_factory=list, description='JSON array of model names')
    seen_explores: list[str] = Field(default_factory=list, description='JSON array of "model::explore" strings')
    definition_hash: str = Field('', description='Content fingerprint per row. Identical hashes = identical definition. Empty string for `dynamic=true` fields (query-scoped, no stable identity).')
    definition_variant_count: int = Field(0, description='`1` = uniformly defined everywhere; `>1` = refinement-driven drift to investigate.')
    definition_appearances_count: int = Field(0, description='Cross-alias lineage count — merges across `from:` join aliases that `seen_in_*` (field_name-keyed) keeps separate.')

    def to_jsonl(self) -> bytes:
        """Serialize to a JSONL-ready bytes line."""
        return orjson.dumps(self.model_dump(), option=orjson.OPT_APPEND_NEWLINE)
