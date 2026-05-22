# looker-fields

> **The compiled truth about every field in your Looker instance** — with an output schema you own.

Hand-rolling Looker metadata pipelines is a tax. Parsing raw `.lkml` files lies (`include:` resolution, refinements, view aliasing). The official SDK gives you raw API JSON, not analysis-ready rows. And every team rewrites the same field flattener — missing the same edge cases, hitting the same duplication bug.

`looker-fields` extracts every field — dimensions, measures, dimension groups, filters, parameters — across every model and explore, with **correct model attribution** and **cross-explore visibility**. The output schema is yours: it's a YAML manifest you can edit, override, regenerate.

```bash
pip install looker-fields
looker-fields extract -o all_fields.jsonl     # 12K+ fields in seconds, zero dupes
```

## What you get

One row per `(project, model, explore, field)` with 49 columns covering:

- **Identity** — fully-qualified name, view, original view (after `from:` aliasing), source LookML file
- **Classification** — category (dimension/measure/filter/parameter), type, is_numeric, is_timeframe, primary_key
- **Display** — label, label_short, group_label, hidden, value_format, value_format_name
- **LookML source** — sql expression (if you have `see_lookml`), source_file_path, scope
- **Quality signals** — `times_used` (dead-field detection), `total_times_used`, tags
- **Cross-explore visibility** — `seen_in_model_count`, `seen_in_explore_count`, `seen_models[]`, `seen_explores[]` — answers "where is this field actually used?"
- **Explore context** — explore label, description, connection, base view
- **Provenance** — extracted_at timestamp, schema_version

Sample row (JSONL):

```json
{"project_name":"thelook","model_name":"thelook","explore_name":"order_items","field_name":"users.email","category":"dimension","field_type":"string","label":"Users Email","view_name":"users","original_view":"users","sql":"${TABLE}.email","source_file_path":"thelook/views/users.view.lkml","primary_key":false,"sortable":true,"can_filter":true,"times_used":1234,"seen_in_explore_count":7,"seen_models":["thelook"],"seen_explores":["thelook::events","thelook::order_items","thelook::orders","thelook::sessions","thelook::users"]}
```

## Use cases

| You want to... | Use the column(s)... |
|---|---|
| Find dead fields nobody uses | `times_used = 0` |
| Map field lineage across explores | `seen_explores[]` |
| Audit which fields expose PII | `tags`, `description`, regex on `sql` |
| Feed a data catalog / metric registry | join on `(model, explore, field_name)` |
| Detect when a LookML refactor changed something | diff JSONL snapshots across runs |
| Audit silent refinement drift across the instance (v0.2.1+) | `definition_variant_count > 1` |
| Trace a field across `from:` join aliases (v0.2.1+) | group by `(original_view, leaf_name)` or use `definition_appearances_count` |
| Track Looker API drift after an upgrade | `looker-fields refresh-schema` |
| Build a BI cost model | aggregate `total_times_used` by `view_name` |
| Push fresh metadata to BigQuery for governance | `looker-fields extract --format bq ...` |

## Why this is different

| Approach | Resolves `include:` | Correct model attribution | Cross-explore visibility | Schema you own |
|---|---|---|---|---|
| Parse raw `.lkml` files | ❌ | ❌ | ❌ | manual |
| Drive the official `looker_sdk` directly | ✅ | ⚠️ (default) | ❌ | none — raw API |
| Build your own flattener | ✅ | ⚠️ (easy to mess up) | ❌ | yours, but you wrote it |
| `looker-fields` | ✅ | ✅ (by construction) | ✅ | YAML manifest, codegen'd |

**The duplication bug** that breaks naive pipelines: an explore can be defined in `model_A` AND surfaced in `model_B` via `include:`. Naive code keys by `(project, explore, field)` and Cartesian-explodes. `looker-fields` keys by `(project, model, explore, field)` — where model is **always** the extraction loop's iteration variable, never the API response's nullable `explore.model_name`. Duplication is impossible by construction.

## Field Identity Semantics (v0.2.1+)

Three distinct identity flavors. Conflating them silently misleads on heavily-refined LookML.

| Identity flavor | Tuple | Answers | Column(s) |
|---|---|---|---|
| **Appearance** | `(project, model, explore, field_name)` | "Where is this field visible in the catalog?" | row grain — 1 row per tuple, never collapsed |
| **Definition** | `(original_view, leaf_name)` + content hash | "What LookML source produced this field?" | `definition_hash`, `definition_variant_count`, `definition_appearances_count` |
| **Logical** | `field_name` alone | "Is this 'the same field' across the instance?" | `seen_in_model_count`, `seen_in_explore_count`, `seen_models[]`, `seen_explores[]` |

The v0.2.0 row grain was correct — every appearance is preserved 1:1, no rows dropped. But the `seen_in_*` summary columns are keyed by `field_name` alone. When a refinement in `model_B` adds a `pii` tag or replaces the SQL on `users.email`, both `model_A.users.email` and `model_B.users.email` rows stamp `seen_in_explore_count=2` — implying uniform definition. **That was the silent drift.** v0.2.1 makes it queryable.

### One-query drift audit

```sql
SELECT field_name,
       seen_in_explore_count,        -- old logical answer
       definition_variant_count,     -- new content-drift answer
       definition_appearances_count  -- new cross-alias lineage answer
FROM read_json_auto('extract.jsonl')
WHERE definition_variant_count > 1
ORDER BY definition_variant_count DESC, seen_in_explore_count DESC;
```

