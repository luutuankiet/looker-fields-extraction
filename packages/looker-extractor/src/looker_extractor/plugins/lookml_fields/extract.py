"""Entity extraction -- pure passthru from swagger-typed API response to dict.

Post-pivot shape: orchestrate API calls, validate with the swagger-generated
pydantic type as a tripwire, and yield ``model_dump()`` dicts. NO projection,
NO enrichment, NO output-shape contract -- the swagger entity IS the shape.
The downstream warehouse handles flattening + dedup.

For Phase 1 the only entity wired up is ``explore_field`` (one field per row,
within the LookmlModelExploreFieldset within LookmlModelExplore). Phase 2
generalizes to per-entity dispatch (dashboards, looks, queries, etc.).
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any, AsyncIterator

from looker_extractor.core.client import LookerClient

from .swagger.types import LookmlModelExplore, LookmlModelExploreField

logger = logging.getLogger(__name__)


def flatten_explore_fields(
    explore: dict[str, Any],
    model_name: str,
) -> list[dict[str, Any]]:
    """Yield one passthru dict per field in the explore.

    Tripwire: validate via swagger-generated pydantic types so any API drift
    surfaces at extract time (rather than warehouse load time). After validate,
    ``model_dump`` emits the natural nested shape -- joins/aliases/enumerations
    as sub-dicts/arrays, not flattened columns.

    Each row carries a minimal lineage envelope (``_extract_*``) so the
    warehouse can join back without inspecting nested structures. Everything
    else is preserved as-is from the API.
    """
    typed_explore = LookmlModelExplore.model_validate(explore)
    fields_obj = explore.get("fields", {}) or {}

    out: list[dict[str, Any]] = []
    for field_kind in ("dimensions", "measures", "filters", "parameters"):
        category = field_kind[:-1]  # dimensions -> dimension
        for raw_field in fields_obj.get(field_kind, []):
            typed_field = LookmlModelExploreField.model_validate(raw_field)
            row = typed_field.model_dump()
            row["_extract_model_name"] = model_name
            row["_extract_explore_name"] = typed_explore.name
            row["_extract_explore_project_name"] = typed_explore.project_name
            row["_extract_field_category"] = category
            out.append(row)

    return out


async def extract_explore_fields(
    client: LookerClient,
    *,
    model_filter: str | None = None,
    explore_filter: str | None = None,
) -> AsyncIterator[dict[str, Any]]:
    """Stream passthru field dicts from all (or filtered) explores."""
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

    async def _fetch_one(model_name: str, explore_name: str) -> list[dict[str, Any]]:
        try:
            explore = await client.lookml_model_explore(model_name, explore_name)
            return flatten_explore_fields(explore, model_name)
        except Exception as exc:
            logger.error("Failed to extract %s::%s: %s", model_name, explore_name, exc)
            return []

    tasks = [_fetch_one(m, e) for m, e in pairs]
    for coro in asyncio.as_completed(tasks):
        rows = await coro
        for row in rows:
            yield row
