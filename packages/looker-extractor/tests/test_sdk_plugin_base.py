"""Pin the Plugin ABC contract + stamp_lineage helper."""

import pytest

from looker_extractor_sdk import Plugin, stamp_lineage


def test_stamp_lineage_adds_prefix() -> None:
    row = {"name": "test"}
    out = stamp_lineage(row, model="m1", explore="e1")
    assert out is row  # in-place
    assert row["_extract_model"] == "m1"
    assert row["_extract_explore"] == "e1"
    assert row["name"] == "test"


def test_stamp_lineage_noop_when_no_kwargs() -> None:
    row = {"name": "test"}
    stamp_lineage(row)
    assert row == {"name": "test"}


def test_plugin_subclass_requires_extract() -> None:
    class BadPlugin(Plugin):
        name = "bad"
        version = "1.0"

    with pytest.raises(TypeError, match="abstract"):
        BadPlugin()


def test_plugin_concrete_subclass_instantiates() -> None:
    from typing import Any, AsyncIterator

    class GoodPlugin(Plugin):
        name = "good"
        version = "1.0"
        swagger_seeds = ["Foo"]

        async def extract(self, client: Any, *, filters: dict[str, str] | None = None) -> AsyncIterator[dict[str, Any]]:
            yield {"x": 1}

    p = GoodPlugin()
    assert p.name == "good"
