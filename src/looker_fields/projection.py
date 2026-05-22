"""Manifest-driven projection: typed API field -> typed FieldRecord output row.

Replaces the hand-rolled body of ``extract.flatten_field``. The manifest YAML
is the contract -- each column entry declares an ``api_source`` dotted-path
plus optional ``fallback_source`` and ``default``. This module walks the
manifest once per field, resolves each path against (typed_field,
typed_explore, context), and constructs a FieldRecord.

Three input sources:
    field    -- typed LookmlModelExploreField (per-field API attributes)
    explore  -- typed LookmlModelExplore (parent explore attributes)
    context  -- ExtractionContext (runtime-derived state: model_name, etc.)

Resolution gotchas the runtime handles:
    * None -> fallback -> default chain: the legacy ``field.get(...) or ''``
      pattern is preserved by treating None as "missing" (not as a valid
      value). Empty strings, 0, [], False are kept as explicit values.
      This divergence is intentional and safe: manifest defaults match
      legacy defaults on every column, so the only observable difference
      would be a column where the API returns an explicit empty value
      that the legacy code would have overwritten with the same empty
      default.
    * extra="allow" fallback: typed pydantic classes don't declare every
      undocumented API attribute (notably ``value_format_name`` is not on
      the swagger spec). ``_resolve`` falls back to ``model_extra`` when
      ``getattr`` returns None.

Manifest ``derived_columns`` are NOT iterated here -- pydantic
``default_factory`` (extracted_at, schema_version) and ``enrich_seen_in``
(post-collection aggregation) populate the remaining 7 FieldRecord fields.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from ._fieldrecord.types import FieldRecord
from ._swagger.types import LookmlModelExplore, LookmlModelExploreField
from .manifest import ManifestSpec


@dataclass(frozen=True)
class ExtractionContext:
    """Runtime-derived ground-truth values not in either typed object.

    Currently just ``model_name`` -- the extraction loop's iteration
    variable, which is THE ground truth for which model the explore was
    fetched under. The API response's nested ``explore.model_name`` is
    nullable per swagger and was the root cause of the duplication bug
    fixed during the manifest-native pivot.
    """

    model_name: str


def _resolve(
    dotted: str,
    field: LookmlModelExploreField,
    explore: LookmlModelExplore,
    context: ExtractionContext,
) -> Any:
    """Resolve a dotted manifest path like ``field.view`` or ``context.model_name``.

    Returns the raw resolved value (possibly None). Caller applies
    fallback chain + default.

    Resolution order for the leaf attribute (pydantic objects):
        1. ``getattr(obj, attr, None)`` -- declared pydantic attribute
        2. ``obj.model_extra.get(attr)`` -- undeclared API attribute
           caught by extra="allow" (e.g. value_format_name)
        3. None
    """
    head, _, attr = dotted.partition(".")
    if head == "context":
        # Dataclass -- no pydantic extras.
        return getattr(context, attr, None)
    if head == "field":
        obj: Any = field
    elif head == "explore":
        obj = explore
    else:
        raise ValueError(f"unknown manifest source {head!r} in {dotted!r}")

    val = getattr(obj, attr, None)
    if val is not None:
        return val

    extras = getattr(obj, "model_extra", None)
    if extras:
        return extras.get(attr)
    return None


def project_field(
    typed_field: LookmlModelExploreField,
    typed_explore: LookmlModelExplore,
    context: ExtractionContext,
    manifest: ManifestSpec,
) -> FieldRecord:
    """Project one typed API field into a FieldRecord per the manifest.

    Walks ``manifest.columns`` in order; for each column resolves
    ``api_source`` then ``fallback_source`` then ``default``. None
    values fall through to the next source; empty strings / 0 / False /
    [] are treated as explicit values (NOT falsy fallthrough).

    Derived columns (``manifest.derived_columns``) are NOT processed
    here. Pydantic ``default_factory`` handles runtime-generated values
    (extracted_at, schema_version); ``enrich_seen_in`` populates the
    seen-in family after collection.
    """
    record_data: dict[str, Any] = {}

    for col in manifest.columns:
        primary = _resolve(col.api_source, typed_field, typed_explore, context)
        if primary is not None:
            record_data[col.name] = primary
            continue

        if col.fallback_source:
            fallback = _resolve(
                col.fallback_source, typed_field, typed_explore, context
            )
            if fallback is not None:
                record_data[col.name] = fallback
                continue

        record_data[col.name] = col.default

    return FieldRecord(**record_data)
