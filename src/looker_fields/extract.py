"""Core field extraction logic -- orchestrates per-field projection.

``flatten_field`` has been removed in the manifest-native pivot.
``flatten_explore`` now validates the raw API response through
``LookmlModelExplore`` + ``LookmlModelExploreField`` (the input tripwire)
and projects each field via ``projection.project_field`` using the
manifest as the contract.
"""

from __future__ import annotations

import asyncio
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
    fields_obj = explore.get("fields", {}) or {}
    for field_kind in ("dimensions", "measures", "filters", "parameters"):
        for raw_field in fields_obj.get(field_kind, []):
            typed_field = LookmlModelExploreField.model_validate(raw_field)
            records.append(
                project_field(typed_field, typed_explore, context, manifest)
            )

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


def enrich_seen_in(records: list[FieldRecord]) -> list[FieldRecord]:
    """Enrich records with seen-in aggregation.

    For each unique field_name, computes:
    - How many distinct models it appears in
    - How many distinct explores it appears in
    - Total times_used across all appearances
    - List of models and model::explore pairs

    Answers: "Where is this field visible across the instance?" A field
    defined in users.view.lkml might be seen in 5 different explores
    across 3 models because those explores all join the users view.

    Mutates records in place via setattr on declared FieldRecord fields
    (the seen-in family). ``extra="forbid"`` only blocks undeclared
    attributes; reassigning declared fields is allowed.
    """
    agg: dict[str, dict[str, Any]] = defaultdict(
        lambda: {"models": set(), "explores": set(), "total_usage": 0}
    )

    for r in records:
        bucket = agg[r.field_name]
        bucket["models"].add(r.model_name)
        bucket["explores"].add(f"{r.model_name}::{r.explore_name}")
        bucket["total_usage"] += r.times_used

    for r in records:
        bucket = agg[r.field_name]
        r.seen_in_model_count = len(bucket["models"])
        r.seen_in_explore_count = len(bucket["explores"])
        r.total_times_used = bucket["total_usage"]
        r.seen_models = sorted(bucket["models"])
        r.seen_explores = sorted(bucket["explores"])

    logger.info(
        "Enriched %d records -- %d unique field definitions",
        len(records),
        len(agg),
    )
    return records
