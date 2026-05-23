#!/usr/bin/env python3
"""Regenerate _swagger/baseline.json + types.py from looker_40_openapi.json.

Strips the Looker Swagger 2.0 spec to the minimal subset needed for field
extraction (LookmlModelExplore* and transitive deps), runs datamodel-codegen
to produce Pydantic v2 models, then patches every class with
``model_config = ConfigDict(extra="allow")`` so undocumented API fields don't
trip validation (see docs/FIELD_SPEC.md "Swagger vs Reality").

Usage:
    .venv/bin/python scripts/regen_schema.py [--input PATH] [--output-dir PATH]

Idempotent: re-running overwrites baseline.json + types.py atomically.
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_INPUT = ROOT / "looker_40_openapi.json"
DEFAULT_OUTPUT_DIR = ROOT / "src" / "looker_extractor" / "plugins" / "lookml_fields" / "swagger"

# Entry-point definitions for field extraction.
# Transitive $refs are reached automatically by BFS over collect_refs().
SEED_DEFINITIONS = [
    "LookmlModelExplore",
    "LookmlModelExploreField",
    "LookmlModelExploreFieldset",
    "LookmlModelExploreJoins",
    "LookmlModelExploreAlwaysFilter",
    "LookmlModelExploreAccessFilter",
    "LookmlModelExploreConditionallyFilter",
    "LookmlModelExploreError",
    "LookmlModelNavExploreField",
    "LookmlModelExploreSupportedMeasureType",
    "Error",
    "ValidationError",
]


def collect_refs(node: Any, found: set[str]) -> None:
    """Walk JSON tree; add every '#/definitions/<Name>' target to ``found``."""
    if isinstance(node, dict):
        ref = node.get("$ref")
        if isinstance(ref, str) and ref.startswith("#/definitions/"):
            found.add(ref.split("/")[-1])
        for v in node.values():
            collect_refs(v, found)
    elif isinstance(node, list):
        for item in node:
            collect_refs(item, found)


def rewrite_refs(node: Any, mapper: callable) -> Any:
    """Recursively rewrite every $ref string in a JSON tree via ``mapper(old) -> new``."""
    if isinstance(node, dict):
        out: dict[str, Any] = {}
        for k, v in node.items():
            if k == "$ref" and isinstance(v, str):
                out[k] = mapper(v)
            else:
                out[k] = rewrite_refs(v, mapper)
        return out
    if isinstance(node, list):
        return [rewrite_refs(item, mapper) for item in node]
    return node


def strip_to_subset(swagger: dict[str, Any], seeds: list[str]) -> dict[str, Any]:
    """Strip to reachable subset AND convert Swagger 2.0 envelope to OpenAPI 3.0.

    dmcg 0.57 only accepts OpenAPI 3.x (--input-file-type openapi); Looker still
    publishes Swagger 2.0. We rewrite the envelope in-flight:
      * definitions/X -> components.schemas/X
      * $ref '#/definitions/X' -> '#/components/schemas/X'
    """
    defs = swagger.get("definitions", {})
    keep: set[str] = set()
    queue = [s for s in seeds if s in defs]
    while queue:
        name = queue.pop()
        if name in keep:
            continue
        keep.add(name)
        refs: set[str] = set()
        collect_refs(defs[name], refs)
        for r in refs:
            if r in defs and r not in keep:
                queue.append(r)

    def map_ref(ref: str) -> str:
        if ref.startswith("#/definitions/"):
            return "#/components/schemas/" + ref.split("/")[-1]
        return ref

    rewritten = {
        name: rewrite_refs(defs[name], map_ref)
        for name in sorted(keep)
    }

    return {
        "openapi": "3.0.0",
        "info": swagger.get("info", {"title": "Looker API", "version": "4.0"}),
        "paths": {},  # dmcg accepts empty paths
        "components": {"schemas": rewritten},
    }


def patch_extra_allow(types_py: Path) -> int:
    """Inject ``model_config = ConfigDict(extra="allow")`` into every BaseModel.

    Idempotent. Adds the ConfigDict import if missing.
    """
    text = types_py.read_text()

    # Idempotency: skip if already patched.
    if 'model_config = ConfigDict(extra="allow")' in text:
        return 0

    # Inject ConfigDict import.
    if "ConfigDict" not in text:
        new_text = re.sub(
            r"from pydantic import ([^\n]+)",
            lambda m: (
                f"from pydantic import {m.group(1)}, ConfigDict"
                if "ConfigDict" not in m.group(1)
                else m.group(0)
            ),
            text,
            count=1,
        )
        if "ConfigDict" not in new_text:
            # Fallback: add a standalone import after the first import block.
            new_text = re.sub(
                r"(\nfrom pydantic[^\n]*\n)",
                r"\1from pydantic import ConfigDict\n",
                text,
                count=1,
            )
        text = new_text

    # Insert model_config line immediately after each `class X(...BaseModel...):` line.
    pattern = re.compile(
        r"^(class\s+\w+\s*\([^)]*\bBaseModel\b[^)]*\)\s*:)\s*$",
        re.MULTILINE,
    )
    patched = 0

    def add_config(m: re.Match[str]) -> str:
        nonlocal patched
        patched += 1
        return f'{m.group(1)}\n    model_config = ConfigDict(extra="allow")'

    text = pattern.sub(add_config, text)
    types_py.write_text(text)
    return patched


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    args = parser.parse_args(argv)

    if not args.input.exists():
        print(f"missing input swagger: {args.input}", file=sys.stderr)
        return 2

    args.output_dir.mkdir(parents=True, exist_ok=True)
    baseline_json = args.output_dir / "baseline.json"
    types_py = args.output_dir / "types.py"

    raw = json.loads(args.input.read_text())
    subset = strip_to_subset(raw, SEED_DEFINITIONS)

    baseline_json.write_text(json.dumps(subset, indent=2, sort_keys=True))
    schemas = subset.get("components", {}).get("schemas", {})
    print(
        f"[regen] baseline.json: {len(schemas)} schemas, "
        f"{baseline_json.stat().st_size // 1024} KB"
    )

    # Resolve datamodel-codegen via the venv that's running this script.
    # subprocess.run() does NOT auto-prepend .venv/bin to PATH.
    codegen_bin = Path(sys.executable).parent / "datamodel-codegen"
    if not codegen_bin.exists():
        print(
            f"datamodel-codegen not found at {codegen_bin}; "
            "install dev deps: `uv pip install -e .[dev]`",
            file=sys.stderr,
        )
        return 3

    cmd = [
        str(codegen_bin),
        "--input", str(baseline_json),
        "--input-file-type", "openapi",  # dmcg 0.57+ handles both Swagger 2.0 and OpenAPI 3.x under "openapi"
        "--output", str(types_py),
        "--output-model-type", "pydantic_v2.BaseModel",
        "--target-python-version", "3.11",
        "--use-standard-collections",
        "--use-union-operator",
        "--field-constraints",
        "--snake-case-field",
        # NB: do NOT pass --allow-population-by-field-name; dmcg would emit a 2nd
        # model_config block that overrides our extra="allow" patch.
    ]
    print("[regen] running:", " ".join(cmd))
    res = subprocess.run(cmd, capture_output=True, text=True)
    if res.returncode != 0:
        sys.stdout.write(res.stdout)
        sys.stderr.write(res.stderr)
        return res.returncode

    patched = patch_extra_allow(types_py)
    print(
        f"[regen] types.py: {types_py.stat().st_size // 1024} KB, "
        f"patched {patched} classes with extra='allow'"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
