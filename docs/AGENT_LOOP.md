# Agent Development Loop

This tool is designed for agent-driven development. AI agents can autonomously implement, verify, and iterate until extraction matches reality.

## The Loop

1. **Read the plan** — Check `FIELD_SPEC.md` for the output contract
2. **Implement** — Write code against the contract
3. **Extract** — Run `looker-fields extract --model <model> --explore <explore>` against a live instance
4. **Verify** — Run `looker-fields verify <model> <explore>` to diff output against API
5. **Fix** — If mismatches found, fix the code
6. **Repeat** — Until zero diff on all sampled explores

## Verification Criteria

- Every field in the API response appears in the output
- No extra fields in the output that aren't in the API response
- All values match exactly (types, nulls, empty strings)
- Grain is unique: no duplicate `(project, model, explore, field)` rows
- All models and explores are enumerated (none missing)

## Common Failure Modes

| Symptom | Likely Cause | Fix |
|---------|-------------|-----|
| Missing fields | Didn't iterate all 4 field types | Check dimensions, measures, filters, parameters |
| Duplicate rows | Same explore in multiple models | Verify grain includes model_name |
| NULL project | Using explore.project_name when field has its own | Use field-level project_name when available |
| Wrong view | Join aliasing | Use `original_view` for source attribution |
| Missing dim groups | Looking for separate array | Dim group members are in dimensions array with `dimension_group != null` |
| Empty sql | Missing permissions | Requires `see_lookml` permission on the API user |
| Extra turtle measures | Looker internal viz fields | Filter by checking for empty view/view_label |

## Recommended Test Explores

| Model | Explore | Fields | Why |
|-------|---------|--------|-----|
| `dvd_rental` | `film` | ~11 | Small, no joins, simple |
| `thelook_partner` | `order_items` | ~231 | Large, 8 joins, dim groups |
| `cortex_sap_operational` | `sales_orders` | ~2340 | Massive enterprise model |

## Agent Checklist Before Declaring Done

- [ ] `looker-fields extract` runs without errors
- [ ] Output file has correct JSONL/CSV/Parquet format
- [ ] Field count matches API for 3+ explores of varying size
- [ ] No duplicate grain rows
- [ ] `verify` command shows zero diff on test explores
- [ ] `--sync` mode works identically to async
