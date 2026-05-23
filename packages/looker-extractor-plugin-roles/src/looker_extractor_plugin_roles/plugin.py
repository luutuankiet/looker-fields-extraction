"""RolesPlugin — extract one row per Looker role.

Hits GET /api/4.0/roles (single call, no pagination); validates each response
record through the plugin-owned swagger-generated pydantic type (the tripwire);
yields ``model_dump()`` dicts with a minimal ``_extract_role_*`` lineage envelope.
"""

from __future__ import annotations

from typing import Any, AsyncIterator

from looker_extractor_sdk import Plugin, stamp_lineage

from .swagger.types import Role


class RolesPlugin(Plugin):
    """Passthru extractor for the Looker /api/4.0/roles endpoint."""

    name = "roles"
    version = "0.1.0a0"
    description = (
        "One row per Looker role; passthru shape from /api/4.0/roles "
        "(Role + nested permission_set + model_set), swagger-validated, "
        "with _extract_role_id / _extract_role_name lineage."
    )
    swagger_seeds = [
        "Role",
        "PermissionSet",
        "ModelSet",
        "Error",
        "ValidationError",
    ]

    async def extract(
        self,
        client: Any,
        *,
        filters: dict[str, str] | None = None,
    ) -> AsyncIterator[dict[str, Any]]:
        # Single API call, no pagination. Optional filter "ids" / "fields" supported.
        params: dict[str, Any] = {}
        if filters:
            if "ids" in filters:
                params["ids"] = filters["ids"]
            if "fields" in filters:
                params["fields"] = filters["fields"]

        raw_roles = await client.get("roles", params=params or None)

        for raw in raw_roles:
            typed = Role.model_validate(raw)
            row = typed.model_dump()
            stamp_lineage(
                row,
                role_id=str(typed.id) if typed.id is not None else None,
                role_name=typed.name,
            )
            yield row
