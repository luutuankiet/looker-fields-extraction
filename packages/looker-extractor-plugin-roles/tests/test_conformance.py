"""Conformance tests: roles plugin is discoverable + implements SDK contract."""

from __future__ import annotations

import pytest

from looker_extractor_sdk import Plugin


def test_roles_plugin_importable() -> None:
    from looker_extractor_plugin_roles.plugin import RolesPlugin
    assert issubclass(RolesPlugin, Plugin)


def test_roles_plugin_class_attrs() -> None:
    from looker_extractor_plugin_roles.plugin import RolesPlugin
    assert RolesPlugin.name == "roles"
    assert RolesPlugin.version == "0.1.0a0"
    assert RolesPlugin.description.startswith("One row per Looker role")
    assert "Role" in RolesPlugin.swagger_seeds
    assert "PermissionSet" in RolesPlugin.swagger_seeds
    assert "ModelSet" in RolesPlugin.swagger_seeds
    assert len(RolesPlugin.swagger_seeds) == 5


def test_roles_plugin_discovered_via_entry_points() -> None:
    """If installed (editable mode in workspace), entry-points fire."""
    from importlib.metadata import entry_points

    eps = entry_points(group="looker_extractor.plugins")
    names = {ep.name for ep in eps}
    assert "roles" in names, f"roles plugin not discoverable; found: {names}"


@pytest.mark.asyncio
async def test_roles_plugin_extract_with_fake_client() -> None:
    """Drive RolesPlugin.extract() against a hand-rolled fake client."""
    from looker_extractor_plugin_roles.plugin import RolesPlugin

    class FakeClient:
        async def get(self, path: str, params: dict | None = None) -> list[dict]:
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
                },
            ]

    plugin = RolesPlugin()
    rows = [r async for r in plugin.extract(FakeClient())]
    assert len(rows) == 1
    row = rows[0]
    assert row["name"] == "Admin"
    assert row["permission_set"]["name"] == "Admin"
    assert row["model_set"]["name"] == "All"
    assert row["_extract_role_id"] == "1"
    assert row["_extract_role_name"] == "Admin"
