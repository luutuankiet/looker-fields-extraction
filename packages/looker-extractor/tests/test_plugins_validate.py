"""Tests for the `lx plugins validate` CLI verb (dry-run contract check)."""

from __future__ import annotations

from typer.testing import CliRunner

from looker_extractor.cli import app

runner = CliRunner()


def test_validate_lookml_fields_passes() -> None:
    """The in-tree reference plugin must always pass validate (regression gate)."""
    result = runner.invoke(app, ["plugins", "validate", "lookml_fields"])
    assert result.exit_code == 0, result.output
    assert "PASS" in result.output
    assert "lookml_fields" in result.output


def test_validate_nonexistent_plugin_fails() -> None:
    """Validate exits 1 with actionable error for missing plugin."""
    result = runner.invoke(app, ["plugins", "validate", "nonexistent_plugin"])
    assert result.exit_code == 1
    assert "FAIL" in result.output
    assert "not found" in result.output


def test_validate_reports_dry_run_count() -> None:
    """Validate prints dry-run row count so author sees what the no-op yielded."""
    result = runner.invoke(app, ["plugins", "validate", "lookml_fields"])
    assert result.exit_code == 0
    assert "dry-run extract(noop_client)" in result.output
    assert "rows (no exceptions)" in result.output
