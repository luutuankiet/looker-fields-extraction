# looker-fields

Extract field-level metadata from any Looker instance via the API.

Produces an accurate, de-duplicated inventory of every field (dimensions, measures, dimension_groups, filters, parameters) across all models, explores, and views — with **correct model attribution**.

## Why

Parsing raw `.lkml` files cannot resolve `include` statements, leading to model misattribution and Cartesian duplication. This tool extracts the **compiled truth** directly from the Looker API — the final state after Looker's engine has resolved all includes, extensions, and refinements.

## Install

```bash
pip install -e ".[dev]"
```

## Setup

Create a `.env` file:

```env
LOOKER_BASE_URL=https://your-instance.cloud.looker.com
LOOKER_CLIENT_ID=your_client_id
LOOKER_CLIENT_SECRET=your_client_secret
```

## Usage

```bash
# Extract all fields (JSONL output)
looker-fields extract

# Extract as CSV
looker-fields extract --format csv --output fields.csv

# Extract specific model
looker-fields extract --model my_model

# Verify extraction against live API
looker-fields verify my_model my_explore

# Show instance info
looker-fields info
```

## Output

Each row represents one field with grain `(project, model, explore, field_name)`.

Supported formats: JSONL (default), CSV, Parquet, BigQuery.

See [`docs/FIELD_SPEC.md`](docs/FIELD_SPEC.md) for the full output schema.

## Architecture

```
src/looker_fields/
├── cli.py       # typer CLI
├── config.py    # .env + Settings
├── client.py    # Async httpx client
├── schema.py    # Output models + Swagger discovery
├── extract.py   # Core extraction logic
└── output.py    # Multi-sink writers
```

See [`gsd-lite/ARCHITECTURE.md`](gsd-lite/ARCHITECTURE.md) for design decisions.

## License

Apache 2.0
