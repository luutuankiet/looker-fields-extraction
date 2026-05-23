"""Per-entity per-instance override manifest. No projection contract.

The manifest's ONLY responsibility post-pivot is to carry overrides on top
of the swagger-generated pydantic types:

  extra_fields    : name -> pydantic-type-str -- fields the swagger lacks but
                    a specific instance returns (caught at runtime via
                    extra=\"allow\"; documented here so they're visible and
                    can be widened in regenerated codegen).
  type_overrides  : name -> pydantic-type-str -- widen a swagger-declared type
                    when an instance returns values the swagger doesn't permit.

There is no projection, no derived columns, no output_grain. The output IS
the swagger entity's natural pydantic shape, dumped to JSON or Parquet.
The downstream warehouse handles flattening, derivation, and dedup.

Schema versioning: bump ``schema_version`` on breaking manifest-shape changes.
The loader does NOT migrate; out-of-version manifests are rejected by callers.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

CURRENT_SCHEMA_VERSION = "2.0"


class ManifestSpec(BaseModel):
    """Per-entity override manifest. Layered on top of swagger types."""

    model_config = ConfigDict(extra="allow")

    schema_version: str = Field(
        ...,
        description=f"Manifest schema version; current = {CURRENT_SCHEMA_VERSION}",
    )
    entity: str = Field(
        ...,
        description="Entity name this manifest scopes to (e.g. 'explore_field').",
    )
    extra_fields: dict[str, str] = Field(
        default_factory=dict,
        description=(
            "Field name -> pydantic type string for instance-specific fields "
            "the swagger lacks. Documented here so they survive codegen."
        ),
    )
    type_overrides: dict[str, str] = Field(
        default_factory=dict,
        description=(
            "Field name -> widened pydantic type string for instance-specific "
            "type drift (e.g. swagger says ``str``, instance returns ``int``)."
        ),
    )
