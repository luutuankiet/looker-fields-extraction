# Field Specification v1.1.0

Baseline output schema for `looker-fields` extraction tool.

**Source of truth:** Looker API 4.0 — `GET /lookml_models/{model}/explores/{explore}`
**Verified against:** `joonpartner.cloud.looker.com` (2026-04-04)
**Swagger ref:** `looker_40_openapi.json` → `#/definitions/LookmlModelExplore`

---

## Output Grain

**One row per `(project_name, model_name, explore_name, field_name)`**

This composite key is unique by construction. The Looker API returns fields scoped to a specific model::explore pair, so `model_name` is always present and correct — eliminating the Cartesian duplication that occurs when merging file-parsed explores with API data.

---

## Field Sources

The API response has this structure:
```
LookmlModelExplore
├── name, model_name, project_name, ...  (explore-level)
└── fields: LookmlModelExploreFieldset
    ├── dimensions[]: LookmlModelExploreField[]
    ├── measures[]: LookmlModelExploreField[]
    ├── filters[]: LookmlModelExploreField[]
    └── parameters[]: LookmlModelExploreField[]
```

All four arrays contain the same `LookmlModelExploreField` type. Dimension groups do NOT have their own array — group members appear as individual dimensions with `dimension_group` set to the group name.

---

## Output Columns

### Identity (Unique Grain)

| Column | Type | API Source | Notes |
|--------|------|------------|-------|
| `project_name` | str | `field.project_name` or `explore.project_name` | Field-level preferred; falls back to explore-level |
| `model_name` | str | `explore.model_name` | Always from explore context — THE fix for duplication |
| `explore_name` | str | `explore.name` | Explore name within the model |
| `field_name` | str | `field.name` | Fully-qualified: `view_name.field_name` (e.g., `order_items.total_revenue`) |

### Classification

| Column | Type | API Source | Notes |
|--------|------|------------|-------|
| `category` | str | `field.category` | `"dimension"`, `"measure"`, `"filter"`, `"parameter"` — more reliable than array membership |
| `field_type` | str | `field.type` | LookML type: `string`, `number`, `yesno`, `date_date`, `date_month`, `count`, `sum`, `average`, etc. |
| `is_numeric` | bool | `field.is_numeric` | True for numeric types |
| `is_timeframe` | bool | `field.is_timeframe` | True for date/time types — dim group members have this set |
| `is_fiscal` | bool | `field.is_fiscal` | True for fiscal calendar variants |
| `is_filter` | bool | `field.is_filter` | True for filter-only fields |
| `dynamic` | bool | `field.dynamic` | True if created via `dynamic_fields`, not in the LookML model |

### Display

| Column | Type | API Source | Notes |
|--------|------|------------|-------|
| `label` | str | `field.label` | Fully-qualified: includes view label (e.g., `"Order Items Total Revenue"`) |
| `label_short` | str | `field.label_short` | Without view prefix (e.g., `"Total Revenue"`) |
| `description` | str | `field.description` | LookML `description` parameter; empty string if unset |
| `view_name` | str | `field.view` | View this field appears under (may be join alias) |
| `view_label` | str | `field.view_label` | Human-readable view label for UI grouping |
| `original_view` | str | `field.original_view` | Where field is actually defined — differs from `view` when `from:` join alias is used |
| `group_label` | str | `field.field_group_label` | UI field group label; null mapped to empty string |
| `hidden` | bool | `field.hidden` | True if hidden from explore UI (still extracted) |

### LookML Source

| Column | Type | API Source | Notes |
|--------|------|------------|-------|
| `sql` | str? | `field.sql` | SQL expression from LookML (e.g., `${TABLE}.date`). **Requires `see_lookml` permission** — null without it |
| `source_file` | str | `field.source_file` | Relative file path (e.g., `views/order_items.view.lkml`) |
| `source_file_path` | str | `field.source_file_path` | Fully-qualified path: `project_name/views/file.lkml` |
| `dimension_group` | str? | `field.dimension_group` | Group name if this field is a dimension group member (e.g., `order_items.created`). Null for non-grouped fields |
| `scope` | str | `field.scope` | LookML scope, typically the view name |
| `primary_key` | bool | `field.primary_key` | True if declared as `primary_key: yes` |

### Formatting

