# looker-extractor-tests-plugin

Pytest base classes that a third-party plugin for [looker-extractor](https://github.com/luutuankiet/looker-extractor) can subclass to validate it conforms to the Plugin SDK contract — dbt-tests-adapter style.

## Install

```bash
uv add --dev looker-extractor-tests-plugin
# or: pip install --dev looker-extractor-tests-plugin
```

## Usage

In your plugin package's `tests/test_conformance.py`:

```python
import pytest
from looker_extractor_tests_plugin import BasePluginContract
from my_plugin import MyPlugin


class TestMyPluginConformance(BasePluginContract):
    plugin_class = MyPlugin
    expected_min_rows = 1

    @pytest.fixture
    def fake_client(self):
        class _Fake:
            async def get(self, path, params=None):
                return [{"id": "1", "name": "alpha"}]
        return _Fake()
```

That single subclass produces 9 tests (ABC compliance, class attrs, swagger_seeds shape, async-generator check, entry-point discovery + resolution, extract behavior + lineage envelope).

For plugin-specific assertions (e.g., field shape, filter pass-through), add additional `test_*` methods to the same class — they have access to the same `fake_client` fixture.

## Knobs

| ClassVar | Default | Notes |
|---|---|---|
| `plugin_class` | required | Your `Plugin` subclass |
| `entry_point_name` | `plugin_class.name` | Override if entry-point key differs from `name` |
| `expected_min_rows` | `1` | Bump if your plugin must always yield > 1 |
| `skip_entry_point_check` | `False` | Set `True` for inline dummies / dev-only plugins not registered as entry-points |

## Helpers

- `assert_lineage_envelope(row)` — assert at least one `_extract_*` key on a row. Use directly in plugin-specific tests when you want to call out lineage without the full contract harness.

## Versioning

Pins `looker-extractor-sdk>=0.1.0,<0.2`. Bumps in lockstep with the SDK major.

## License

MIT.
