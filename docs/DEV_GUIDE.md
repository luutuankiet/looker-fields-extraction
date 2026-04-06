# Developer Guide

## Setup

1. Clone the repo:
   ```bash
   git clone <repo-url>
   cd looker-fields-extraction
   ```

2. Create a virtual environment (Python 3.11+):
   ```bash
   python3.11 -m venv .venv
   source .venv/bin/activate
   ```

3. Install in development mode:
   ```bash
   pip install -e ".[dev]"
   ```

4. Create `.env` file:
   ```env
   LOOKER_BASE_URL=https://your-instance.cloud.looker.com
   LOOKER_CLIENT_ID=your_client_id
   LOOKER_CLIENT_SECRET=your_client_secret
   ```

## Running

```bash
# Extract all fields (default: JSONL output)
looker-fields extract

# Extract with specific format
looker-fields extract --format csv --output fields.csv

# Extract specific model only
looker-fields extract --model thelook_partner

# Synchronous mode (for debugging)
looker-fields extract --sync

# Show instance info
looker-fields info

# Verify extraction
looker-fields verify thelook_partner order_items
```

## Project Structure

```
src/looker_fields/
|-- __init__.py      # Package version
|-- cli.py           # typer CLI entry point
|-- config.py        # .env loading, Settings model
|-- client.py        # Async Looker API client (httpx)
|-- schema.py        # Swagger discovery + output models
|-- extract.py       # Core extraction logic
|-- output.py        # Multi-sink writers (JSONL, CSV, Parquet, BQ)
```

## Key Concepts

- **Swagger-first**: The tool fetches `/api/4.0/swagger.json` at startup for schema discovery and drift detection
- **Streaming**: Fields are processed one explore at a time, never all in memory
- **Output grain**: Each row is unique by `(project_name, model_name, explore_name, field_name)`
- **Verification mode**: Compare extracted output against live API calls to ensure accuracy

## Module Responsibilities

| Module | Responsibility | Dependencies |
|--------|---------------|--------------|
| `cli.py` | Parse args, orchestrate pipeline | config, client, extract, output |
| `config.py` | Load .env, validate settings | pydantic-settings |
| `client.py` | HTTP requests, auth, rate limiting | httpx, config |
| `schema.py` | Output data model, swagger parsing | pydantic, orjson |
| `extract.py` | Flatten API responses to records | client, schema |
| `output.py` | Write records to various formats | schema, pyarrow, bigquery |

## Running Tests

```bash
pytest tests/
pytest tests/ -v  # verbose
```

## Code Style

- Python 3.11+ features (match/case, type unions, tomllib)
- Ruff for linting and formatting: `ruff check . && ruff format .`
- Pydantic v2 for all data models
- Type hints on all public functions
- Docstrings on all public functions and classes
