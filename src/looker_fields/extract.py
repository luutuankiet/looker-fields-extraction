"""Core field extraction logic -- orchestrates per-field projection.

``flatten_field`` has been removed in the manifest-native pivot.
``flatten_explore`` now validates the raw API response through
``LookmlModelExplore`` + ``LookmlModelExploreField`` (the input tripwire)
and projects each field via ``projection.project_field`` using the
manifest as the contract.
"""

from __future__ import annotations

import asyncio
import hashlib
import logging
from collections import defaultdict
from typing import Any, AsyncIterator

from ._swagger.types import LookmlModelExplore, LookmlModelExploreField
from .client import LookerClient
from .manifest import ManifestSpec, load_manifest
from .projection import ExtractionContext, project_field
from .schema import FieldRecord

logger = logging.getLogger(__name__)


def flatten_explore(
    explore: dict[str, Any],
    model_name: str,
    manifest: ManifestSpec | None = None,
) -> list[FieldRecord]:
    """Flatten all fields from a single explore response into FieldRecords.

    Validates the explore + each field through the typed pydantic classes
    (input tripwire -- raises ValidationError on API drift). Projects
    each typed field into a FieldRecord via the manifest.

    Args:
        explore: Raw explore dict from LookerClient.lookml_model_explore.
        model_name: Model name (extraction-loop ground truth -- the
            duplication-bug fix; ``explore.model_name`` from the API is
            unreliable per swagger nullability).
        manifest: Optional pre-loaded ManifestSpec. Falls back to bundled
            default load when None -- keeps callers like ``verify.py``
            single-shot-friendly without threading manifest through every
            layer.
    """
    if manifest is None:
        manifest = ManifestSpec.model_validate(load_manifest())

    typed_explore = LookmlModelExplore.model_validate(explore)
    context = ExtractionContext(model_name=model_name)

    records: list[FieldRecord] = []
    seen_field_names: set[str] = set()
    fields_obj = explore.get("fields", {}) or {}
    for field_kind in ("dimensions", "measures", "filters", "parameters"):
        for raw_field in fields_obj.get(field_kind, []):
            typed_field = LookmlModelExploreField.model_validate(raw_field)
            record = project_field(typed_field, typed_explore, context, manifest)
            if record.field_name in seen_field_names:
                raise ValueError(
                    f"Grain violation: field_name {record.field_name!r} appeared "
                    f"twice within explore {model_name}::{typed_explore.name!r}. "
                    "Looker's LookML validator prevents duplicate field names within "
                    "an explore at definition time; this indicates an API anomaly. "
                    "If reproducible, please file an issue with the raw explore JSON."
                )
            seen_field_names.add(record.field_name)
            records.append(record)

    return records


async def extract_all(
    client: LookerClient,
    *,
    model_filter: str | None = None,
    explore_filter: str | None = None,
    manifest: ManifestSpec | None = None,
) -> AsyncIterator[FieldRecord]:
    """Extract all fields from all models/explores, yielding FieldRecords.

    Loads the manifest once at entry, then threads the typed spec down
    so each per-explore flatten skips re-load + re-validation.

    Args:
        client: Authenticated LookerClient.
        model_filter: Optional model name filter.
        explore_filter: Optional explore name filter.
        manifest: Optional pre-loaded ManifestSpec (default: bundled load).

    Yields:
        FieldRecord for each field in each explore.
    """
    if manifest is None:
        manifest = ManifestSpec.model_validate(load_manifest())

    models = await client.all_lookml_models()

    pairs: list[tuple[str, str]] = []
    for model in models:
        mname = model.get("name", "")
        if model_filter and mname != model_filter:
            continue
        for explore in model.get("explores", []):
            ename = explore.get("name", "")
            if explore_filter and ename != explore_filter:
                continue
            pairs.append((mname, ename))

    logger.info("Extracting fields from %d model::explore pairs", len(pairs))

    async def _fetch_one(model_name: str, explore_name: str) -> list[FieldRecord]:
        try:
            explore = await client.lookml_model_explore(model_name, explore_name)
            return flatten_explore(explore, model_name, manifest)
        except Exception as exc:
            logger.error("Failed to extract %s::%s: %s", model_name, explore_name, exc)
            return []

    tasks = [_fetch_one(m, e) for m, e in pairs]
    for coro in asyncio.as_completed(tasks):
        records = await coro
        for record in records:
            yield record


