# looker-extractor

Plugin-based passthru extractor for the Looker v4.0 API. Authenticate, dispatch to a plugin, validate the API response against the plugin's swagger-generated pydantic types, and emit the natural nested shape as JSONL or Parquet. The reference plugin (`lookml_fields`) ships in-tree; third-party plugins ship as separate pip packages and are discovered via Python entry-points.

Think **dbt for Looker extraction**: a core harness + an SDK + plugins. Each plugin owns one Looker entity (explore fields, dashboards, looks, scheduled plans, ...) and produces one row per record, passthru-shaped from the Looker API.

> v0.3.0a0 is the first alpha of the plugin platform. The reference plugin `lookml_fields` is fully wired and live-verified against a 12,731-row Joon-instance baseline. Additional in-tree plugins land in Phase 4 (priority order: roles → users → looks → scheduled_plans → folders → user_attributes).

## What you get

- **One row per Looker entity** (currently `explore_field` via the reference plugin; more plugins queued)
- **Native nested shape preserved** — `enumerations`, `time_interval`, `map_layer`, `sql_case`, `links`, `drill_fields` stay as structs/arrays, not stringified
- **Minimal lineage envelope** (`_extract_<key>` keys per plugin) so warehouse joins don't have to walk nested dicts
- **Pydantic tripwire** on every API response — drift surfaces at extract time, not warehouse load time
- **Per-instance manifest override layer** (`extra_fields`, `type_overrides`) — narrow type widening for instance-specific drift, no projection contract
- **Plugin SDK** as a separate `looker-extractor-sdk` pip package — plugin authors depend on a minimal ABI, not the full core
- **Entry-points discovery** — third-party plugins (`pip install looker-extractor-plugin-<name>`) auto-register; no core code changes needed

## Install

```bash
pip install looker-extractor
# or with uv
uv pip install looker-extractor
```

## Setup

```bash
# .env file in the directory you'll run from
LOOKER_BASE_URL=https://your.looker.cloud
LOOKER_CLIENT_ID=...
LOOKER_CLIENT_SECRET=...
```

## Quickstart

```bash
# Show what your instance has
looker-extractor info

# List installed plugins (default install bundles lookml_fields)
looker-extractor plugins list

# Show metadata for one plugin
looker-extractor plugins info lookml_fields

# Run the default plugin (lookml_fields) — JSONL
looker-extractor extract --output fields.jsonl

# Same, explicit plugin selection + short alias `lx`
lx extract --plugin lookml_fields --output fields.jsonl

# Parquet for warehouse load
looker-extractor extract --format parquet --output fields.parquet

# Filter to one model / explore
looker-extractor extract --model thelook --explore order_items --output one.jsonl

# Dump one explore's raw API JSON for offline debugging
looker-extractor dump thelook order_items --output dump.json

# Pull the live swagger (cache for future codegen)
looker-extractor refresh-schema
```

## Output shape (reference plugin `lookml_fields`)

One row per field, passthru-shaped from the `LookmlModelExploreField` pydantic model. Nested structures preserved:

```json
{
  "name": "discounts.date_day_of_week",
  "type": "string",
  "category": "dimension",
  "view": "discounts",
  "original_view": "dates",
  "sql": "${TABLE}.date_day_of_week",
  "enumerations": [
    {"label": "Monday", "value": "Monday"},
    {"label": "Tuesday", "value": "Tuesday"}
  ],
  "time_interval": null,
  "tags": ["business_day"],
  "_extract_model_name": "thelook_partner",
  "_extract_explore_name": "order_items",
  "_extract_explore_project_name": "thelook",
  "_extract_field_category": "dimension"
}
```

Downstream flattening is a warehouse job:

```sql
-- BigQuery example: flatten the enumerations struct array
SELECT name, e.label, e.value
FROM fields, UNNEST(enumerations) AS e
WHERE _extract_field_category = 'dimension';
```

## Per-instance manifest overrides

If your Looker instance returns fields the swagger doesn't declare (every instance has some — `convert_tz`, `synonyms`, `lookml_expression`, etc.), document them in a per-instance manifest:

```yaml
# ~/.config/looker-extractor/manifest.yaml
schema_version: "2.0"
entity: explore_field
extra_fields:
  convert_tz: "bool | None"
  synonyms: "list[str] | None"
type_overrides:
  times_used: "int | str | None"   # some instances return string here
```

Resolution chain (first hit wins): `--manifest-path` flag > `LOOKER_FIELDS_MANIFEST` env > `~/.config/looker-extractor/manifest.yaml` > bundled default (empty).

Runtime catches extra fields via pydantic `extra="allow"` regardless; the manifest is for visibility + future codegen widening.

## Schema discovery

```bash
# Fetch live swagger from your instance; cached to ~/.config/looker-extractor/swagger.json
looker-extractor refresh-schema

# Override per-invocation
LOOKER_SWAGGER_PATH=/path/to/swagger.json looker-extractor extract --output fields.jsonl
```

## Plugin architecture

```
looker-extractor/                    # CLI + core harness
  src/looker_extractor/
    cli.py                           # typer: extract / dump / refresh-schema / info / plugins {list,info}
    core/
      client.py                      # async httpx client w/ rate limit + token auth
      config.py                      # .env + Settings (pydantic-settings)
      manifest/                      # per-instance override layer (NOT projection)
      swagger/                       # 4-step swagger loader (CLI > env > XDG > bundled)
    plugins/
      lookml_fields/                 # reference plugin (in-tree)
        plugin.py                    # LookmlFieldsPlugin(Plugin) wrapper
        extract.py                   # async generator over (model, explore) pairs
        manifest.yaml                # bundled manifest scaffold
        swagger/                     # plugin-specific swagger types + baseline
    registry/
      discover.py                    # entry-points scan (group: looker_extractor.plugins)

looker-extractor-sdk/                # separate pip package
  src/looker_extractor_sdk/
    plugin.py                        # Plugin ABC + stamp_lineage helper (minimal ABI)
```

Third-party plugin authors depend on `looker-extractor-sdk` only (pydantic-only deps); their package declares the plugin entry-point:

```toml
# my-plugin/pyproject.toml
[project.entry-points."looker_extractor.plugins"]
my_plugin = "my_plugin.plugin:MyPlugin"
```

`pip install my-looker-plugin` makes it available as `looker-extractor extract --plugin my_plugin`. No core modification needed.

## Roadmap

| Phase | Surface | Status |
|---|---|---|
| Phase 1 (v0.3.0a0) | uv workspace + plugin platform + lookml_fields reference | ✅ shipped LOCAL |
| Phase 2 | SDK extraction as standalone PyPI release + per-package release workflows | next |
| Phase 3 | Copier scaffold for `plugins init <name>` | queued |
| Phase 4 | In-tree plugins: roles → users → looks → scheduled_plans → folders → user_attributes | queued |
| Phase 5 | Plugin Hub JSON + `plugins search/install` | queued |
| Phase 6 | Sandbox mode `plugins sandbox <name>` via uvx | queued |
| Phase 7 | YAML-only plugin loader (no Python required for simple extractors) | queued |
| Phase 8 | Conformance harness `looker-extractor-tests-plugin` + v1.0 tag + PyPI publish | queued |

## Contributing

```bash
# Run the full suite
uv sync --extra dev
.venv/bin/pytest packages/looker-extractor/tests/ -v
```

## License

Apache 2.0. See `pyproject.toml`. (LICENSE file pending — issue tracked.)
