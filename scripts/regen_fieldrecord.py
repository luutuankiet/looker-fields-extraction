#!/usr/bin/env python3
"""Regenerate src/looker_fields/_fieldrecord/types.py from manifest/fields.yaml.

The manifest IS the contract; this script projects it into a typed Pydantic v2
output model that downstream consumers (cli, output, verify) import.

Idempotent: re-running overwrites types.py atomically with byte-stable output.

Usage:
    .venv/bin/python scripts/regen_fieldrecord.py [--output PATH]

Phase 5 of TASK-007 (manifest-native architecture pivot).
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_MANIFEST = ROOT / "src" / "looker_fields" / "manifest" / "fields.yaml"
DEFAULT_OUTPUT = ROOT / "src" / "looker_fields" / "_fieldrecord" / "types.py"

# Hand-rolled FieldRecord required these as Field(...) Ellipsis - i.e. no default,
# must be provided at construction. Output grain + classification keys.
# (Manifest output_grain only lists the 4 identity fields; classification keys
# are separately required by the extract pipeline.)
REQUIRED_BEYOND_GRAIN = frozenset({"category", "field_type"})

# Derived columns with `expression: Hardcoded` carry their literal value in the
# manifest description. The build script can't safely parse that - hardcode here.
HARDCODED_DERIVED_VALUES = {
    "schema_version": '"1.1.0"',
}

TYPE_MAP = {
    "str": "str",
    "bool": "bool",
    "int": "int",
    "list[str]": "list[str]",
    "str?": "str | None",
    "int?": "int | None",
    "bool?": "bool | None",
}


def py_type(manifest_type: str) -> str:
    if manifest_type not in TYPE_MAP:
        raise ValueError(f"unknown manifest type: {manifest_type!r}")
    return TYPE_MAP[manifest_type]


def render_literal(value) -> str:
    """Render a YAML-loaded scalar default as a Python source expression."""
    if value is None:
        return "None"
    if isinstance(value, bool):
        return "True" if value else "False"
    if isinstance(value, int):  # bool is a subclass of int - handled above
        return str(value)
    if isinstance(value, str):
        return repr(value)
    raise ValueError(f"unrenderable literal: {value!r} (type={type(value).__name__})")


def render_column(col: dict, required_set: set[str]) -> str:
    name = col["name"]
    mtype = col["type"]
    pytype = py_type(mtype)
    desc = col.get("description", "")
    desc_arg = f", description={desc!r}" if desc else ""

    if name in required_set:
        return f"    {name}: {pytype} = Field(...{desc_arg})"

    # Mutable default (list) -> factory
    if mtype == "list[str]":
        return f"    {name}: {pytype} = Field(default_factory=list{desc_arg})"

    default = col.get("default")
    # Defensive: empty list as default literal also routes to factory
    if isinstance(default, list) and not default:
        return f"    {name}: {pytype} = Field(default_factory=list{desc_arg})"

    rendered = render_literal(default)
    return f"    {name}: {pytype} = Field({rendered}{desc_arg})"


def render_derived(col: dict) -> str:
    name = col["name"]
    mtype = col["type"]
    pytype = py_type(mtype)
    expr = col.get("expression", "")
    desc = col.get("description", "")
    desc_arg = f", description={desc!r}" if desc else ""

    # Specialty 1: Generated (runtime - extracted_at uses datetime.now lambda)
    if expr == "Generated" and name == "extracted_at":
        return (
            f"    {name}: {pytype} = Field("
            f"default_factory=lambda: datetime.now(timezone.utc).isoformat()"
            f"{desc_arg})"
        )

    # Specialty 2: Hardcoded literal from per-name table
    if expr == "Hardcoded" and name in HARDCODED_DERIVED_VALUES:
        val = HARDCODED_DERIVED_VALUES[name]
        return f"    {name}: {pytype} = Field({val}{desc_arg})"

    # Default rule: post-extraction computed -> type-default zero value
    if mtype == "list[str]":
        return f"    {name}: {pytype} = Field(default_factory=list{desc_arg})"
    if mtype == "int":
        return f"    {name}: {pytype} = Field(0{desc_arg})"
    if mtype == "str":
        return f"    {name}: {pytype} = Field(''{desc_arg})"
    if mtype == "bool":
        return f"    {name}: {pytype} = Field(False{desc_arg})"

    raise ValueError(
        f"unhandled derived column: {name} (type={mtype}, expr={expr!r})"
    )


def render_module(manifest: dict) -> str:
    columns = manifest["columns"]
    derived = manifest.get("derived_columns", [])
    grain = manifest["output_grain"]
    required_set = set(grain) | REQUIRED_BEYOND_GRAIN
    grain_csv = ", ".join(grain)

    lines = [
        '"""Generated FieldRecord - DO NOT EDIT.',
        "",
        "Regenerate via: .venv/bin/python scripts/regen_fieldrecord.py",
        "Source:         src/looker_fields/manifest/fields.yaml",
        "",
        "The manifest is the contract; this file projects it into a typed",
        "Pydantic v2 BaseModel for downstream consumers (cli, output, verify).",
        '"""',
        "",
        "from __future__ import annotations",
        "",
        "from datetime import datetime, timezone",
        "",
        "import orjson",
        "from pydantic import BaseModel, ConfigDict, Field",
        "",
        "",
        "class FieldRecord(BaseModel):",
        '    """One extracted field - the fundamental output row.',
        "",
        f"    Grain: ({grain_csv}) = unique row.",
        "    Generated from manifest/fields.yaml; do not hand-edit.",
        '    """',
        "",
        '    model_config = ConfigDict(extra="forbid")',
        "",
    ]

    for col in columns:
        lines.append(render_column(col, required_set))
    lines.append("")

    for col in derived:
        lines.append(render_derived(col))
    lines.append("")

    # to_jsonl preserved verbatim from hand-rolled FieldRecord (output.py contract)
    lines.extend([
        "    def to_jsonl(self) -> bytes:",
        '        """Serialize to a JSONL-ready bytes line."""',
        "        return orjson.dumps(self.model_dump(), option=orjson.OPT_APPEND_NEWLINE)",
        "",
    ])

    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args(argv)

    if not args.manifest.exists():
        print(f"missing manifest: {args.manifest}", file=sys.stderr)
        return 2

    manifest = yaml.safe_load(args.manifest.read_text())
    body = render_module(manifest)

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(body)
    print(
        f"[regen] manifest: {len(manifest['columns'])} direct + "
        f"{len(manifest.get('derived_columns', []))} derived -> "
        f"{args.output} ({len(body.encode())} bytes)"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
