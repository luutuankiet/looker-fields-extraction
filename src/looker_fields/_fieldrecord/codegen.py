"""FieldRecord code generation: manifest YAML -> pydantic class source.

This module contains the codegen logic.
scripts/regen_fieldrecord.py is a thin CLI wrapper.
cli.py 'regen-types' command calls regenerate() directly for XDG-cache writes.

Lifting the body into the package makes ``regen-types`` available to
pip-installed users (the scripts/ directory ships only in repo checkouts).
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

# Hand-rolled FieldRecord required these as Field(...) ellipsis -- no default,
# must be provided at construction. Output grain + classification keys.
REQUIRED_BEYOND_GRAIN: frozenset[str] = frozenset({"category", "field_type"})

# Derived columns with ``expression: Hardcoded`` carry their literal value in
# the manifest description. The build can't safely parse that -- hardcode here.
HARDCODED_DERIVED_VALUES: dict[str, str] = {
    "schema_version": '"1.1.0"',
}

TYPE_MAP: dict[str, str] = {
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


def render_literal(value: Any) -> str:
    """Render a YAML-loaded scalar default as a Python source expression."""
    if value is None:
        return "None"
    if isinstance(value, bool):
        return "True" if value else "False"
    if isinstance(value, int):  # bool subclass already handled above
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

    if mtype == "list[str]":
        return f"    {name}: {pytype} = Field(default_factory=list{desc_arg})"

    default = col.get("default")
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

    if expr == "Generated" and name == "extracted_at":
        return (
            f"    {name}: {pytype} = Field("
            f"default_factory=lambda: datetime.now(timezone.utc).isoformat()"
            f"{desc_arg})"
        )

    if expr == "Hardcoded" and name in HARDCODED_DERIVED_VALUES:
        val = HARDCODED_DERIVED_VALUES[name]
        return f"    {name}: {pytype} = Field({val}{desc_arg})"

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
        "           or: looker-fields regen-types (writes to XDG cache)",
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

    lines.extend([
        "    def to_jsonl(self) -> bytes:",
        '        """Serialize to a JSONL-ready bytes line."""',
        "        return orjson.dumps(self.model_dump(), option=orjson.OPT_APPEND_NEWLINE)",
        "",
    ])

    return "\n".join(lines)


def regenerate(manifest_path: Path, output_path: Path) -> tuple[Path, int]:
    """Read manifest YAML, regenerate FieldRecord module, write atomically.

    Returns (output_path, bytes_written).
    """
    if not manifest_path.exists():
        raise FileNotFoundError(f"missing manifest: {manifest_path}")

    manifest = yaml.safe_load(manifest_path.read_text())
    body = render_module(manifest)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(body)

    return output_path, len(body.encode())
