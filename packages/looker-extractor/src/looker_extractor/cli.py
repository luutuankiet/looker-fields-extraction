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


@plugins_app.command("init")
def plugins_init(
    name: str = typer.Argument(...,
        help="Plugin distribution name (e.g. 'looker-extractor-plugin-users')."),
    template_url: str = typer.Option(
        "gh:luutuankiet/looker-extractor.git", "--template-url",
        help="Copier template source URL or local path."),
    template_ref: str = typer.Option(
        "template-v0.1.0", "--template-ref",
        help="Copier template git ref (tag, branch, SHA)."),
    output_dir: Optional[Path] = typer.Option(
        None, "--output-dir", "-o",
        help="Output directory (default: ./<name>)."),
    defaults: bool = typer.Option(
        False, "--defaults",
        help="Use template defaults for unanswered questions (non-interactive)."),
) -> None:
    """Scaffold a new plugin from the copier template.

    Example:
        lx plugins init looker-extractor-plugin-users

    Requires the `init` extra: pip install 'looker-extractor[init]'
    """
    try:
        from copier import run_copy
    except ImportError:
        typer.echo(
            "Error: copier is not installed. Install scaffold deps with one of:\n"
            "  pip install 'looker-extractor[init]'  # recommended\n"
            "  uv add 'looker-extractor[init]'\n"
            "  pip install copier                    # standalone",
            err=True,
        )
        raise typer.Exit(1)

    dst = output_dir or Path.cwd() / name
    if dst.exists() and any(dst.iterdir()):
        typer.echo(f"Error: destination {dst} exists and is not empty.", err=True)
        raise typer.Exit(1)

    typer.echo(f"Scaffolding plugin {name!r} at {dst}")
    typer.echo(f"  Template: {template_url}@{template_ref}")

    run_copy(
        src_path=template_url,
        dst_path=str(dst),
        vcs_ref=template_ref,
        unsafe=True,  # equivalent to copier CLI --trust
        defaults=defaults,
    )

    try:
        rel = dst.relative_to(Path.cwd())
        shown = str(rel) if str(rel) != "." else str(dst)
    except ValueError:
        shown = str(dst)

    typer.echo("")
    typer.echo("Done. Next steps:")
    typer.echo(f"  cd {shown}")
    typer.echo("  uv sync --extra dev")
    typer.echo("  uv run pytest -v")
    typer.echo("")
    typer.echo("Edit src/<plugin_slug>/plugin.py to implement extract(), then:")
    typer.echo("  uv run looker-extractor plugins list")
    typer.echo("  uv run looker-extractor extract --plugin <entry_point_key> -o out.jsonl")


@plugins_app.command("validate")
def plugins_validate(
    name: str = typer.Argument(..., help="Plugin entry-point key."),
) -> None:
    """Validate a plugin against the SDK contract without hitting the network.

    Checks performed:
      1. Plugin imports + entry-point resolves
      2. Required class attrs (name / version / description / swagger_seeds) populated
      3. extract() is an async generator function
      4. Dry-run: extract(no_op_client) completes without raising

    Useful as a CI gate in third-party plugin repos to catch SDK-contract drift
    between releases without a live Looker instance.
    """
    import asyncio
    import inspect
    from typing import Any

    from .registry import get_plugin

    # ---- 1. Import + entry-point resolve ----
    try:
        cls = get_plugin(name)
    except ValueError as e:
        typer.echo(f"FAIL: {e}", err=True)
        raise typer.Exit(1)

    typer.echo(f"Validating plugin: {cls.__name__} (entry-point: {name!r})")

    errors: list[str] = []

    # ---- 2. Class attrs ----
    if not cls.name:
        errors.append("plugin_class.name is empty")
    if not cls.version:
        errors.append("plugin_class.version is empty")
    if not cls.description:
        errors.append("plugin_class.description is empty")
    if not cls.swagger_seeds:
        errors.append("plugin_class.swagger_seeds is empty")
    elif "Error" not in cls.swagger_seeds or "ValidationError" not in cls.swagger_seeds:
        errors.append(
            "swagger_seeds should include canonical 'Error' + 'ValidationError'"
        )

    # ---- 3. extract is async generator ----
    if not inspect.isasyncgenfunction(cls.extract):
        errors.append(
            f"{cls.__name__}.extract must be an async generator "
            "(declared `async def extract(...)` with `yield` inside)"
        )

    # ---- 4. Dry-run extract with no-op client ----
    class _NoopClient:
        """Returns empty results for any method a plugin might call."""

        async def get(self, path: str, params: Any = None) -> list[dict[str, Any]]:
            return []

        async def all_lookml_models(self) -> list[dict[str, Any]]:
            return []

        async def lookml_model_explore(
            self, model: str, explore: str
        ) -> dict[str, Any]:
            return {
                "name": explore,
                "model_name": model,
                "project_name": "_validate_",
                "fields": {},
            }

        async def get_swagger(self) -> dict[str, Any]:
            return {}

    async def _dry_run() -> int:
        plugin = cls()
        count = 0
        async for _ in plugin.extract(_NoopClient()):
            count += 1
        return count

    try:
        count = asyncio.run(_dry_run())
        typer.echo(f"  dry-run extract(noop_client) -> {count} rows (no exceptions)")
    except Exception as e:
        errors.append(
            f"dry-run extract(noop_client) raised "
            f"{type(e).__name__}: {e}"
        )

    # ---- Report ----
    if errors:
        typer.echo(f"\nFAIL: {name!r} has {len(errors)} contract issue(s):", err=True)
        for e in errors:
            typer.echo(f"  - {e}", err=True)
        raise typer.Exit(1)

    typer.echo(f"\nPASS: {cls.name!r} v{cls.version} - SDK contract OK")


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
