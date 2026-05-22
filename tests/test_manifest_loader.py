"""Pin the precedence chain of manifest.loader.resolve_manifest_source.

Mirrors tests/test_swagger_loader.py exactly — same 7 invariants applied to
the manifest YAML loader (CLI > LOOKER_FIELDS_MANIFEST > XDG > bundled).

The \"bundled validates against ManifestSpec\" test doubles as a sanity check
that the Phase 2 parser output is well-formed.
"""

from __future__ import annotations

import textwrap
from pathlib import Path

import pytest

from looker_fields.manifest import (
    ManifestSourceKind,
    ManifestSpec,
    load_manifest,
    resolve_manifest_source,
    user_config_path,
)


@pytest.fixture(autouse=True)
def _clear_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("LOOKER_FIELDS_MANIFEST", raising=False)


def _write_stub_manifest(path: Path) -> None:
    path.write_text(
        textwrap.dedent(
            """\
            schema_version: \"1.0.0\"
            entity: field
            output_grain: [field_name]
            columns:
              - name: field_name
                type: str
                api_source: field.name
                default: \"\"
                description: stub
            """
        )
    )


def test_default_falls_back_to_bundled() -> None:
    src = resolve_manifest_source()
    assert src.kind is ManifestSourceKind.BUNDLED
    assert src.path is not None and src.path.is_file()
    assert src.path.name == "fields.yaml"


def test_bundled_manifest_validates_against_spec() -> None:
    raw = load_manifest()
    spec = ManifestSpec.model_validate(raw)
    assert spec.entity == "field"
    assert spec.schema_version == "1.0.0"
    # Phase 2 parser emitted 39 cols + 7 derived + 26 exclusions
    assert len(spec.columns) >= 30, "columns sanity floor"
    assert len(spec.exclusions) >= 20, "exclusions sanity floor"
    # All grain columns must be present in columns[]
    column_names = {c.name for c in spec.columns}
    for grain in spec.output_grain:
        assert grain in column_names, f"grain column {grain!r} missing from columns[]"


def test_env_overrides_bundled(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    stub = tmp_path / "env.yaml"
    _write_stub_manifest(stub)
    monkeypatch.setenv("LOOKER_FIELDS_MANIFEST", str(stub))
    src = resolve_manifest_source()
    assert src.kind is ManifestSourceKind.ENV
    assert src.path == stub


def test_cli_beats_env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    env_stub = tmp_path / "env.yaml"
    cli_stub = tmp_path / "cli.yaml"
    _write_stub_manifest(env_stub)
    _write_stub_manifest(cli_stub)
    monkeypatch.setenv("LOOKER_FIELDS_MANIFEST", str(env_stub))
    src = resolve_manifest_source(cli_override=cli_stub)
    assert src.kind is ManifestSourceKind.CLI
    assert src.path == cli_stub


def test_missing_cli_override_raises(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError):
        resolve_manifest_source(cli_override=tmp_path / "does-not-exist.yaml")


def test_missing_env_target_raises(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("LOOKER_FIELDS_MANIFEST", str(tmp_path / "nope.yaml"))
    with pytest.raises(FileNotFoundError):
        resolve_manifest_source()


def test_user_config_path_under_app_name() -> None:
    p = user_config_path()
    assert p.name == "manifest.yaml"
    assert "looker-fields" in str(p)
