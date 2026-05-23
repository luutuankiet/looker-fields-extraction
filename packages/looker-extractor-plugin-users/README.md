# looker-extractor-plugin-users

looker-extractor plugin: extract Looker users records.

## What this is

A [looker-extractor](https://github.com/luutuankiet/looker-extractor) plugin that extracts records from the Looker `/api/4.0/users` endpoint, validates them against a swagger-generated pydantic type (the tripwire), and yields passthru dicts with `_extract_*` lineage envelopes.

## Install

```bash
uv add looker-extractor-plugin-users
# or: pip install looker-extractor-plugin-users
```

## Use

After install, the plugin is auto-discovered via Python entry-points:

```bash
looker-extractor plugins list      # should show: users
looker-extractor extract --plugin users -o users.jsonl
```

## Develop

```bash
git clone <your-repo-url>
cd looker-extractor-plugin-users
uv sync --extra dev
uv run pytest -v
```

The test suite uses [looker-extractor-tests-plugin](https://github.com/luutuankiet/looker-extractor/tree/main/packages/looker-extractor-tests-plugin); a single `class TestUsersPluginConformance(BasePluginContract)` subclass produces 9 conformance tests automatically (ABC compliance, class attrs, swagger seeds shape, async-generator check, entry-point discovery + resolution, extract-behavior + lineage envelope).

To enable the 2 extract-behavior tests, uncomment + populate the `fake_client` fixture in `tests/test_conformance.py`.

## Regenerate swagger types

The `src/looker_extractor_plugin_users/swagger/types.py` file is a placeholder. To generate real pydantic types from Looker's OAS3 spec, see the [Plugin Authoring Guide](https://github.com/luutuankiet/looker-extractor/blob/main/packages/looker-extractor-sdk/AUTHORING.md#regenerating-swagger-types).

(Future: `lx plugins gen-types --plugin users` will do this in one command — Phase 3 Iter 5.)

## Template provenance

Generated from the [looker-extractor plugin template](https://github.com/luutuankiet/looker-extractor) via [copier](https://copier.readthedocs.io/).

`.copier-answers.yml` (committed alongside source) records the template ref + answers used at init time.

To pull template improvements later:
```bash
copier update --trust
```

Files preserved on update: `plugin.py`, `swagger/types.py`, `tests/test_conformance.py` (your work). Infrastructure files (pyproject, README, conformance harness) update cleanly.

## License

Apache-2.0.
