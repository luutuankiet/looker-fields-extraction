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
    manifest_path: Optional[Path] = typer.Option(
        None,
        "--manifest-path",
        help="Path to manifest YAML override (default: 4-step chain CLI>env>XDG>bundled)",
    ),
) -> None:
    """Extract all field metadata from the configured Looker instance."""
    logging.basicConfig(
        level=logging.DEBUG if verbose else logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    from .config import load_settings
    from .client import LookerClient
    from .extract import extract_all
    from .manifest import ManifestSpec, load_manifest
    from .output import get_writer
    from .schema import FieldRecord

    settings = load_settings(env_file)
    typer.echo(f"Connecting to {settings.looker_base_url}...")

    manifest = ManifestSpec.model_validate(load_manifest(manifest_path))

    async def _run() -> None:
        async with LookerClient(settings, concurrency=concurrency) as client:
            all_records: list[FieldRecord] = []
            async for record in extract_all(
                client,
                model_filter=model,
                explore_filter=explore,
                manifest=manifest,
            ):
                all_records.append(record)

            from .extract import enrich_seen_in

            enrich_seen_in(all_records)

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
    manifest_path: Optional[Path] = typer.Option(
        None,
        "--manifest-path",
        help="Path to manifest YAML override (default: 4-step resolution chain)",
    ),
) -> None:
    """Verify extracted fields against live API for a specific explore.

    Re-fetches the explore from the API, re-runs the extractor's flatten_explore
    over the fresh response (using the same manifest), and diffs the result
    against ``--output``. Exit 0 if the diff is clean, exit 1 otherwise.
    """
    logging.basicConfig(
        level=logging.DEBUG if verbose else logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    from .config import load_settings
    from .client import LookerClient
    from .manifest import ManifestSpec, load_manifest
    from .verify import diff_extracted_vs_raw, load_extracted_records

    if not output.exists():
        typer.echo(f"error: extraction output not found: {output}", err=True)
        raise typer.Exit(2)

    settings = load_settings(env_file)
    typer.echo(f"Verifying {model}::{explore} against {output}")

    manifest = ManifestSpec.model_validate(load_manifest(manifest_path))

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
        report = diff_extracted_vs_raw(extracted, raw, model, manifest=manifest)
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
    """Fetch live swagger.json, persist it, run both drift detectors.

    Drift v1: swagger-vs-extractor-required-paths (REQUIRED_*_PROPERTIES).
    Drift v2: manifest-vs-swagger (api_source paths the swagger no longer carries).
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

        from .manifest import ManifestSpec, load_manifest, validate_manifest_drift

        manifest = ManifestSpec.model_validate(load_manifest())
        m_warnings = validate_manifest_drift(manifest, spec)
        if m_warnings:
            typer.echo(f"\n{len(m_warnings)} manifest drift warning(s):")
            for w in m_warnings:
                typer.echo(f"  WARN: {w}")
        else:
            typer.echo("No manifest drift warnings.")

    asyncio.run(_run())


@app.command("refresh-manifest")
def refresh_manifest(
    env_file: Path = typer.Option(".env", "--env", help="Path to .env file"),
    manifest_path: Optional[Path] = typer.Option(
        None,
        "--manifest-path",
        help="Path to manifest YAML to check (default: 4-step resolution chain)",
    ),
) -> None:
    """Diff manifest against live swagger; report drift + suggest additions.

    Surfaces two directions of drift:
      1. Manifest -> Swagger: api_source paths the swagger no longer carries (drift v2)
      2. Swagger -> Manifest: swagger attrs the manifest does not reference yet

    Does NOT auto-write. Use suggestions to manually edit the manifest YAML
    (and KNOWN_API_OVERRIDES in scripts/parse_field_spec_to_manifest.py if
    you want regen-from-spec to preserve the fix).
    """
    from .config import load_settings
    from .client import LookerClient
    from .manifest import (
        ManifestSpec,
        load_manifest,
        suggest_manifest_additions,
        validate_manifest_drift,
    )

    settings = load_settings(env_file)
    typer.echo(f"Connecting to {settings.looker_base_url}...")

    async def _run() -> None:
        async with LookerClient(settings) as client:
            spec = await client.get_swagger()
        manifest = ManifestSpec.model_validate(load_manifest(manifest_path))

        drift_warnings = validate_manifest_drift(manifest, spec)
        if drift_warnings:
            typer.echo(
                f"\n{len(drift_warnings)} drift warning(s) -- manifest references "
                f"missing swagger paths:"
            )
            for w in drift_warnings:
                typer.echo(f"  WARN: {w}")
        else:
            typer.echo("\nNo drift: every manifest api_source resolves against swagger.")

        additions = suggest_manifest_additions(manifest, spec)
        if additions:
            typer.echo(
                f"\n{len(additions)} addition suggestion(s) -- swagger declares but "
                f"manifest does not reference:"
            )
            for a in additions:
                typer.echo(f"  + {a}")
        else:
            typer.echo("\nNo additions: manifest covers all swagger paths.")

    asyncio.run(_run())


@app.command("regen-types")
def regen_types(
    output: Optional[Path] = typer.Option(
        None,
        "--output",
        "-o",
        help="Target path for regenerated types.py (default: XDG user cache)",
    ),
    manifest_path: Optional[Path] = typer.Option(
        None,
        "--manifest-path",
        help="Path to manifest YAML override (default: 4-step resolution chain)",
    ),
) -> None:
    """Regenerate FieldRecord from the manifest, writing to XDG cache by default.

    The regenerated types.py is dynamic-imported on next startup, replacing
    the bundled FieldRecord. Use this when overrides extend or modify the
    manifest schema and you want downstream consumers (pydantic validation,
    JSONL serialization) to honor the override.

    To revert to bundled: rm ~/.cache/looker-fields/_fieldrecord/types.py
    """
    import platformdirs

    from ._fieldrecord.codegen import regenerate
    from .manifest.loader import resolve_manifest_source

    source = resolve_manifest_source(manifest_path)
    assert source.path is not None
    typer.echo(f"Manifest source: {source}")

    target = output or (
        Path(platformdirs.user_cache_dir("looker-fields", appauthor=False))
        / "_fieldrecord"
        / "types.py"
    )

    path, bytes_written = regenerate(source.path, target)
    typer.echo(f"Wrote {path} ({bytes_written} bytes)")
    typer.echo(
        "Next run will dynamic-import this file instead of the bundled types.py.\n"
        f"To revert: rm {path}"
    )


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
