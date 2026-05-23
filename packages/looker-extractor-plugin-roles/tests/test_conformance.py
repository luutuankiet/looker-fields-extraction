"""Conformance: roles plugin meets the SDK contract + roles-specific shape.

The 9 generic conformance tests are inherited from BasePluginContract
(looker-extractor-tests-plugin). This file adds roles-specific assertions:
name pin, swagger_seeds full-set pin, and end-to-end extract field shape.
"""

from __future__ import annotations

from typing import Any

import pytest
from looker_extractor_tests_plugin import BasePluginContract

from looker_extractor_plugin_roles.plugin import RolesPlugin


class _RolesFakeClient:
    """Returns a single Admin role with nested permission/model_set sub-objects."""

    async def get(
        self,
        path: str,
        params: dict[str, Any] | None = None,
    ) -> list[dict[str, Any]]:
        assert path == "roles"
        return [
            {
                "id": "1",
                "name": "Admin",
                "permission_set": {
                    "id": "1",
                    "name": "Admin",
                    "permissions": ["administer"],
                    "all_access": True,
                    "built_in": True,
                    "url": "https://example/api/4.0/permission_sets/1",
                },
                "model_set": {
                    "id": "1",
                    "name": "All",
                    "models": ["thelook"],
                    "all_access": True,
                    "built_in": True,
                    "url": "https://example/api/4.0/model_sets/1",
                },
                "internal": False,
                "url": "https://example/api/4.0/roles/1",
                "users_url": "https://example/api/4.0/roles/1/users",
            }
        ]


class TestRolesConformance(BasePluginContract):
    """Full harness + roles-specific assertions.

    Inherits 9 generic tests; adds 3 roles-specific tests below.
    fake_client fixture is overridden → extract-behavior tests run (not skipped).
    """

    plugin_class = RolesPlugin
    expected_min_rows = 1

    @pytest.fixture
    def fake_client(self) -> Any:
        return _RolesFakeClient()

    # ------------------------------------------------------------------
    # Roles-specific (in addition to inherited harness)
    # ------------------------------------------------------------------

    def test_roles_name_pinned(self) -> None:
        """name is the entry-point key + the CLI --plugin flag; never change accidentally."""
        assert self.plugin_class.name == "roles"

    def test_roles_swagger_seeds_full_set(self) -> None:
        """Pin the seed list to catch accidental drift between regenerations."""
        seeds = self.plugin_class.swagger_seeds
        assert "Role" in seeds
        assert "PermissionSet" in seeds
        assert "ModelSet" in seeds
        assert len(seeds) == 5  # Role, PermissionSet, ModelSet, Error, ValidationError

    @pytest.mark.asyncio
    async def test_extract_yields_admin_role_with_nested_shape(
        self,
        fake_client: Any,
    ) -> None:
        """End-to-end: fake response → typed pass-through → nested shape preserved + lineage."""
        plugin = self.plugin_class()
        rows = [r async for r in plugin.extract(fake_client)]
        assert len(rows) == 1
        row = rows[0]
        assert row["name"] == "Admin"
        assert row["permission_set"]["name"] == "Admin"
        assert row["model_set"]["name"] == "All"
        assert row["_extract_role_id"] == "1"
        assert row["_extract_role_name"] == "Admin"