| Column | Type | API Source | Notes |
|--------|------|------------|-------|
| `value_format` | str? | `field.value_format` | Explicit LookML `value_format` string |
| `value_format_name` | str? | `field.value_format_name` | Named format (e.g., `decimal_2`, `usd`) |
| `sortable` | bool | `field.sortable` | Whether field can be sorted in queries |
| `can_filter` | bool | `field.can_filter` | Whether field can be used in filters |

### Suggestions & Tags

| Column | Type | API Source | Notes |
|--------|------|------------|-------|
| `suggest_dimension` | str | `field.suggest_dimension` | Dimension used for suggest queries |
| `suggest_explore` | str | `field.suggest_explore` | Explore used for suggest queries |
| `tags` | list[str] | `field.tags` | Arbitrary string tags from LookML `tags` parameter. Serialized as JSON array in JSONL/CSV |

### Usage

| Column | Type | API Source | Notes |
|--------|------|------------|-------|
| `times_used` | int | `field.times_used` | Count of query usage. Valuable for identifying dead fields |

### Explore Context (Denormalized)

These explore-level fields are repeated on every field row for flat-file queryability:

| Column | Type | API Source | Notes |
|--------|------|------------|-------|
| `explore_label` | str | `explore.label` | Human-readable explore label |
| `explore_description` | str? | `explore.description` | Explore description; null if unset |
| `explore_group_label` | str? | `explore.group_label` | Navigation menu grouping |
| `explore_hidden` | bool | `explore.hidden` | Whether explore is hidden in nav |
| `explore_connection` | str | `explore.connection_name` | Database connection name |
| `explore_view_name` | str | `explore.view_name` | Base view of the explore |

### Extraction Metadata

| Column | Type | Source | Notes |
|--------|------|--------|-------|
| `extracted_at` | str | Generated | ISO 8601 UTC timestamp of extraction |
| `schema_version` | str | Hardcoded | `"1.1.0"` — incremented on breaking changes |

### Seen-In Enrichment (Computed Post-Extraction)

These columns are computed after all fields are extracted, by grouping on `field_name` across all models/explores. They answer: *"Where is this field visible across the instance?"*

| Column | Type | Computed From | Notes |
|--------|------|--------------|-------|
| `seen_in_model_count` | int | Count distinct `model_name` per `field_name` | 1 = single model, >1 = shared across models |
| `seen_in_explore_count` | int | Count distinct `explore_name` per `field_name` | How many explores expose this field |
| `total_times_used` | int | Sum of `times_used` per `field_name` | Aggregate usage across all appearances |
| `seen_models` | list[str] | Distinct `model_name` values | JSON array of model names |
| `seen_explores` | list[str] | Distinct `model::explore` pairs | JSON array of "model::explore" strings |

**Why this matters:** A field defined in `users.view.lkml` may be visible in 14 explores across 5 models (because those explores all join the `users` view). Without this enrichment, you'd need to aggregate the flat output yourself. These columns make cross-model field lineage queryable in any tool.

**Real example from joonpartner.cloud.looker.com:**
- `users.id`: seen in 5 models, 14 explores, total_times_used=312
- `order_items.count`: seen in 5 models, 10 explores, total_times_used=2078
- 270 field definitions (3%) appear across multiple models
- 8,755 field definitions (97%) are model-local

---

## Evidence: Real API Responses

Verified against `joonpartner.cloud.looker.com` on 2026-04-04.

### Instance Scale

- **Total models with explores:** ~27 models with 1+ explores
- **Total explores:** ~139 across all models
- **Field counts range:** 11 (dvd_rental::film) to 2,340 (cortex_sap_operational::sales_orders)

### Sample: dvd_rental::film (simple)

```json
{
  "name": "film",
  "model_name": "dvd_rental",
  "project_name": "dvd_rental",
  "view_name": "film",
  "connection_name": "joon-sandbox",
  "field_counts": {"dimensions": 8, "measures": 3, "filters": 0, "parameters": 0}
}
```

Sample dimension:
```json
{
  "name": "film.film_id",
  "type": "number",
  "category": "dimension",
  "primary_key": true,
  "view": "film",
  "original_view": "film",
  "sql": "${TABLE}.film_id",
  "source_file": "views/film.view.lkml"
}
```

Sample measure:
```json
{
  "name": "film.count",
  "type": "count",
  "category": "measure",
  "sql": null,
  "view": "film"
}
```

### Sample: thelook_partner::order_items (complex, joined)

