"""Pin the precedence chain of _swagger.loader.resolve_swagger_source.

Order: CLI flag > LOOKER_SWAGGER_PATH env > XDG > bundled baseline.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from looker_fields._swagger import (
    SwaggerSourceKind,
    load_swagger,
    resolve_swagger_source,
    user_config_path,
)


@pytest.fixture(autouse=True)
def _clear_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("LOOKER_SWAGGER_PATH", raising=False)


def _write_stub_spec(path: Path) -> None:
    path.write_text(json.dumps({"openapi": "3.0.0", "components": {"schemas": {}}}))


def test_default_falls_back_to_bundled() -> None:
    src = resolve_swagger_source()
    assert src.kind is SwaggerSourceKind.BUNDLED
    assert src.path is not None and src.path.is_file()
    assert src.path.name == "baseline.json"


def test_bundled_baseline_is_valid_openapi3() -> None:
    spec = load_swagger()
    assert spec.get("openapi", "").startswith("3.")
    schemas = spec["components"]["schemas"]
    assert "LookmlModelExplore" in schemas
    assert "LookmlModelExploreField" in schemas


def test_env_overrides_bundled(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    stub = tmp_path / "env.json"
    _write_stub_spec(stub)
    monkeypatch.setenv("LOOKER_SWAGGER_PATH", str(stub))
    src = resolve_swagger_source()
    assert src.kind is SwaggerSourceKind.ENV
    assert src.path == stub


def test_cli_beats_env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    env_stub = tmp_path / "env.json"
    cli_stub = tmp_path / "cli.json"
    _write_stub_spec(env_stub)
    _write_stub_spec(cli_stub)
    monkeypatch.setenv("LOOKER_SWAGGER_PATH", str(env_stub))
    src = resolve_swagger_source(cli_override=cli_stub)
    assert src.kind is SwaggerSourceKind.CLI
    assert src.path == cli_stub


def test_missing_cli_override_raises(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError):
        resolve_swagger_source(cli_override=tmp_path / "does-not-exist.json")


def test_missing_env_target_raises(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("LOOKER_SWAGGER_PATH", str(tmp_path / "nope.json"))
    with pytest.raises(FileNotFoundError):
        resolve_swagger_source()


def test_user_config_path_under_app_name() -> None:
    p = user_config_path()
    assert p.name == "swagger.json"
    assert "looker-fields" in str(p)
