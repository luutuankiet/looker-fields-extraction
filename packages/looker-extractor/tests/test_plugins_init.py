"""Tests for the `lx plugins init` CLI verb (copier wrapper)."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
from typer.testing import CliRunner

from looker_extractor.cli import app

# In click 8.2+ the `mix_stderr` kwarg was removed; use result.output (combined
# stdout+stderr) for assertions that need to see err=True echos.
runner = CliRunner()


def test_copier_importable() -> None:
    """Smoke: copier must be available in the dev env (added to [dev] extra)."""
    from copier import run_copy  # noqa: F401


def test_plugins_init_invokes_copier_with_defaults(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """`lx plugins init <name>` calls copier.run_copy with the template defaults."""
    captured: list[dict[str, Any]] = []

    def fake_run_copy(**kwargs: Any) -> None:
        captured.append(kwargs)
        # Simulate copier creating the dest dir so post-render messages don't
        # confuse the test.
        Path(kwargs["dst_path"]).mkdir(parents=True, exist_ok=True)

    monkeypatch.setattr("copier.run_copy", fake_run_copy)

    dst = tmp_path / "looker-extractor-plugin-demo"
    result = runner.invoke(
        app,
        [
            "plugins",
            "init",
            "looker-extractor-plugin-demo",
            "--output-dir",
            str(dst),
            "--defaults",
        ],
    )

    assert result.exit_code == 0, result.stdout
    assert len(captured) == 1, captured
    call = captured[0]
    assert call["src_path"] == "gh:luutuankiet/looker-extractor.git"
    assert call["vcs_ref"] == "template-v0.1.0"
    assert call["dst_path"] == str(dst)
    assert call["unsafe"] is True
    assert call["defaults"] is True

    # Next-steps guidance present in stdout
    assert "Done. Next steps:" in result.stdout
    assert "uv sync --extra dev" in result.stdout


def test_plugins_init_custom_template(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """--template-url + --template-ref are forwarded to copier."""
    captured: list[dict[str, Any]] = []

    def fake_run_copy(**kwargs: Any) -> None:
        captured.append(kwargs)
        Path(kwargs["dst_path"]).mkdir(parents=True, exist_ok=True)

    monkeypatch.setattr("copier.run_copy", fake_run_copy)

    dst = tmp_path / "my-plugin"
    result = runner.invoke(
        app,
        [
            "plugins",
            "init",
            "my-plugin",
            "--output-dir",
            str(dst),
            "--template-url",
            "file:///tmp/my-template",
            "--template-ref",
            "main",
            "--defaults",
        ],
    )

    assert result.exit_code == 0, result.stdout
    assert captured[0]["src_path"] == "file:///tmp/my-template"
    assert captured[0]["vcs_ref"] == "main"


def test_plugins_init_refuses_non_empty_destination(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """Refuse to scaffold into a non-empty directory (avoid clobber)."""
    dst = tmp_path / "existing"
    dst.mkdir()
    (dst / "sentinel.txt").write_text("already here")

    # Even if copier were called, we want the early-exit; assert it's NOT called.
    def fake_run_copy(**kwargs: Any) -> None:
        pytest.fail("copier should not be invoked when destination is non-empty")

    monkeypatch.setattr("copier.run_copy", fake_run_copy)

    result = runner.invoke(
        app,
        [
            "plugins",
            "init",
            "existing",
            "--output-dir",
            str(dst),
            "--defaults",
        ],
    )

    assert result.exit_code == 1
    assert "exists and is not empty" in result.output


def test_plugins_init_missing_copier_clear_error(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """If copier import fails, print actionable install instructions."""
    import sys

    # Force ImportError on `from copier import run_copy`
    monkeypatch.setitem(sys.modules, "copier", None)

    result = runner.invoke(
        app,
        [
            "plugins",
            "init",
            "some-plugin",
            "--output-dir",
            str(tmp_path / "some-plugin"),
            "--defaults",
        ],
    )

    assert result.exit_code == 1
    assert "copier is not installed" in result.output
    assert "looker-extractor[init]" in result.output
