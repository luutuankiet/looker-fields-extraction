# looker-fields

A swagger-typed passthru extractor for the Looker v4.0 API. Authenticate, call the API for an entity, validate against pydantic types generated from the live swagger, and emit the natural nested shape as JSONL or Parquet. No projection, no dedup, no opinionated transforms -- the downstream warehouse handles those.

Think **meltano for Looker**: a single-responsibility tap built around Looker's v4.0 OpenAPI surface.

> v0.3.0a0 is the first alpha of the post-pivot architecture. Phase 1 (shipped): passthru shape for `explore_field`. Phase 2 (in progress): per-entity dispatch (dashboards, looks, queries, models, content). Phase 3+ adds Singer-protocol output and Meltano Hub registration.

## What you get

- One row per Looker entity (currently `explore_field`; `dashboard`, `look`, `query`, `model` queued for Phase 2)
- Native nested shape preserved -- `enumerations`, `time_interval`, `map_layer`, `sql_case`, `links`, `drill_fields` stay as structs/arrays, not stringified
- Minimal lineage envelope (`_extract_model_name`, `_extract_explore_name`, `_extract_explore_project_name`, `_extract_field_category`) so warehouse joins don't have to walk nested dicts
- Pydantic tripwire on every response -- API drift surfaces at extract time, not warehouse load time
- Per-instance manifest override layer (`extra_fields`, `type_overrides`) -- narrow type widening for instance-specific drift, no projection contract

## Use cases

| Want | Path |
|---|---|
| Build a Looker field catalog in BigQuery / Snowflake / Redshift | `extract --format parquet`, `bq load` / `COPY` |
| Power dbt models off Looker metadata | `extract --format jsonl` into a stage table, model in dbt |
| Inventory dashboards / looks / queries for a Looker audit | (Phase 2) `extract dashboard`, `extract look`, ... |
| Diff Looker state across environments | Two extracts, `diff` the JSONL or use DuckDB JOIN |
| Detect refinement / extends drift across explores | Pure SQL on the passthru shape -- see `docs/EXAMPLES.md` (queued) |

## Install

```bash
pip install looker-fields
# or with uv
uv pip install looker-fields
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
looker-fields info

# Extract all explore fields (JSONL default)
looker-fields extract --output fields.jsonl

# Parquet for warehouse load
looker-fields extract --format parquet --output fields.parquet

# Filter to one model / explore
looker-fields extract --model thelook --explore order_items --output one.jsonl

# Dump one explore's raw API JSON for offline debugging
looker-fields dump thelook order_items --output dump.json

# Pull the live swagger (cache for future codegen)
looker-fields refresh-schema
```

## Output shape

One row per field, passthru-shaped from the LookmlModelExploreField pydantic model. Nested structures preserved:

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

If your Looker instance returns fields the swagger doesn't declare (every instance has some -- `convert_tz`, `synonyms`, `lookml_expression`, etc.), document them in a per-instance manifest:

```yaml
# ~/.config/looker-fields/manifest.yaml
schema_version: "2.0"
entity: explore_field
extra_fields:
  convert_tz: "bool | None"
  synonyms: "list[str] | None"
type_overrides:
  times_used: "int | str | None"   # some instances return string here
```

Resolution chain (first hit wins): `--manifest-path` flag > `LOOKER_FIELDS_MANIFEST` env > `~/.config/looker-fields/manifest.yaml` > bundled default (empty).

Runtime catches extra fields via pydantic `extra="allow"` regardless; the manifest is for visibility + future codegen widening.

## Schema discovery

```bash
# Fetch live swagger from your instance; cached to ~/.config/looker-fields/swagger.json
looker-fields refresh-schema

# Override per-invocation
LOOKER_SWAGGER_PATH=/path/to/swagger.json looker-fields extract --output fields.jsonl
```

## Architecture

```
src/looker_fields/
├── cli.py            # typer CLI -- extract / dump / refresh-schema / info
├── config.py         # .env + Settings (pydantic-settings)
├── client.py         # async httpx client w/ rate limit + token auth
├── extract.py        # passthru: LookmlModelExploreField.model_validate → model_dump
├── output.py         # JsonlWriter + ParquetWriter (dict-based)
├── manifest/         # per-instance override layer (NOT projection)
│   ├── schema.py     #   ManifestSpec: schema_version + entity + extra_fields + type_overrides
│   ├── loader.py     #   4-step resolution (CLI > env > XDG > bundled)
│   └── fields.yaml   #   bundled scaffold -- empty extra_fields/type_overrides
└── _swagger/         # generated pydantic types from live swagger
    ├── types.py      #   21 pydantic classes (extra="allow")
    ├── loader.py     #   resolution chain mirrors manifest loader
    └── baseline.json #   bundled OpenAPI 3.0 subset
```

## Roadmap

| Version | Surface | Status |
|---|---|---|
| v0.3.0a0 | Phase 1 -- explore_field passthru | ✅ |
| v0.3.0 | Phase 2 -- per-entity dispatch (dashboards / looks / queries / models / content) | in progress |
| v0.3.x | Phase 3 -- ParquetWriter explicit nested schema (from pydantic) | queued |
| v0.4.0 | Singer-protocol output mode (`--format singer`) for Meltano compat | stretch |
| v0.5.0 | Register on MeltanoHub as `tap-looker-v4` (succeeds the deprecated v3.1 tap) | stretch |

## Contributing

```bash
# Run the full suite
pytest tests/ -v
```

## License

Apache 2.0. See `pyproject.toml`. (LICENSE file pending -- issue tracked.)
