#!/usr/bin/env python3
"""Parse docs/FIELD_SPEC.md → src/looker_fields/manifest/fields.yaml.

Phase 2 of the Manifest-Native Architecture pivot.

The manifest IS the source of truth for the FieldRecord output contract:
  columns[]         — direct extractions from Looker API responses
  derived_columns[] — generated / hardcoded / post-extraction-enriched
  exclusions[]      — conscious omissions, documented per V1 scope

Output is the BUNDLED DEFAULT manifest. User overrides via
~/.config/looker-fields/manifest.yaml or LOOKER_FIELDS_MANIFEST env
(see manifest/loader.py — Phase 3).

Idempotent — re-run after editing FIELD_SPEC.md.

Usage:
    .venv/bin/python scripts/parse_field_spec_to_manifest.py [--out PATH]
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path
from typing import Any

import yaml

SCHEMA_VERSION = "1.0.0"
ENTITY = "field"
OUTPUT_GRAIN = ["project_name", "model_name", "explore_name", "field_name"]

# Defaults that aren't derivable from type alone — extracted from
# the legacy hand-rolled extract.flatten_field. Bool columns that
# don't appear here default to False (per TYPE_DEFAULTS).
KNOWN_DEFAULT_OVERRIDES: dict[str, Any] = {
    "sortable": True,
    "can_filter": True,
}

# Per-name api_source overrides: forces a column to read from a different
# manifest path than FIELD_SPEC.md declares. Used when the docs describe the
# "intended" source but the runtime needs a different (more reliable) one.
# Applied AFTER FIELD_SPEC parsing -- keeps regen idempotent on fixes that
# exist outside the spec doc.
#
# Set a value to None to STRIP that key from the parsed entry (use for
# fallback_source when the override eliminates the need for a fallback).
KNOWN_API_OVERRIDES: dict[str, dict[str, Any]] = {
    # FIELD_SPEC.md docs "explore.model_name" but the API response's nested
    # explore.model_name is nullable per swagger and was the root cause of
    # the duplication bug. context.model_name is the extraction loop's
    # iteration variable -- always populated, never null.
    "model_name": {"api_source": "context.model_name", "fallback_source": None},
}

# Type → default-value mapping (when no override).
TYPE_DEFAULTS: dict[str, Any] = {
    "str": "",
    "str?": None,
    "bool": False,
    "int": 0,
    "list[str]": [],
}

REPO_ROOT = Path(__file__).resolve().parent.parent
SPEC_PATH = REPO_ROOT / "docs" / "FIELD_SPEC.md"
DEFAULT_OUT = REPO_ROOT / "src" / "looker_fields" / "manifest" / "fields.yaml"

# Sanity floors — abort if parse produces less than this.
MIN_COLUMN_COUNT = 30          # actual ~39 direct API columns
EXPECTED_EXCLUSION_COUNT = 26  # from FIELD_SPEC "API Fields NOT Included"


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument(
        "--spec",
        type=Path,
        default=SPEC_PATH,
        help=f"Path to FIELD_SPEC.md (default: {SPEC_PATH.relative_to(REPO_ROOT)})",
    )
    p.add_argument(
        "--out",
        type=Path,
        default=DEFAULT_OUT,
        help=f"Output YAML path (default: {DEFAULT_OUT.relative_to(REPO_ROOT)})",
    )
    return p.parse_args()


def _strip_backticks(s: str) -> str:
    """Strip a single pair of backticks if present."""
    s = s.strip()
    if s.startswith("`") and s.endswith("`"):
        return s[1:-1]
    return s


def _parse_api_source_cell(cell: str) -> tuple[str | None, str | None]:
    """Extract (primary, fallback) API path tokens from an \"API Source\" cell.

    Returns (None, None) if the cell describes a derived column.

    Patterns handled:
        `field.X`                       → ("field.X", None)
        `field.X` or `explore.Y`        → ("field.X", "explore.Y")
        "Generated" / "Hardcoded"       → (None, None)  (derived column)
    """
    cell = cell.strip()
    tokens = re.findall(r"`([^`]+)`", cell)
    if not tokens:
        return None, None
    api_tokens = [
        t for t in tokens
        if "." in t and t.split(".", 1)[0] in ("field", "explore")
    ]
    if not api_tokens:
        return None, None
    primary = api_tokens[0]
    fallback = api_tokens[1] if len(api_tokens) > 1 else None
    return primary, fallback


def _split_table_row(line: str) -> list[str] | None:
    """Parse a markdown table row → list of cells, or None if not a row."""
    line = line.strip()
    if not line.startswith("|") or not line.endswith("|"):
        return None
    return [c.strip() for c in line[1:-1].split("|")]


def _is_header_row(cells: list[str]) -> bool:
    return cells[:1] == ["Column"] or cells[:1] == ["API Field"]


def _is_separator_row(cells: list[str]) -> bool:
    return all(set(c) <= set("-: ") and "-" in c for c in cells)


def _default_for(name: str, type_: str) -> Any:
    if name in KNOWN_DEFAULT_OVERRIDES:
        return KNOWN_DEFAULT_OVERRIDES[name]
    return TYPE_DEFAULTS.get(type_, None)


def _derived_deterministic(expression: str) -> bool:
    """Heuristic: is the derivation reproducible from input alone?

    Generated timestamps are non-deterministic (depend on wall clock).
    Hardcoded / Count / Sum / Distinct expressions are deterministic.
    """
    expr = expression.strip()
    if expr.lower() == "generated":
        return False
    if expr.lower() == "hardcoded":
        return True
    if any(kw in expr for kw in ("Count distinct", "Sum of", "Distinct ")):
        return True
    return False


def parse_spec(spec_text: str) -> tuple[list[dict], list[dict], list[str]]:
    """Walk FIELD_SPEC.md once, extract (columns, derived_columns, exclusions).

    Routing rule (driven by table header column 3):
        "API Source"    → columns[]          (direct API extractions)
        "Source"        → derived_columns[]  (Generated / Hardcoded)
        "Computed From" → derived_columns[]  (post-extraction enrichment)
    """
    columns: list[dict] = []
    derived: list[dict] = []
    exclusions: list[str] = []

    section: str | None = None
    in_output_columns = False
    in_exclusions = False
    current_table_kind: str | None = None

    for line in spec_text.splitlines():
        # ## section transitions
        if line.startswith("## "):
            if line.startswith("## Output Columns"):
                in_output_columns = True
                in_exclusions = False
            elif line.startswith("## API Fields NOT Included"):
                in_output_columns = False
                in_exclusions = True
            else:
                in_output_columns = False
                in_exclusions = False
            section = None
            current_table_kind = None
            continue

        # ### subsection
        if line.startswith("### "):
            section = line[4:].strip()
            current_table_kind = None
            continue

        if not in_output_columns and not in_exclusions:
            continue

        cells = _split_table_row(line)
        if cells is None:
            continue

        if _is_header_row(cells):
            current_table_kind = cells[2] if len(cells) >= 3 else None
            continue
        if _is_separator_row(cells):
            continue

        if in_exclusions:
            if cells:
                name = _strip_backticks(cells[0])
                if name:
                    exclusions.append(name)
            continue

        if in_output_columns:
            if len(cells) < 4:
                continue
            name = _strip_backticks(cells[0])
            type_ = _strip_backticks(cells[1])
            source_cell = cells[2]
            notes = cells[3].strip()

            entry: dict[str, Any] = {"name": name, "type": type_}

            if current_table_kind == "API Source":
                primary, fallback = _parse_api_source_cell(source_cell)
                if primary is None:
                    print(
                        f"WARN: row {name!r} in section {section!r} has no api_source "
                        f"token in {source_cell!r} — skipped",
                        file=sys.stderr,
                    )
                    continue
                entry["api_source"] = primary
                if fallback:
                    entry["fallback_source"] = fallback
                entry["default"] = _default_for(name, type_)
                entry["description"] = notes
                # Apply api_source overrides for known cases where the spec
                # doc is intentionally inaccurate (e.g. model_name: context
                # vs explore -- see KNOWN_API_OVERRIDES docstring).
                if name in KNOWN_API_OVERRIDES:
                    for k, v in KNOWN_API_OVERRIDES[name].items():
                        if v is None:
                            entry.pop(k, None)
                        else:
                            entry[k] = v
                columns.append(entry)

            elif current_table_kind in ("Source", "Computed From"):
                entry["expression"] = source_cell.strip()
                entry["deterministic"] = _derived_deterministic(source_cell)
                entry["source_section"] = section or ""
                entry["description"] = notes
                derived.append(entry)

            else:
                print(
                    f"WARN: row {name!r} in section {section!r} with unknown table kind "
                    f"{current_table_kind!r}",
                    file=sys.stderr,
                )

    return columns, derived, exclusions


def render_manifest_yaml(
    columns: list[dict],
    derived: list[dict],
    exclusions: list[str],
) -> str:
    """Render the manifest dict to YAML with stable ordering + header comment."""
    manifest = {
        "schema_version": SCHEMA_VERSION,
        "entity": ENTITY,
        "output_grain": OUTPUT_GRAIN,
        "columns": columns,
        "derived_columns": derived,
        "exclusions": exclusions,
    }
    header = (
        "# Looker fields manifest — BUNDLED DEFAULT.\n"
        "# Source of truth: docs/FIELD_SPEC.md\n"
        "# Regenerate: .venv/bin/python scripts/parse_field_spec_to_manifest.py\n"
        f"# schema_version: {SCHEMA_VERSION}\n"
        "\n"
    )
    body = yaml.safe_dump(
        manifest,
        sort_keys=False,
        default_flow_style=False,
        width=120,
        allow_unicode=True,
    )
    return header + body


def validate(columns: list[dict], derived: list[dict], exclusions: list[str]) -> list[str]:
    """Return a list of HARD validation errors (empty = OK).

    Soft warnings (e.g. exclusion count drift) print to stderr but don't abort.
    """
    errors: list[str] = []
    if len(columns) < MIN_COLUMN_COUNT:
        errors.append(
            f"only {len(columns)} columns parsed, expected >= {MIN_COLUMN_COUNT}"
        )
    column_names = {c["name"] for c in columns}
    missing_grain = [g for g in OUTPUT_GRAIN if g not in column_names]
    if missing_grain:
        errors.append(f"output_grain columns missing from columns[]: {missing_grain}")
    for ovname, ovval in KNOWN_DEFAULT_OVERRIDES.items():
        match = next((c for c in columns if c["name"] == ovname), None)
        if match is None:
            errors.append(f"override target column {ovname!r} not found")
        elif match.get("default") != ovval:
            errors.append(
                f"override for {ovname!r} not applied: got default={match.get('default')!r}, "
                f"expected {ovval!r}"
            )
    for ovname, overrides in KNOWN_API_OVERRIDES.items():
        match = next((c for c in columns if c["name"] == ovname), None)
        if match is None:
            errors.append(f"api-override target column {ovname!r} not found")
            continue
        for k, expected in overrides.items():
            actual = match.get(k)
            if expected is None:
                if k in match:
                    errors.append(
                        f"api-override {ovname!r}.{k!r}: expected absent, got {actual!r}"
                    )
            elif actual != expected:
                errors.append(
                    f"api-override {ovname!r}.{k!r}: got {actual!r}, expected {expected!r}"
                )
    # Soft warning only
    if len(exclusions) != EXPECTED_EXCLUSION_COUNT:
        print(
            f"WARN: {len(exclusions)} exclusions parsed, expected {EXPECTED_EXCLUSION_COUNT} "
            f"(FIELD_SPEC.md may have drifted)",
            file=sys.stderr,
        )
    return errors


def main() -> int:
    args = parse_args()
    spec_text = args.spec.read_text(encoding="utf-8")
    columns, derived, exclusions = parse_spec(spec_text)

    errors = validate(columns, derived, exclusions)
    if errors:
        print("FATAL: validation errors:", file=sys.stderr)
        for e in errors:
            print(f"  - {e}", file=sys.stderr)
        return 1

    yaml_text = render_manifest_yaml(columns, derived, exclusions)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(yaml_text, encoding="utf-8")

    print(f"OK: wrote {args.out.relative_to(REPO_ROOT)}")
    print(f"  columns:         {len(columns)}")
    print(f"  derived_columns: {len(derived)}")
    print(f"  exclusions:      {len(exclusions)}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
