"""Plugin Protocol/ABC — what plugin authors implement."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, AsyncIterator, ClassVar


class Plugin(ABC):
    """Base class for looker-extractor plugins.

    Subclass and set class attributes ``name``, ``version``, ``swagger_seeds``,
    then implement ``extract()``. Register via entry-points group
    ``looker_extractor.plugins`` in your pyproject.toml::

        [project.entry-points."looker_extractor.plugins"]
        my_plugin = "my_pkg.plugin:MyPlugin"
    """

    name: ClassVar[str] = ""
    version: ClassVar[str] = ""
    description: ClassVar[str] = ""
    swagger_seeds: ClassVar[list[str]] = []

    @abstractmethod
    async def extract(
        self,
        client: Any,
        *,
        filters: dict[str, str] | None = None,
    ) -> AsyncIterator[dict[str, Any]]:
        """Yield one passthru dict per record.

        Validate API response through plugin's own swagger-generated pydantic
        types (the tripwire), yield ``model_dump()`` dicts. Each record should
        carry a minimal ``_extract_*`` lineage envelope (use ``stamp_lineage``).
        """
        if False:  # pragma: no cover
            yield {}


def stamp_lineage(record: dict[str, Any], **kwargs: Any) -> dict[str, Any]:
    """Stamp ``_extract_*`` lineage keys into a record (in-place + returned)."""
    for k, v in kwargs.items():
        record[f"_extract_{k}"] = v
    return record