def _compute_definition_hash(record: FieldRecord) -> str:
    """Stable content hash per row for cross-row identity.

    Hashes the canonical tuple:
        (original_view, leaf_name, normalized_sql, sorted(tags),
         dimension_group, primary_key, field_type)

    Whitespace-normalized sql so cosmetic formatting drift doesn't split
    semantically-identical definitions. Dynamic fields (query-scoped) get
    an empty hash since they have no stable identity across queries.
    """
    if record.dynamic:
        return ""

    leaf_name = record.field_name.split(".", 1)[-1] if record.field_name else ""
    sql_normalized = " ".join((record.sql or "").split())
    tags_sorted = sorted(record.tags or [])
    canonical = "|".join([
        record.original_view or "",
        leaf_name,
        sql_normalized,
        ",".join(tags_sorted),
        record.dimension_group or "",
        str(bool(record.primary_key)),
        record.field_type or "",
    ])
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def enrich_seen_in(records: list[FieldRecord]) -> list[FieldRecord]:
    """Enrich records with seen-in + definition aggregation.

    Two independent aggregation passes:

    1. ``seen_in_*`` family (logical identity, keyed by ``field_name`` alone)
       For each field_name, counts distinct models / explores / total usage.
       Answers "where is this field-name visible across the instance?"
       Skips rows where ``dynamic=True`` (query-scoped, no stable identity).

    2. ``definition_*`` family (content + lineage identity)
       - ``definition_hash`` per row: sha256 of canonical content tuple
       - ``definition_variant_count``: distinct hashes per ``field_name``
         (high N = refinement-driven drift surfaced in the API responses)
       - ``definition_appearances_count``: distinct ``(model, explore)`` per
         ``(original_view, leaf_name)``. Merges across ``from:`` join
         aliases that ``seen_in_*`` (field_name-keyed) keeps separate.

    Mutates records in place via setattr on declared FieldRecord fields.
    ``extra="forbid"`` only blocks undeclared attributes; reassigning
    declared fields is allowed.
    """
    # Pass 1: seen_in_* (field_name-keyed, excludes dynamic)
    agg: dict[str, dict[str, Any]] = defaultdict(
        lambda: {"models": set(), "explores": set(), "total_usage": 0}
    )

    for r in records:
        if r.dynamic:
            continue
        bucket = agg[r.field_name]
        bucket["models"].add(r.model_name)
        bucket["explores"].add(f"{r.model_name}::{r.explore_name}")
        bucket["total_usage"] += r.times_used

    for r in records:
        if r.dynamic:
            r.seen_in_model_count = 0
            r.seen_in_explore_count = 0
            r.total_times_used = 0
            r.seen_models = []
            r.seen_explores = []
        else:
            bucket = agg[r.field_name]
            r.seen_in_model_count = len(bucket["models"])
            r.seen_in_explore_count = len(bucket["explores"])
            r.total_times_used = bucket["total_usage"]
            r.seen_models = sorted(bucket["models"])
            r.seen_explores = sorted(bucket["explores"])

    # Pass 2: definition_* (content + lineage identity)
    for r in records:
        r.definition_hash = _compute_definition_hash(r)

    variant_agg: dict[str, set[str]] = defaultdict(set)
    for r in records:
        if r.dynamic:
            continue
        variant_agg[r.field_name].add(r.definition_hash)

    appearance_agg: dict[tuple[str, str], set[str]] = defaultdict(set)
    for r in records:
        if r.dynamic:
            continue
        leaf_name = r.field_name.split(".", 1)[-1] if r.field_name else ""
        key = (r.original_view or "", leaf_name)
        appearance_agg[key].add(f"{r.model_name}::{r.explore_name}")

    for r in records:
        if r.dynamic:
            r.definition_variant_count = 0
            r.definition_appearances_count = 0
        else:
            r.definition_variant_count = len(variant_agg[r.field_name])
            leaf_name = r.field_name.split(".", 1)[-1] if r.field_name else ""
            key = (r.original_view or "", leaf_name)
            r.definition_appearances_count = len(appearance_agg[key])

    logger.info(
        "Enriched %d records -- %d distinct field_names; %d distinct (original_view, leaf) keys",
        len(records),
        len(agg),
        len(appearance_agg),
    )
    return records
