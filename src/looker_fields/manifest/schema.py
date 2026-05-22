"""Pydantic schema for the manifest YAML — validates structure at load time.

Use case: catch malformed user overrides early with a typed ValidationError
instead of a runtime KeyError deep in the projection layer (Phase 6).

The schema is intentionally permissive:
    * Forward-compat: top-level ``extra=\"allow\"`` accepts new sections
      (e.g. future ``enrichments:`` key) without code changes here.
    * Per-row ``extra=\"allow\"`` lets users add custom keys for plugin
      metadata (e.g. ``bq_type:`` for the future BigQuery sink).

The strict surface is the REQUIRED fields. Everything else floats.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict


class ColumnSpec(BaseModel):
    """One direct-API column in the manifest."""

    model_config = ConfigDict(extra="allow")

    name: str
    type: str
    api_source: str
    fallback_source: str | None = None
    default: Any = None
    description: str = ""


class DerivedColumnSpec(BaseModel):
    """One derived column (generated, hardcoded, or post-extraction enrichment)."""

    model_config = ConfigDict(extra="allow")

    name: str
    type: str
    expression: str
    deterministic: bool = False
    source_section: str = ""
    description: str = ""


class ManifestSpec(BaseModel):
    """Top-level manifest structure. Validates ``fields.yaml`` at load time."""

    model_config = ConfigDict(extra="allow")

    schema_version: str
    entity: str
    output_grain: list[str]
    columns: list[ColumnSpec]
    derived_columns: list[DerivedColumnSpec] = []
    exclusions: list[str] = []
