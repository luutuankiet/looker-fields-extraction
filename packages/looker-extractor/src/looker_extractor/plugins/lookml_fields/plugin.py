"""LookmlFieldsPlugin — the reference plugin.

Wraps the existing ``extract_explore_fields`` + ``flatten_explore_fields``
functions as a Plugin subclass. Functions remain importable directly for
back-compat; the Plugin subclass is what the registry returns.
"""

from __future__ import annotations

from typing import Any, AsyncIterator

from looker_extractor_sdk import Plugin

from .extract import extract_explore_fields


class LookmlFieldsPlugin(Plugin):
    """Reference passthru extractor for the explore_field entity."""

    name = "lookml_fields"
    version = "0.3.0a0"
    description = (
        "One row per LookML explore field; passthru shape from "
        "LookmlModelExploreField (swagger-validated) with lineage envelope."
    )
    swagger_seeds = [
        "LookmlModelExplore",
        "LookmlModelExploreField",
        "LookmlModelExploreFieldset",
        "LookmlModelExploreJoins",
        "LookmlModelExploreAlwaysFilter",
        "LookmlModelExploreAccessFilter",
        "LookmlModelExploreConditionallyFilter",
        "LookmlModelExploreError",
        "LookmlModelNavExploreField",
        "LookmlModelExploreSupportedMeasureType",
        "Error",
        "ValidationError",
    ]

    async def extract(
        self,
        client: Any,
        *,
        filters: dict[str, str] | None = None,
    ) -> AsyncIterator[dict[str, Any]]:
        f = filters or {}
        async for row in extract_explore_fields(
            client,
            model_filter=f.get("model"),
            explore_filter=f.get("explore"),
        ):
            yield row
