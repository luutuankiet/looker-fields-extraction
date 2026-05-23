"""Base pytest class — inherit + set ``plugin_class`` to validate a plugin.

Mirrors the dbt-tests-adapter pattern (Base* pytest classes shipped as an
installable dep; adapter test suites subclass with one-line
``class TestX(BaseY): pass``).
"""

from __future__ import annotations

import inspect
from importlib.metadata import entry_points
from typing import Any, ClassVar

import pytest

from looker_extractor_sdk import Plugin

PLUGIN_ENTRY_POINT_GROUP = "looker_extractor.plugins"


def assert_lineage_envelope(row: dict[str, Any]) -> None:
    """Assert ``row`` carries at least one ``_extract_*`` key.

    Use directly in plugin-specific tests when you want to call out lineage
    without subclassing the full conformance harness.
    """
    lineage_keys = [k for k in row if k.startswith("_extract_")]
    assert lineage_keys, (
        f"Row missing lineage envelope (no `_extract_*` keys). "
        f"Row keys: {sorted(row)}"
    )


class BasePluginContract:
    """Inherit + set ``plugin_class`` to validate a plugin against the SDK contract.

    Required:
        plugin_class: type[Plugin]

    Optional fixture override (enables extract-behavior tests):
        @pytest.fixture
        def fake_client(self) -> Any:
            class _Fake:
                async def get(self, path, params=None):
                    return [{"id": "1"}]
            return _Fake()

    Optional ClassVar overrides:
        entry_point_name: defaults to ``plugin_class.name``
        expected_min_rows: defaults to 1
        skip_entry_point_check: set True for inline / dev-only plugins
    """

    plugin_class: ClassVar[type[Plugin]]
    entry_point_name: ClassVar[str | None] = None
    expected_min_rows: ClassVar[int] = 1
    skip_entry_point_check: ClassVar[bool] = False

    @pytest.fixture
    def fake_client(self) -> Any:
        pytest.skip(
            "Override the `fake_client` fixture in your test subclass to enable "
            "extract-behavior tests. Return an object with an "
            "`async def get(self, path, params=None)` method."
        )

    # ------------------------------------------------------------------
    # Pure ABC / class-attr conformance (no client needed)
    # ------------------------------------------------------------------

    def test_plugin_class_subclasses_sdk_plugin(self) -> None:
        assert issubclass(self.plugin_class, Plugin), (
            f"{self.plugin_class.__name__} must subclass "
            "looker_extractor_sdk.Plugin"
        )

    def test_plugin_class_attrs_non_empty(self) -> None:
        assert self.plugin_class.name, "plugin_class.name must be non-empty"
        assert self.plugin_class.version, "plugin_class.version must be non-empty"
        assert self.plugin_class.description, (
            "plugin_class.description must be non-empty"
        )

    def test_plugin_swagger_seeds_unique_non_empty(self) -> None:
        seeds = self.plugin_class.swagger_seeds
        assert isinstance(seeds, list), "swagger_seeds must be a list"
        assert seeds, (
            "swagger_seeds must be non-empty (regen_schema needs >=1 type "
            "to anchor the OAS3 subset extraction)"
        )
        assert len(set(seeds)) == len(seeds), (
            f"swagger_seeds has duplicates: {seeds}"
        )

    def test_plugin_swagger_seeds_include_error_types(self) -> None:
        seeds = self.plugin_class.swagger_seeds
        # OAS3 codegen relies on these as canonical error types
        assert "Error" in seeds, (
            "swagger_seeds should include 'Error' (canonical error type)"
        )
        assert "ValidationError" in seeds, (
            "swagger_seeds should include 'ValidationError' (canonical "
            "validation-error type)"
        )

    def test_plugin_extract_is_async_generator(self) -> None:
        assert inspect.isasyncgenfunction(self.plugin_class.extract), (
            f"{self.plugin_class.__name__}.extract must be an async generator "
            "function (declared `async def extract(...)` with `yield` inside)."
        )

    def test_plugin_discovered_via_entry_points(self) -> None:
        if self.skip_entry_point_check:
            pytest.skip(
                "skip_entry_point_check=True; entry-point discovery not "
                "validated for this subclass"
            )
        ep_name = self.entry_point_name or self.plugin_class.name
        eps = entry_points(group=PLUGIN_ENTRY_POINT_GROUP)
        found = {ep.name: ep.value for ep in eps}
        assert ep_name in found, (
            f"Plugin {ep_name!r} not discoverable via entry-points group "
            f"{PLUGIN_ENTRY_POINT_GROUP!r}. Found: {sorted(found)}. "
            f'Add to your pyproject.toml: '
            f'[project.entry-points."{PLUGIN_ENTRY_POINT_GROUP}"] '
            f'{ep_name} = "your_module.plugin:{self.plugin_class.__name__}"'
        )

    def test_plugin_entry_point_resolves_to_class(self) -> None:
        if self.skip_entry_point_check:
            pytest.skip("skip_entry_point_check=True")
        ep_name = self.entry_point_name or self.plugin_class.name
        eps = entry_points(group=PLUGIN_ENTRY_POINT_GROUP)
        matches = [ep for ep in eps if ep.name == ep_name]
        if not matches:
            pytest.skip(
                "entry-point not registered; "
                "covered by test_plugin_discovered_via_entry_points"
            )
        loaded = matches[0].load()
        assert loaded is self.plugin_class, (
            f"Entry-point {ep_name!r} resolves to {loaded!r}, "
            f"expected {self.plugin_class!r}"
        )

    # ------------------------------------------------------------------
    # Extract behavior — requires fake_client fixture override
    # ------------------------------------------------------------------

    @pytest.mark.asyncio
    async def test_extract_yields_min_rows(self, fake_client: Any) -> None:
        plugin = self.plugin_class()
        rows = [r async for r in plugin.extract(fake_client)]
        assert len(rows) >= self.expected_min_rows, (
            f"extract() yielded {len(rows)} rows, "
            f"expected >= {self.expected_min_rows}"
        )

    @pytest.mark.asyncio
    async def test_extract_rows_have_lineage(self, fake_client: Any) -> None:
        plugin = self.plugin_class()
        rows = [r async for r in plugin.extract(fake_client)]
        if not rows:
            pytest.skip(
                "no rows yielded; covered by test_extract_yields_min_rows"
            )
        for i, row in enumerate(rows):
            try:
                assert_lineage_envelope(row)
            except AssertionError as e:
                raise AssertionError(f"row[{i}]: {e}") from e