Empirical baseline on one real 12,731-field instance: **9.6% of rows** had `definition_variant_count > 1` (silent refinement drift); **40.2%** had `definition_appearances_count > 1` (cross-alias semantics `seen_in_*` couldn't surface).

### What we can't tell you (honest limits)

The Looker API does not expose `extends_chain`, `included_via`, or any refinement-chain attribution — only the *composed result*. So `definition_hash` will split rows whose semantic content actually differs, but cannot tell you *which* refinement or include caused the divergence. For that, parse the LookML repo directly.

## Install

```bash
pip install looker-fields
```

Or for development:

```bash
git clone https://github.com/luutuankiet/looker-fields-extraction.git
cd looker-fields-extraction
pip install -e ".[dev]"
```

## Setup

Create `.env`:

```env
LOOKER_BASE_URL=https://your-instance.cloud.looker.com
LOOKER_CLIENT_ID=your_client_id
LOOKER_CLIENT_SECRET=your_client_secret
```

API credentials: Looker → Admin → Users → your user → "Edit Keys" → "New API3 Key".

## Quickstart

```bash
# Show what your instance has
looker-fields info

# Extract everything (JSONL is the default; -o is short for --output)
looker-fields extract -o all_fields.jsonl

# Single model / explore
looker-fields extract --model my_model --explore my_explore -o slice.jsonl

# Round-trip verify a specific explore (re-fetches, diffs, exits 0/1)
looker-fields verify my_model my_explore -o all_fields.jsonl

# Push to BigQuery
looker-fields extract --format bq -o my_project.my_dataset.fields

# Dump one explore's raw API JSON for offline debugging
looker-fields dump my_model my_explore -o raw.json
```

## The manifest is your contract

Most metadata tools force you to live with their output schema. This one inverts that: the output is defined by `src/looker_fields/manifest/fields.yaml`, which ships as a bundled default but you can override entirely.

```yaml
# manifest/fields.yaml (excerpt)
columns:
  - name: model_name
    type: str
    api_source: context.model_name   # extraction-loop ground truth (never null)
    default: ''
    description: Always from explore context — the fix for duplication

  - name: times_used
    type: int
    api_source: field.times_used
    default: 0
    description: Count of query usage. Valuable for identifying dead fields
```

Want to add a column? Edit the YAML.

```bash
# Use a custom manifest for one invocation
looker-fields extract --manifest-path ./my_manifest.yaml

# Or install it permanently to XDG config
cp my_manifest.yaml ~/.config/looker-fields/manifest.yaml

# Or set per-invocation via env
LOOKER_FIELDS_MANIFEST=./my_manifest.yaml looker-fields extract

# Regenerate the typed FieldRecord pydantic class to match your manifest
looker-fields regen-types

# Next invocation dynamic-imports your custom contract from
# ~/.cache/looker-fields/_fieldrecord/types.py
# (revert: rm that file)
```

4-step resolution chain (CLI flag > env var > XDG > bundled). Whichever you set wins predictably.

## Drift detection at both ends

When Looker upgrades and the API changes:

```bash
# Fetch fresh swagger, run TWO drift detectors:
#   v1 — does the swagger still carry every path the extractor depends on?
#   v2 — does every manifest api_source still resolve against the live swagger?
looker-fields refresh-schema
```

When you want to know if there are new API attributes you could add to your manifest:

```bash
# Surfaces additions: swagger attrs the manifest doesn't reference yet.
looker-fields refresh-manifest
```

Both commands surface signal. Neither auto-writes — you decide.

## Output formats

| Format | Flag | Use case |
|---|---|---|
| JSONL | `--format jsonl` (default) | Streaming, DuckDB, jq |
| CSV | `--format csv` | Spreadsheet, diff, manual review |
| Parquet | `--format parquet` | Columnar analytics, large instances |
| BigQuery | `--format bq` | Production governance pipelines |

Adding a new sink = one writer class subclassing `output.Writer`.

## Architecture

Three-layer codegen surface:

```
swagger.json (Looker owns) ---> _swagger/types.py (input parsers, extra="allow")
manifest/fields.yaml (you own) ---> _fieldrecord/types.py (output records, extra="forbid")
                              ---> projection.project_field (runtime mapper)
```

The three-`extra`-policy invariant:

| Layer | Module | Pydantic policy | Why |
|---|---|---|---|
| **Input** | `_swagger/types.py` | `extra="allow"` | forward-compat with Looker API additions |
| **Config** | `manifest/schema.py` | `extra="allow"` | forward-compat with new manifest sections |
| **Output** | `_fieldrecord/types.py` | `extra="forbid"` | strict contract for downstream consumers |

Client overrides flow through XDG cache + dynamic import: edit YAML, run `regen-types`, next program startup loads your contract instead of the bundled one. No site-packages write needed.

## Roadmap

This is **Fields v1** of a multi-entity framework. Same manifest-native pattern will land for:

- **Models** (v2) — model-level metadata + project lineage
- **Explores** (v3) — explore graphs + join semantics
- **Looks / Dashboards** (v4-v5) — saved-query metadata + dashboard composition

## Contributing

```bash
# Run the full suite (43 tests)
pytest tests/ -v

# Regenerate the bundled manifest after editing docs/FIELD_SPEC.md
python scripts/parse_field_spec_to_manifest.py

# Regenerate the bundled FieldRecord after editing the manifest
python scripts/regen_fieldrecord.py
```

PRs welcome. The codebase is intentionally small (~2K LOC) and aggressively unit-tested. Adding a column = YAML edit + one regen + commit; adding a sink = one writer class.

## License

Apache 2.0
