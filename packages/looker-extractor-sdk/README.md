# looker-extractor-sdk

The plugin SDK for [looker-extractor](https://github.com/luutuankiet/looker-extractor) —
the Plugin Protocol + helpers that plugin authors depend on to build their own Looker
entity extractors without pulling the full extractor core.

## What's in this package

```python
from looker_extractor_sdk import Plugin, stamp_lineage
```

- **`Plugin`** — abstract base class. Subclass it, set class attributes
  (`name`, `version`, `swagger_seeds`), implement async `extract(client, *, filters)`.
- **`stamp_lineage`** — helper that writes `_extract_<key>` keys into a record dict.

That's the entire public surface. Intentionally tiny.

## Quick start (10-line plugin)

```python
from looker_extractor_sdk import Plugin, stamp_lineage

class MyPlugin(Plugin):
    name = "my_plugin"
    version = "0.1.0"
    swagger_seeds = ["MyEntity"]

    async def extract(self, client, *, filters=None):
        for row in await client.get("my_entities"):
            yield stamp_lineage(row, my_entity_id=row["id"])
```

Register it via entry-points in your `pyproject.toml`:

```toml
[project.entry-points."looker_extractor.plugins"]
my_plugin = "my_pkg.plugin:MyPlugin"
```

Install your plugin into the same env as `looker-extractor`, and it's discoverable:

```bash
$ looker-extractor plugins list
NAME            VERSION   DESCRIPTION
lookml_fields   0.3.0a0   One row per LookML explore field; ...
my_plugin       0.1.0     ...

$ looker-extractor extract --plugin my_plugin -o out.jsonl
```

## Why a separate package?

The SDK is intentionally minimal. It depends ONLY on `pydantic` so plugin authors
don't pull the full looker-extractor dependency tree (httpx, looker-sdk, typer,
pyarrow, ...) just to declare a Plugin class.

Pattern borrowed from `dbt-adapters` / `dbt-core`: a stable, slim contract package
that adapter authors target, separate from the engine that consumes them.

## Plugin Authoring Guide

See [AUTHORING.md](./AUTHORING.md) for the full walkthrough: plugin contract,
entry-points registration, lineage envelope (`stamp_lineage`), swagger seeds +
`regen_schema` flow, filters convention, testing recipes (4 reusable patterns),
and a worked example walking through the [`roles` plugin](https://github.com/luutuankiet/looker-extractor/tree/main/packages/looker-extractor-plugin-roles)
end-to-end.

## Compatibility

- Python ≥ 3.11
- pydantic ≥ 2.0

License: Apache-2.0.
