"""Meta-tests: drive BasePluginContract against an inline dummy plugin.

Validates the harness itself works as advertised, without requiring any
third-party plugin to be installed.
"""

from __future__ import annotations

from typing import Any, AsyncIterator

import pytest

from looker_extractor_sdk import Plugin, stamp_lineage
from looker_extractor_tests_plugin import (
    BasePluginContract,
    assert_lineage_envelope,
)


class _DummyPlugin(Plugin):
    """Inline plugin for meta-testing — not registered as an entry-point."""

    name = "_dummy_meta_plugin_"
    version = "0.0.1"
    description = "Inline dummy for meta-testing the conformance harness."
    swagger_seeds = ["DummyType", "Error", "ValidationError"]

    async def extract(
        self,
        client: Any,
        *,
        filters: dict[str, str] | None = None,
    ) -> AsyncIterator[dict[str, Any]]:
        raw = await client.get("dummy", params=None)
        for r in raw:
            row = dict(r)
            stamp_lineage(row, dummy_id=str(r["id"]))
            yield row


class _FakeClient:
    """Hand-rolled fake for the dummy plugin."""

    async def get(self, path: str, params: Any = None) -> list[dict[str, Any]]:
        assert path == "dummy", f"unexpected path: {path}"
        return [
            {"id": "1", "name": "alpha"},
            {"id": "2", "name": "beta"},
        ]


class TestDummyPluginContract(BasePluginContract):
    """Meta-suite — drives the full BasePluginContract against _DummyPlugin."""

    plugin_class = _DummyPlugin
    skip_entry_point_check = True  # not registered as entry-point
    expected_min_rows = 2

    @pytest.fixture
    def fake_client(self) -> Any:
        return _FakeClient()


# ----------------------------------------------------------------------
# Helper-function tests (assert_lineage_envelope)
# ----------------------------------------------------------------------

def test_assert_lineage_envelope_passes_on_stamped_row() -> None:
    assert_lineage_envelope({"_extract_id": "1", "name": "alpha"})


def test_assert_lineage_envelope_fails_on_unstamped_row() -> None:
    with pytest.raises(AssertionError, match="lineage envelope"):
        assert_lineage_envelope({"id": "1", "name": "alpha"})