```json
{
  "name": "order_items",
  "model_name": "thelook_partner",
  "project_name": "looker_partner_demo",
  "view_name": "order_items",
  "connection_name": "looker_partner_demo",
  "field_counts": {"dimensions": 176, "measures": 55, "filters": 0, "parameters": 0},
  "joins": ["order_facts", "inventory_items", "users", "user_order_facts", "products", "repeat_purchase_facts", "discounts", "distribution_centers"]
}
```

Sample dimension group member:
```json
{
  "name": "discounts.date_date",
  "type": "date_date",
  "category": "dimension",
  "dimension_group": "discounts.date",
  "is_timeframe": true,
  "time_interval": {"name": "day", "count": 1},
  "view": "discounts",
  "original_view": "discounts",
  "source_file": "views/discounts.view.lkml",
  "source_file_path": "looker_partner_demo/views/discounts.view.lkml",
  "sql": "${TABLE}.date",
  "times_used": 33
}
```

### Sample: cortex_sap_operational::sales_orders (massive)

```json
{
  "name": "sales_orders",
  "model_name": "cortex_sap_operational",
  "project_name": "marketplace_https_github_com_looker_open_source_block_cortex_sap_git",
  "field_counts": {"dimensions": 2242, "measures": 97, "filters": 0, "parameters": 1}
}
```

Sample parameter:
```json
{
  "name": "sales_orders.Currency_Required",
  "type": "string",
  "category": "parameter",
  "view": "sales_orders"
}
```

---

## API Fields NOT Included in V1 Output (Conscious Exclusions)

| API Field | Why Excluded |
|-----------|-------------|
| `align` | Display-only, not field metadata |
| `drill_fields` | Complex nested structure, V2 scope |
| `enumerations` | Complex nested, rarely needed |
| `fill_style` | Display-only |
| `fiscal_month_offset` | Derivable from `is_fiscal` |
| `has_allowed_values` | Redundant with enumerations |
| `has_drills_metadata` | Boolean flag, not useful standalone |
| `links` | Complex nested, requires `add_drills_metadata=true` |
| `map_layer` | Geo-specific nested object, V2 scope |
| `sql_case` | Complex nested, derivable from `sql` |
| `field.filters` (on measures) | Measure filter conditions, V2 scope |
| `suggestions` | Runtime data, not metadata |
| `synonyms` | AI synonym suggestions, not core metadata |
| `label_from_parameter` | Rare, derivable |
| `lookml_link` | Instance-specific URL |
| `lookml_expression` | Rarely populated |
| `datatype` | Backend-specific (TIMESTAMP, etc) |
| `convert_tz` | Timezone conversion flag |
| `period_over_period_params` | PoP-specific nested object |
| `time_interval` | Derivable from type + dimension_group |
| `user_attribute_filter_types` | Filter UI metadata |
| `week_start_day` | Instance config, not field metadata |
| `requires_refresh_on_sort` | Query engine detail |
| `strict_value_format` | Rarely relevant |
| `permanent` | Internal use |
| `suggestable` | Runtime behavior |

---

## Swagger vs Reality

Fields present in the real API response but **not documented in the Swagger spec** (or documented differently):

| Field | In Swagger? | In Reality? | Notes |
|-------|-------------|-------------|-------|
| `field.synonyms` | No | Yes (array of strings) | AI-generated, usually empty |
| `field.value_format_name` | Yes | Yes | Named format presets |
| `field.lookml_expression` | No | Yes (usually null) | Rare, LookML expression syntax |
| `field.datatype` | No | Yes (e.g., "TIMESTAMP") | Backend SQL type |
| `field.convert_tz` | No | Yes (boolean) | Timezone conversion flag |

---

## Versioning Policy

| Event | Action |
|-------|--------|
| New output column added | Minor version bump (1.0 → 1.1). Column added with default value |
| Output column removed | Major version bump (1.x → 2.0). Breaking change |
| Column type changed | Major version bump |
| New API field appears in Swagger | Evaluate for inclusion. Add to exclusions list if not needed |
| API field removed | Remove from output, major version bump |
| Column renamed | Major version bump. Old name aliased for one version |

The `schema_version` field in each output row tracks which version of this spec produced it.

---

*FIELD_SPEC v1.0.0 — Established 2026-04-04 from live API analysis of joonpartner.cloud.looker.com*
