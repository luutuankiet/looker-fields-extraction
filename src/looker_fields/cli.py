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
) -> None:
    """Verify extracted fields against live API for a specific explore."""
    # TODO: Implement verification
    # 1. Load extracted fields for model::explore from output file
    # 2. Call API for same model::explore
    # 3. Diff field-by-field
    # 4. Report mismatches
    typer.echo(f"Verifying {model}::{explore} against {output}")
    raise NotImplementedError("Verification not yet implemented")


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
