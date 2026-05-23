"""CLI entry point for looker-fields.

Post-pivot surface (v0.3.0a0):
  extract        -- stream explore-field passthru dicts to JSONL or Parquet
  dump           -- one-shot raw API dump for a single explore (debugging)
  refresh-schema -- fetch live swagger.json and persist to XDG
  info           -- list models + explore counts for the configured instance

Gone (pre-pivot, deprecated):
  verify           -- projection-layer dedup audit (no projection any more)
  refresh-manifest -- manifest-driven column drift detection (no columns)
  regen-types      -- FieldRecord codegen (no FieldRecord)
"""

from __future__ import annotations

import asyncio
import logging
from pathlib import Path
from typing import Optional

import typer

app = typer.Typer(
    name="looker-fields",
    help="Extract entity metadata from any Looker instance via the API (passthru).",
    no_args_is_help=True,
)


@app.command()
def extract(
    output: Path = typer.Option("output.jsonl", "--output", "-o", help="Output file path"),
    format: str = typer.Option("jsonl", "--format", "-f", help="Output format: jsonl, parquet"),
    model: Optional[str] = typer.Option(None, "--model", "-m", help="Filter to specific model"),
    explore: Optional[str] = typer.Option(None, "--explore", "-e", help="Filter to specific explore"),
    concurrency: int = typer.Option(10, "--concurrency", "-c", help="Max concurrent API calls"),
    env_file: Path = typer.Option(".env", "--env", help="Path to .env file"),
    verbose: bool = typer.Option(False, "--verbose", "-v", help="Enable debug logging"),
) -> None:
    """Extract explore-field metadata from the configured Looker instance.

    Output is one row per field, passthru-shaped from the LookmlModelExploreField
    pydantic model. Nested structures (enumerations, links, time_interval, etc.)
    are preserved as nested JSON/Parquet structs. A minimal lineage envelope
    (``_extract_model_name``, ``_extract_explore_name``,
    ``_extract_explore_project_name``, ``_extract_field_category``) is added
    per row so the warehouse can join back to model/explore without inspecting
    nested structures.
    """
    logging.basicConfig(
        level=logging.DEBUG if verbose else logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    from .client import LookerClient
    from .config import load_settings
    from .extract import extract_explore_fields
    from .output import get_writer

    settings = load_settings(env_file)
    typer.echo(f"Connecting to {settings.looker_base_url}...")

    async def _run() -> None:
        async with LookerClient(settings, concurrency=concurrency) as client:
            writer = get_writer(format, output)
            count = 0
            batch: list[dict] = []
            async for record in extract_explore_fields(
                client,
                model_filter=model,
                explore_filter=explore,
            ):
                batch.append(record)
                count += 1
                if len(batch) >= 500:
                    writer.write_records(batch)
                    batch = []
            if batch:
                writer.write_records(batch)
            writer.close()
            typer.echo(f"Done. Extracted {count} fields to {output}")

    asyncio.run(_run())


@app.command()
def dump(
    model: str = typer.Argument(..., help="Model name to dump"),
    explore: str = typer.Argument(..., help="Explore name to dump"),
    output: Path = typer.Option(
        None,
        "--output",
        "-o",
        help="Output JSON file (default: dump_<model>_<explore>.json)",
    ),
    env_file: Path = typer.Option(".env", "--env", help="Path to .env file"),
) -> None:
    """Dump the raw API response for one explore to a local JSON file."""
    import json

    from .client import LookerClient
    from .config import load_settings

    settings = load_settings(env_file)
    target = output or Path(f"dump_{model}_{explore}.json")

    async def _run() -> None:
        async with LookerClient(settings) as client:
            raw = await client.lookml_model_explore(model, explore)
        target.write_text(json.dumps(raw, indent=2, sort_keys=True))
        typer.echo(f"Wrote {target} ({target.stat().st_size // 1024} KB)")

    asyncio.run(_run())


@app.command("refresh-schema")
def refresh_schema(
    output: Optional[Path] = typer.Option(
        None,
        "--output",
        "-o",
        help="Target path for the fresh swagger.json (default: XDG user config)",
    ),
    env_file: Path = typer.Option(".env", "--env", help="Path to .env file"),
) -> None:
    """Fetch live swagger.json from the configured instance and persist it.

    Per-instance swagger drift detection (vs bundled baseline) lands in
    Phase 2 -- this command currently just persists the spec.
    """
    from ._swagger import user_config_path, write_user_config
    from .client import LookerClient
    from .config import load_settings

    settings = load_settings(env_file)
    target = output or user_config_path()

    async def _run() -> None:
        async with LookerClient(settings) as client:
            spec = await client.get_swagger()
        written = write_user_config(spec, target)
        typer.echo(f"Wrote {written} ({written.stat().st_size // 1024} KB)")

    asyncio.run(_run())


@app.command()
def info(
    env_file: Path = typer.Option(".env", "--env", help="Path to .env file"),
) -> None:
    """Show instance info: models, explores, field counts."""
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s: %(message)s")
    from .client import LookerClient
    from .config import load_settings

    settings = load_settings(env_file)

    async def _run() -> None:
        async with LookerClient(settings) as client:
            models = await client.all_lookml_models()
            typer.echo(f"\nConnected to: {settings.looker_base_url}")
            typer.echo(f"{'Model':<40} {'Project':<30} {'Explores':>10}")
            typer.echo("-" * 82)
            total_explores = 0
            for m in sorted(models, key=lambda x: len(x.get('explores', [])), reverse=True):
                explores = m.get('explores', [])
                if not explores:
                    continue
                total_explores += len(explores)
                typer.echo(
                    f"{m['name']:<40} {m.get('project_name', ''):<30} {len(explores):>10}"
                )
            typer.echo("-" * 82)
            typer.echo(f"Total: {len(models)} models, {total_explores} explores")

    asyncio.run(_run())


if __name__ == "__main__":
    app()
