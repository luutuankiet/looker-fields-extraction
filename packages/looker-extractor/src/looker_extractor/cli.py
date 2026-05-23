"""CLI entry point for looker-extractor.

Post-pivot surface (v0.3.0a0 + plugin platform):
  extract                -- run a plugin's extractor (default plugin: lookml_fields)
  dump <model> <explore> -- raw API dump for one explore (debug)
  refresh-schema         -- fetch live swagger.json and persist to XDG
  info                   -- list models + explore counts for the configured instance
  plugins list           -- list installed plugins
  plugins info <name>    -- show plugin metadata + swagger_seeds
"""

from __future__ import annotations

import asyncio
import logging
from pathlib import Path
from typing import Optional

import typer

app = typer.Typer(
    name="looker-extractor",
    help="Plugin-based extractor for the Looker v4.0 API.",
    no_args_is_help=True,
)
plugins_app = typer.Typer(name="plugins", help="Plugin management.", no_args_is_help=True)
app.add_typer(plugins_app, name="plugins")


@app.command()
def extract(
    plugin: str = typer.Option("lookml_fields", "--plugin", "-p",
        help="Plugin name to invoke (default: lookml_fields)."),
    output: Path = typer.Option("output.jsonl", "--output", "-o", help="Output file path"),
    format: str = typer.Option("jsonl", "--format", "-f", help="Output format: jsonl, parquet"),
    model: Optional[str] = typer.Option(None, "--model", "-m", help="Filter to specific model"),
    explore: Optional[str] = typer.Option(None, "--explore", "-e", help="Filter to specific explore"),
    concurrency: int = typer.Option(10, "--concurrency", "-c", help="Max concurrent API calls"),
    env_file: Path = typer.Option(".env", "--env", help="Path to .env file"),
    verbose: bool = typer.Option(False, "--verbose", "-v", help="Enable debug logging"),
) -> None:
    """Run the specified plugin's extractor."""
    logging.basicConfig(
        level=logging.DEBUG if verbose else logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    from .core.client import LookerClient
    from .core.config import load_settings
    from .output import get_writer
    from .registry import get_plugin

    PluginCls = get_plugin(plugin)
    plugin_inst = PluginCls()
    settings = load_settings(env_file)
    typer.echo(f"Connecting to {settings.looker_base_url} (plugin={plugin})...")

    filters: dict[str, str] = {}
    if model:
        filters["model"] = model
    if explore:
        filters["explore"] = explore

    async def _run() -> None:
        async with LookerClient(settings, concurrency=concurrency) as client:
            writer = get_writer(format, output)
            count = 0
            batch: list[dict] = []
            async for record in plugin_inst.extract(client, filters=filters):
                batch.append(record)
                count += 1
                if len(batch) >= 500:
                    writer.write_records(batch)
                    batch = []
            if batch:
                writer.write_records(batch)
            writer.close()
            typer.echo(f"Done. Extracted {count} records to {output}")

    asyncio.run(_run())


@app.command()
def dump(
    model: str = typer.Argument(..., help="Model name to dump"),
    explore: str = typer.Argument(..., help="Explore name to dump"),
    output: Path = typer.Option(None, "--output", "-o",
        help="Output JSON file (default: dump_<model>_<explore>.json)"),
    env_file: Path = typer.Option(".env", "--env", help="Path to .env file"),
) -> None:
    """Dump the raw API response for one explore to a local JSON file."""
    import json
    from .core.client import LookerClient
    from .core.config import load_settings

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
    output: Optional[Path] = typer.Option(None, "--output", "-o",
        help="Target path for the fresh swagger.json (default: XDG user config)"),
    env_file: Path = typer.Option(".env", "--env", help="Path to .env file"),
) -> None:
    """Fetch live swagger.json from the configured instance and persist it."""
    from .core.client import LookerClient
    from .core.config import load_settings
    from .core.swagger import user_config_path, write_user_config

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
    from .core.client import LookerClient
    from .core.config import load_settings

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
                typer.echo(f"{m['name']:<40} {m.get('project_name', ''):<30} {len(explores):>10}")
            typer.echo("-" * 82)
            typer.echo(f"Total: {len(models)} models, {total_explores} explores")

    asyncio.run(_run())


@plugins_app.command("list")
def plugins_list() -> None:
    """List installed plugins."""
    from .registry import discover_plugins
    found = discover_plugins()
    if not found:
        typer.echo("No plugins installed.")
        return
    typer.echo(f"{'NAME':<25} {'VERSION':<12} DESCRIPTION")
    typer.echo("-" * 80)
    for name in sorted(found):
        cls = found[name]
        typer.echo(f"{cls.name:<25} {cls.version:<12} {cls.description}")


@plugins_app.command("info")
def plugins_info(name: str = typer.Argument(..., help="Plugin name")) -> None:
    """Show detailed info for one plugin."""
    from .registry import get_plugin
    cls = get_plugin(name)
    typer.echo(f"name        : {cls.name}")
    typer.echo(f"version     : {cls.version}")
    typer.echo(f"description : {cls.description}")
    typer.echo(f"swagger_seeds ({len(cls.swagger_seeds)}):")
    for s in cls.swagger_seeds:
        typer.echo(f"  - {s}")


if __name__ == "__main__":
    app()
