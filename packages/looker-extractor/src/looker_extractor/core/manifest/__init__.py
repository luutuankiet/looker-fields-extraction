"""Manifest package -- per-entity per-instance override layer.

Post-pivot, the manifest's job is narrow: carry instance-specific overrides
on top of the swagger-generated pydantic types. No projection, no derived
columns, no output_grain -- those concerns moved downstream to the warehouse.

Public surface:
    load_manifest(cli_override) -> dict       -- resolve and load the manifest YAML
    resolve_manifest_source(cli_override)     -- describe where it came from
    user_config_path() -> Path                -- XDG location for user-managed override
    write_user_config(spec) -> Path           -- persist a manifest to the XDG location
    ManifestSpec                              -- pydantic validator for the YAML structure
    CURRENT_SCHEMA_VERSION                    -- current manifest schema version

Resolution chain: CLI > env > XDG > bundled.
"""

from __future__ import annotations

from .loader import (
    ManifestSource,
    ManifestSourceKind,
    load_manifest,
    resolve_manifest_source,
    user_config_path,
    write_user_config,
)
from .schema import (
    CURRENT_SCHEMA_VERSION,
    ManifestSpec,
)

__all__ = [
    "CURRENT_SCHEMA_VERSION",
    "ManifestSource",
    "ManifestSourceKind",
    "ManifestSpec",
    "load_manifest",
    "resolve_manifest_source",
    "user_config_path",
    "write_user_config",
]
