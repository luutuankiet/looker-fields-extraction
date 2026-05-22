"""Drift detector v2 -- validates manifest aligns with live swagger.

Where ``schema.validate_schema_drift`` answers: *does the FRESH swagger
still expose the API paths our extractor's REQUIRED_*_PROPERTIES
contracts depend on?*

This module answers the complementary question: *does every ``api_source``
in our manifest still resolve against the live LookmlModelExplore /
LookmlModelExploreField swagger classes?*

Run by the ``refresh-schema`` CLI after pulling fresh swagger. Returns a
list of warning strings (non-fatal). Empty list = no drift.
"""

from __future__ import annotations

from typing import Any

from .schema import ManifestSpec

# Known undocumented API attributes the swagger doesn't declare but the
# API empirically returns. Caught via extra="allow" model_extra at
# runtime; tolerated here so drift detector doesn't false-positive.
KNOWN_API_EXTRAS: dict[str, frozenset[str]] = {
    "LookmlModelExploreField": frozenset({"value_format_name"}),
    "LookmlModelExplore": frozenset(),
}

# Manifest source-prefix -> swagger class name.
SOURCE_TO_CLASS: dict[str, str] = {
    "field": "LookmlModelExploreField",
    "explore": "LookmlModelExplore",
}

# Attributes the runtime ExtractionContext provides (not from API).
CONTEXT_ATTRS: frozenset[str] = frozenset({"model_name"})


def _extract_swagger_attrs(swagger: dict[str, Any], class_name: str) -> set[str]:
    """Property names declared on ``class_name`` in the swagger spec."""
    schemas = (swagger.get("components") or {}).get("schemas") or {}
    cls = schemas.get(class_name, {})
    return set((cls.get("properties") or {}).keys())


def _check_dotted_path(
    dotted: str,
    swagger_props: dict[str, set[str]],
) -> str | None:
    """Return a warning string if the dotted path is unresolvable, else None."""
    head, _, attr = dotted.partition(".")
    if head == "context":
        if attr not in CONTEXT_ATTRS:
            return (
                f"unknown context attr {attr!r} in {dotted!r} -- "
                f"ExtractionContext provides {sorted(CONTEXT_ATTRS)}"
            )
        return None
    cls = SOURCE_TO_CLASS.get(head)
    if cls is None:
        return f"unknown source prefix {head!r} in {dotted!r}"
    declared = swagger_props.get(cls, set())
    extras = KNOWN_API_EXTRAS.get(cls, frozenset())
    if attr in declared or attr in extras:
        return None
    return (
        f"{dotted!r}: {attr!r} not in swagger {cls!r} "
        f"(neither declared nor in known-extras)"
    )


def validate_manifest_drift(
    manifest: ManifestSpec,
    swagger: dict[str, Any],
) -> list[str]:
    """Walk manifest columns; flag any api_source / fallback_source the swagger lacks.

    Returns warnings; empty list means clean. Caller (CLI) prints them.
    """
    swagger_props: dict[str, set[str]] = {
        cls: _extract_swagger_attrs(swagger, cls) for cls in SOURCE_TO_CLASS.values()
    }

    warnings: list[str] = []
    for col in manifest.columns:
        if (w := _check_dotted_path(col.api_source, swagger_props)) is not None:
            warnings.append(f"column {col.name!r}: {w}")
        if col.fallback_source:
            if (w := _check_dotted_path(col.fallback_source, swagger_props)) is not None:
                warnings.append(f"column {col.name!r} fallback: {w}")
    return warnings


def suggest_manifest_additions(
    manifest: ManifestSpec,
    swagger: dict[str, Any],
) -> list[str]:
    """Return suggestions for swagger attrs not yet referenced by any manifest column.

    The complement to ``validate_manifest_drift``. Where the v2 detector
    surfaces *manifest-side* drift (paths the manifest claims that the
    swagger lacks), this surfaces *swagger-side* drift (attrs the swagger
    declares that the manifest ignores).

    Used by the ``refresh-manifest`` CLI to surface fields the user might
    want to add to their manifest after a Looker upgrade exposes new API
    attributes.

    Returns a list of ``<prefix>.<attr> -- ...`` strings; empty list = the
    manifest covers every declared swagger attr. Caller (CLI) prints them.
    """
    referenced: dict[str, set[str]] = {cls: set() for cls in SOURCE_TO_CLASS.values()}
    for col in manifest.columns:
        for src in (col.api_source, col.fallback_source):
            if not src:
                continue
            head, _, attr = src.partition(".")
            cls = SOURCE_TO_CLASS.get(head)
            if cls:
                referenced[cls].add(attr)

    swagger_props: dict[str, set[str]] = {
        cls: _extract_swagger_attrs(swagger, cls)
        for cls in SOURCE_TO_CLASS.values()
    }
    prefix_for_cls = {v: k for k, v in SOURCE_TO_CLASS.items()}

    suggestions: list[str] = []
    for cls, props in swagger_props.items():
        prefix = prefix_for_cls[cls]
        missing = sorted(props - referenced[cls])
        for attr in missing:
            suggestions.append(
                f"{prefix}.{attr} -- swagger declares but manifest does not reference"
            )
    return suggestions
