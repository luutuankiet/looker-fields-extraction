"""Core field extraction logic."""

from __future__ import annotations

import asyncio
import logging
from collections import defaultdict
from typing import Any, AsyncIterator

from .client import LookerClient
from .schema import FieldRecord

logger = logging.getLogger(__name__)


def flatten_field(
    field: dict[str, Any],
    *,
    model_name: str,
    explore_name: str,
    project_name: str,
    explore_meta: dict[str, Any],
) -> FieldRecord:
    """Transform a single API field dict into a FieldRecord.

    Args:
        field: Raw field dict from API response (dimension, measure, filter, or parameter)
        model_name: The LookML model name
        explore_name: The explore name
        project_name: The project name
        explore_meta: Explore-level metadata (label, description, connection, etc)
    """
    return FieldRecord(
        project_name=project_name,
        model_name=model_name,
        explore_name=explore_name,
        field_name=field.get("name", ""),
        category=field.get("category", ""),
        field_type=field.get("type", ""),
        is_numeric=field.get("is_numeric", False),
        is_timeframe=field.get("is_timeframe", False),
        is_fiscal=field.get("is_fiscal", False),
        is_filter=field.get("is_filter", False),
        dynamic=field.get("dynamic", False),
        label=field.get("label", ""),
        label_short=field.get("label_short", ""),
        description=field.get("description", ""),
        view_name=field.get("view", ""),
        view_label=field.get("view_label", ""),
        original_view=field.get("original_view", ""),
        group_label=field.get("field_group_label") or "",
        hidden=field.get("hidden", False),
        sql=field.get("sql"),
        source_file=field.get("source_file", ""),
        source_file_path=field.get("source_file_path", ""),
        dimension_group=field.get("dimension_group"),
        scope=field.get("scope", ""),
        primary_key=field.get("primary_key", False),
        value_format=field.get("value_format"),
        value_format_name=field.get("value_format_name"),
        sortable=field.get("sortable", True),
        can_filter=field.get("can_filter", True),
        suggest_dimension=field.get("suggest_dimension", ""),
        suggest_explore=field.get("suggest_explore", ""),
        tags=field.get("tags", []),
        times_used=field.get("times_used", 0),
        explore_label=explore_meta.get("label", ""),
        explore_description=explore_meta.get("description"),
        explore_group_label=explore_meta.get("group_label"),
        explore_hidden=explore_meta.get("hidden", False),
        explore_connection=explore_meta.get("connection_name", ""),
        explore_view_name=explore_meta.get("view_name", ""),
    )


def flatten_explore(explore: dict[str, Any], model_name: str) -> list[FieldRecord]:
    """Flatten all fields from a single explore response into FieldRecords.

    Processes dimensions, measures, filters, and parameters from the
    explore's 'fields' object.
    """
    records: list[FieldRecord] = []
    project_name = explore.get("project_name", "")
    explore_name = explore.get("name", "")
    explore_meta = {
        "label": explore.get("label", ""),
        "description": explore.get("description"),
        "group_label": explore.get("group_label"),
        "hidden": explore.get("hidden", False),
        "connection_name": explore.get("connection_name", ""),
        "view_name": explore.get("view_name", ""),
    }

    fields_obj = explore.get("fields", {}) or {}
    for field_type in ("dimensions", "measures", "filters", "parameters"):
        for field in fields_obj.get(field_type, []):
            records.append(
                flatten_field(
                    field,
                    model_name=model_name,
                    explore_name=explore_name,
                    project_name=project_name,
                    explore_meta=explore_meta,
                )
            )

    return records


async def extract_all(
    client: LookerClient,
    *,
    model_filter: str | None = None,
    explore_filter: str | None = None,
) -> AsyncIterator[FieldRecord]:
    """Extract all fields from all models/explores, yielding FieldRecords.

    Args:
        client: Authenticated LookerClient
        model_filter: Optional model name filter
        explore_filter: Optional explore name filter

    Yields:
        FieldRecord for each field in each explore
    """
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
            return flatten_explore(explore, model_name)
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

    This answers: "Where is this field visible across the instance?"
    A field defined in users.view.lkml might be seen in 5 different explores
    across 3 models because those explores all join the users view.
    """
    from typing import Any

    # Phase 1: Aggregate by field_name
    agg: dict[str, dict[str, Any]] = defaultdict(
        lambda: {"models": set(), "explores": set(), "total_usage": 0}
    )

    for r in records:
        bucket = agg[r.field_name]
        bucket["models"].add(r.model_name)
        bucket["explores"].add(f"{r.model_name}::{r.explore_name}")
        bucket["total_usage"] += r.times_used

    # Phase 2: Stamp back onto each record
    for r in records:
        bucket = agg[r.field_name]
        r.seen_in_model_count = len(bucket["models"])
        r.seen_in_explore_count = len(bucket["explores"])
        r.total_times_used = bucket["total_usage"]
        r.seen_models = sorted(bucket["models"])
        r.seen_explores = sorted(bucket["explores"])

    logger.info(
        "Enriched %d records — %d unique field definitions",
        len(records),
        len(agg),
    )
    return records
