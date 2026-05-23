"""UsersPlugin — extract one row per Looker user.

Hits GET /api/4.0/users/search (paginated via limit/offset, default 500/page);
validates each response record through the plugin-owned swagger-generated
pydantic type (the tripwire); yields ``model_dump()`` dicts with a minimal
``_extract_user_*`` lineage envelope.

``users/search`` is preferred over ``users`` because /users returns ALL
credential sub-objects per record (heavy fan-out) whereas /users/search
accepts a ``fields=`` filter to project only the columns we want.
"""

from __future__ import annotations

from typing import Any, AsyncIterator

from looker_extractor_sdk import Plugin, stamp_lineage

from .swagger.types import User

# Default projection — identity + status + group/role linkage + email-credential
# metadata. Caller can override via filters["fields"].
DEFAULT_FIELDS = (
    "id,email,first_name,last_name,display_name,is_disabled,"
    "role_ids,group_ids,verified_looker_employee,credentials_email"
)

# Page size for /users/search; Looker caps at 5000 but 500 keeps bodies bounded.
DEFAULT_PAGE_SIZE = 500


class UsersPlugin(Plugin):
    """Passthru extractor for the Looker /api/4.0/users/search endpoint."""

    name = "users"
    version = "0.1.0a0"
    description = (
        "One row per Looker user; passthru shape from /api/4.0/users/search "
        "(User + embedded credentials_*), swagger-validated, paginated via "
        "limit/offset, with _extract_user_id / _extract_user_email lineage."
    )
    swagger_seeds = [
        "User",
        "CredentialsApi3",
        "CredentialsEmail",
        "CredentialsEmailSearch",
        "CredentialsEmbed",
        "CredentialsGoogle",
        "CredentialsLDAP",
        "CredentialsLookerOpenid",
        "CredentialsOIDC",
        "CredentialsSaml",
        "CredentialsTotp",
        "Error",
        "ValidationError",
    ]

    async def extract(
        self,
        client: Any,
        *,
        filters: dict[str, str] | None = None,
    ) -> AsyncIterator[dict[str, Any]]:
        # Paginate via /users/search with limit/offset. Stop on empty or short page.
        filters = filters or {}
        fields = filters.get("fields", DEFAULT_FIELDS)
        page_size = int(filters.get("limit", str(DEFAULT_PAGE_SIZE)))
        offset = int(filters.get("offset", "0"))

        while True:
            params: dict[str, Any] = {
                "fields": fields,
                "limit": page_size,
                "offset": offset,
            }
            raw_users = await client.get("users/search", params=params)
            if not raw_users:
                return
            for raw in raw_users:
                typed = User.model_validate(raw)
                row = typed.model_dump()
                stamp_lineage(
                    row,
                    user_id=str(typed.id) if typed.id is not None else None,
                    user_email=typed.email,
                )
                yield row
            if len(raw_users) < page_size:
                return
            offset += page_size
