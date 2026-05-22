"""CLI entry point for looker-fields."""

from __future__ import annotations

import asyncio
import logging
from pathlib import Path
from typing import Optional

import typer

app = typer.Typer(
    name="looker-fields",
    help="Extract field-level metadata from any Looker instance via the API.",
    no_args_is_help=True,
)


@app.command()
def extract(
    output: Path = typer.Option("output.jsonl", "--output", "-o", help="Output file path"),
    format: str = typer.Option("jsonl", "--format", "-f", help="Output format: jsonl, csv, parquet"),
    model: Optional[str] = typer.Option(None, "--model", "-m", help="Filter to specific model"),
    explore: Optional[str] = typer.Option(None, "--explore", "-e", help="Filter to specific explore"),
    concurrency: int = typer.Option(10, "--concurrency", "-c", help="Max concurrent API calls"),
    sync: bool = typer.Option(False, "--sync", help="Use synchronous mode (no async)"),
    env_file: Path = typer.Option(".env", "--env", help="Path to .env file"),
    verbose: bool = typer.Option(False, "--verbose", "-v", help="Enable debug logging"),
) -> None:
    """Extract all field metadata from the configured Looker instance."""
    logging.basicConfig(
        level=logging.DEBUG if verbose else logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    from .config import load_settings
    from .client import LookerClient
    from .extract import extract_all
    from .output import get_writer
    from .schema import FieldRecord

    settings = load_settings(env_file)
    typer.echo(f"Connecting to {settings.looker_base_url}...")

    async def _run() -> None:
        async with LookerClient(settings, concurrency=concurrency) as client:
            # Collect all records first for seen-in enrichment
            all_records: list[FieldRecord] = []
            async for record in extract_all(
                client, model_filter=model, explore_filter=explore
            ):
                all_records.append(record)

            # Enrich with cross-model/explore visibility stats
            from .extract import enrich_seen_in

            enrich_seen_in(all_records)

            # Write enriched output
            writer = get_writer(format, output)
            writer.write_records(all_records)
            writer.close()
            typer.echo(f"Done. Extracted {len(all_records)} fields to {output}")

    asyncio.run(_run())


@app.command()
def verify(
    model: str = typer.Argument(..., help="Model name to verify"),
    explore: str = typer.Argument(..., help="Explore name to verify"),
    output: Path = typer.Option(
        "output.jsonl", "--output", "-o", help="Extraction output to verify against"
    ),
    env_file: Path = typer.Option(".env", "--env", help="Path to .env file"),
    verbose: bool = typer.Option(False, "--verbose", "-v", help="Enable debug logging"),
) -> None:
    """Verify extracted fields against live API for a specific explore.

    Re-fetches the explore from the API, re-runs the extractor's flatten_explore
    over the fresh response, and diffs the result against ``--output``. Exit 0
    if the diff is clean, exit 1 otherwise.
    """
    logging.basicConfig(
        level=logging.DEBUG if verbose else logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    from .config import load_settings
    from .client import LookerClient
    from .verify import diff_extracted_vs_raw, load_extracted_records

    if not output.exists():
        typer.echo(f"error: extraction output not found: {output}", err=True)
        raise typer.Exit(2)

    settings = load_settings(env_file)
    typer.echo(f"Verifying {model}::{explore} against {output}")

    async def _run() -> int:
        extracted = load_extracted_records(output, model, explore)
        if not extracted:
            typer.echo(
                f"error: no records found in {output} for {model}::{explore}",
                err=True,
            )
            return 2
        async with LookerClient(settings) as client:
            raw = await client.lookml_model_explore(model, explore)
        report = diff_extracted_vs_raw(extracted, raw, model)
        typer.echo(report.render())
        return 0 if report.is_clean else 1

    raise typer.Exit(asyncio.run(_run()))


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
    """Dump the raw API response for one explore to a local JSON file.

    Useful for offline development, debugging extractor behavior, and feeding
    the verifier in air-gapped CI.
    """
    import json

    from .config import load_settings
    from .client import LookerClient

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
    """Fetch live swagger.json from the configured Looker instance and persist it.

    Default target is the XDG user config path. Once written, the loader's
    XDG step picks it up automatically on the next run (precedence chain:
    CLI flag > LOOKER_SWAGGER_PATH env > XDG > bundled baseline).

    After writing, runs ``validate_schema_drift`` against the new spec and
    prints any drift warnings.
    """
    from .config import load_settings
    from .client import LookerClient
    from ._swagger import user_config_path, write_user_config
    from .schema import validate_schema_drift

    settings = load_settings(env_file)
    target = output or user_config_path()

    async def _run() -> None:
        async with LookerClient(settings) as client:
            spec = await client.get_swagger()
        written = write_user_config(spec, target)
        typer.echo(f"Wrote {written} ({written.stat().st_size // 1024} KB)")
        warnings = validate_schema_drift(spec)
        if warnings:
            typer.echo(f"\n{len(warnings)} drift warning(s) vs extractor's required-paths contract:")
            for w in warnings:
                typer.echo(f"  WARN: {w}")
        else:
            typer.echo("No drift warnings.")

    asyncio.run(_run())


@app.command()
def info(
    env_file: Path = typer.Option(".env", "--env", help="Path to .env file"),
) -> None:
    """Show instance info: models, explores, field counts."""
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s: %(message)s")
    from .config import load_settings
    from .client import LookerClient

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
