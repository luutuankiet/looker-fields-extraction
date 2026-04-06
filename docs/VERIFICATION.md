# Verification Guide

## Quick Verify

```bash
# Extract fields for a specific model/explore
looker-fields extract --model dvd_rental --explore film -o test_output.jsonl

# Verify against live API
looker-fields verify dvd_rental film --output test_output.jsonl
```

## Manual Verification Steps

1. Pick a model::explore pair (start small: `dvd_rental::film` has ~11 fields)
2. Run extraction for just that pair
3. Call the API directly and save the raw response
4. Compare:
   - Field count matches (dimensions + measures + filters + parameters)
   - Every `field_name` appears in output
   - `category` is correct for each field
   - View attribution is correct (especially for joined views)
   - `dimension_group` members are present

## What to Diff

For each field, verify these critical columns:

| Column | What to Check |
|--------|---------------|
| `field_name` | Must match API `name` exactly |
| `category` | dimension/measure/filter/parameter |
| `field_type` | LookML type string |
| `view_name` | Which view this field belongs to |
| `original_view` | Where actually defined (join alias cases) |
| `hidden` | Must match API value |
| `primary_key` | Must match |
| `dimension_group` | null vs group name |
| `times_used` | Integer, match API |

## Recommended Test Matrix

| Model | Explore | Dims | Measures | Filters | Params | Joins |
|-------|---------|------|----------|---------|--------|-------|
| `dvd_rental` | `film` | 8 | 3 | 0 | 0 | 0 |
| `thelook_partner` | `order_items` | 176 | 55 | 0 | 0 | 8 |
| `cortex_sap_operational` | `sales_orders` | 2242 | 97 | 0 | 1 | many |
| `fivetran_joon_4_joon` | `fct__hubspot__deals` | varies | varies | varies | varies | varies |

## Edge Cases to Test

1. **Dimension groups** — Members appear as individual dimensions with `dimension_group` set
2. **Joined views** — `view` may differ from `original_view` when `from:` is used
3. **Hidden fields** — Should still appear in output with `hidden: true`
4. **Dynamic fields** — Created via `dynamic_fields` parameter, `dynamic: true`
5. **Turtle measures** — Looker visualization measures with empty view/scope
6. **Parameters** — Appear in `fields.parameters` array with `category: parameter`
7. **Measure filters** — `field.filters` array on measures (different from fieldset.filters)
