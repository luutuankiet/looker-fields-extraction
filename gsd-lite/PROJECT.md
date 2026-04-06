# looker-fields-extraction

## What This Is

An open-source Python CLI tool that extracts field-level metadata from any Looker instance via the Looker API. It produces an accurate, de-duplicated inventory of every field (dimensions, measures, dimension_groups, filters) across all models, explores, and views — with **correct model attribution**.

This tool exists because the conventional approach (parsing raw `.lkml` files with the `lkml` Python library) **cannot resolve `include` statements**, leading to silent model misattribution and Cartesian duplication when merging with API-sourced model-explore mappings.

Instead of parsing text files, this tool extracts the **compiled truth** directly from the Looker API — the final state after Looker's engine has resolved all includes, extensions, and refinements.

## Core Value

**A single CLI command that produces a 100% accurate field inventory from any Looker instance, with correct model-explore-view-field lineage, in multiple output formats (JSONL, CSV, Parquet, BigQuery).**

## Success Criteria

V1 succeeds when:

- [ ] Tool connects to any Looker instance via `.env` or CLI flags
- [ ] Swagger spec is fetched dynamically to discover API response shape
- [ ] Every `model::explore` is enumerated and its fields extracted
- [ ] Output grain is one row per `(project, model_name, explore_name, field_name)` — unique, no duplicates
- [ ] Output matches the live Looker API response with zero diff (verified against real instance)
- [ ] Supports JSONL, CSV, Parquet, and BigQuery output sinks
- [ ] Async extraction with configurable concurrency and `--sync` fallback
- [ ] Agent dev loop documented: any AI agent can pick up, implement, verify, iterate autonomously

## Context

### Why This Exists

The problem was discovered during a consulting engagement analyzing a client's `looker_repo.py` pipeline — a ~1500-line Python script that parses raw `.lkml` files from 20 hub-spoke repositories and merges with Looker API data.

**The root cause:** The `lkml` Python library parses raw LookML strings but has no concept of how Looker's engine compiles multiple files together. It cannot resolve `include` statements. When an explore appears in multiple models (via different `include` patterns), the merge creates a Cartesian product.

**The impact (proven with BQ evidence):**
- 13.79% Cartesian duplication from model-explore merge
- 7.71% NULL model attribution
- 21.5% total bad data
- 25.7M ghost usage events (fields showing zero usage that are actively queried)

**The fix:** Extract from the Looker API directly. Each `sdk.lookml_model_explore(model, explore)` call returns the fully-resolved explore FOR THAT MODEL — no ambiguity, no Cartesian product.

### Design Principles

1. **Swagger-first:** Fetch the OpenAPI spec from the target server at startup. Derive field mappings from the spec, not hardcoded paths. Detect schema drift across Looker API versions.
2. **Verify against reality:** Every extraction run can be verified against the live API. The tool includes a verification mode that diffs output against direct API calls.
3. **Multi-sink from day one:** JSONL (dev default), CSV (IDE-visual), Parquet (columnar/BQ-optimized), BigQuery (production deployment).
4. **Agent-developable:** The `docs/` directory contains machine-readable guidance so AI agents can autonomously implement, verify, and iterate until extraction matches reality.

## Constraints

- **Python 3.11+** — for modern asyncio, tomllib, type hints
- **Looker API 4.0** — current stable API version (tool adapts via Swagger discovery)
- **Rate limits** — must respect Looker API rate limits; configurable concurrency with semaphore
- **Memory** — streaming architecture; never hold all responses in memory at once

## Stakeholders

| Who | Role |
|-----|------|
| **Us** | Maintainers, primary developers |
| **AI agents** | Autonomous development loop participants |
| **Open-source community** | Future contributors, users with their own Looker instances |
| **Client (indirect)** | This tool, once validated, can replace their broken pipeline |

---

*Open-source project. No client dependency. No approval gates.*
