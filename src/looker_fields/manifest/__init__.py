"""Manifest package — declarative source of truth for the FieldRecord output contract.

Public surface:
    load_manifest(cli_override) -> dict       — resolve and load the manifest YAML
    resolve_manifest_source(cli_override)     — describe where it came from
    user_config_path() -> Path                — XDG location for user-managed override
    write_user_config(spec) -> Path           — persist a manifest to the XDG location
    ManifestSpec                              — pydantic validator for the YAML structure

Architecture layers:
    loader.py     — 4-step resolution chain: CLI > env > XDG > bundled
    schema.py     — ManifestSpec pydantic model, validates YAML at load
    fields.yaml   — BUNDLED DEFAULT manifest (generated from docs/FIELD_SPEC.md)
    projection.py — (Phase 6) runtime mapper: typed_field + manifest → FieldRecord

User overrides via ``~/.config/looker-fields/manifest.yaml`` or
``LOOKER_FIELDS_MANIFEST`` env. CLI flag ``--manifest-path`` wins all.
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
from .drift import (
    KNOWN_API_EXTRAS,
    suggest_manifest_additions,
    validate_manifest_drift,
)
from .schema import (
    ColumnSpec,
    DerivedColumnSpec,
    ManifestSpec,
)

__all__ = [
    "ColumnSpec",
    "DerivedColumnSpec",
    "KNOWN_API_EXTRAS",
    "ManifestSource",
    "ManifestSourceKind",
    "ManifestSpec",
    "load_manifest",
    "resolve_manifest_source",
    "suggest_manifest_additions",
    "user_config_path",
    "validate_manifest_drift",
    "write_user_config",
]
