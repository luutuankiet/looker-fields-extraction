"""Conformance: UsersPlugin meets the SDK contract.

Inherits 9 generic conformance tests from BasePluginContract
(looker-extractor-tests-plugin) via plugin_class binding. Adds plugin-specific
assertions for endpoint, lineage envelope, and pagination loop termination.
"""

from __future__ import annotations

from typing import Any

import pytest
from looker_extractor_tests_plugin import BasePluginContract, assert_lineage_envelope

from looker_extractor_plugin_users.plugin import UsersPlugin


USER_FIXTURE_PAGE_1 = [
    {
        "id": "100",
        "email": "alice@example.com",
        "first_name": "Alice",
        "last_name": "Anderson",
        "is_disabled": False,
        "role_ids": ["1", "2"],
        "group_ids": ["10"],
        "verified_looker_employee": True,
    },
    {
        "id": "101",
        "email": "bob@example.com",
        "first_name": "Bob",
        "last_name": "Brown",
        "is_disabled": True,
        "role_ids": ["3"],
        "group_ids": ["20", "21"],
        "verified_looker_employee": False,
    },
]


class _RecordingFakeClient:
    """Records every (path, params) call; returns scripted pages from `pages`.

    Used to assert: endpoint, params, pagination-loop termination behavior.
    """

    def __init__(self, pages: list[list[dict[str, Any]]]) -> None:
        self.pages = pages
        self.calls: list[tuple[str, dict[str, Any] | None]] = []

    async def get(self, path: str, params: dict[str, Any] | None = None) -> list[dict[str, Any]]:
        self.calls.append((path, params))
        if not self.pages:
            return []
        return self.pages.pop(0)


class TestUsersPluginConformance(BasePluginContract):
    """All 9 inherited conformance tests + plugin-specific assertions."""

    plugin_class = UsersPlugin
    expected_min_rows = 2  # fixture yields 2 users on the default page

    @pytest.fixture
    def fake_client(self) -> Any:
        # Default fixture: one page of 2 users, then a short-page exit.
        # (2 < default page_size 500 — loop terminates after first call.)
        return _RecordingFakeClient(pages=[list(USER_FIXTURE_PAGE_1)])

    # ----- Plugin-specific assertions -----

    def test_name_pinned(self) -> None:
        """name is the entry-point key + the CLI --plugin flag; never change accidentally."""
        assert self.plugin_class.name == "users"

    def test_swagger_seeds_complete(self) -> None:
        """All credential variants present so generated User type resolves transitively."""
        seeds = set(self.plugin_class.swagger_seeds)
        required = {
            "User", "CredentialsApi3", "CredentialsEmail", "CredentialsEmailSearch",
            "CredentialsEmbed", "CredentialsGoogle", "CredentialsLDAP",
            "CredentialsLookerOpenid", "CredentialsOIDC", "CredentialsSaml",
            "CredentialsTotp", "Error", "ValidationError",
        }
        missing = required - seeds
        assert not missing, f"swagger_seeds missing: {sorted(missing)}"

    async def test_hits_users_search_endpoint(self) -> None:
        """Plugin must call /users/search (not /users) for fields= projection support."""
        client = _RecordingFakeClient(pages=[list(USER_FIXTURE_PAGE_1)])
        plugin = self.plugin_class()
        rows = [row async for row in plugin.extract(client)]
        assert len(rows) == 2
        assert all(call[0] == "users/search" for call in client.calls)

    async def test_default_fields_projection(self) -> None:
        """Default extract sends a fields= param so /users/search projects only what we need."""
        client = _RecordingFakeClient(pages=[list(USER_FIXTURE_PAGE_1)])
        plugin = self.plugin_class()
        async for _ in plugin.extract(client):
            pass
        first_params = client.calls[0][1] or {}
        assert "fields" in first_params
        # Identity columns must be in default projection.
        for col in ("id", "email", "first_name", "last_name"):
            assert col in first_params["fields"], f"{col!r} missing from default fields projection"

    async def test_lineage_envelope_stamped(self) -> None:
        """Every yielded row has _extract_user_id + _extract_user_email lineage."""
        client = _RecordingFakeClient(pages=[list(USER_FIXTURE_PAGE_1)])
        plugin = self.plugin_class()
        rows = [row async for row in plugin.extract(client)]
        for row in rows:
            assert_lineage_envelope(row)
            assert "_extract_user_id" in row
            assert "_extract_user_email" in row
        # Spot-check identity
        assert rows[0]["_extract_user_id"] == "100"
        assert rows[0]["_extract_user_email"] == "alice@example.com"
        assert rows[1]["_extract_user_id"] == "101"
        assert rows[1]["_extract_user_email"] == "bob@example.com"

    async def test_pagination_terminates_on_empty_page(self) -> None:
        """With explicit limit matching page size, loop must terminate when next page is []."""
        # Page 1: 2 records (matches limit=2 → not short → fetch next)
        # Page 2: [] (empty → terminate)
        client = _RecordingFakeClient(pages=[list(USER_FIXTURE_PAGE_1), []])
        plugin = self.plugin_class()
        rows = [row async for row in plugin.extract(client, filters={"limit": "2"})]
        assert len(rows) == 2
        assert len(client.calls) == 2, f"expected 2 calls (page + empty), got {len(client.calls)}"

    async def test_pagination_terminates_on_short_page(self) -> None:
        """Single page shorter than page_size terminates the loop in one call."""
        client = _RecordingFakeClient(pages=[list(USER_FIXTURE_PAGE_1)])
        plugin = self.plugin_class()
        rows = [row async for row in plugin.extract(client, filters={"limit": "500"})]
        assert len(rows) == 2
        assert len(client.calls) == 1, f"short-page must exit in 1 call, got {len(client.calls)}"
