#!/usr/bin/env python3
"""Regenerate src/looker_fields/_fieldrecord/types.py from manifest/fields.yaml.

Thin CLI wrapper around looker_fields._fieldrecord.codegen.regenerate().
For programmatic / XDG-cache regen, use the ``looker-fields regen-types``
command instead -- it's available to pip-installed users (scripts/ ships
only in repo checkouts).

Usage:
    .venv/bin/python scripts/regen_fieldrecord.py [--manifest PATH] [--output PATH]
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

# Repo-relative path manipulation so ``import looker_fields`` resolves to
# the src/ tree when this script is run from a checkout.
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from looker_fields._fieldrecord.codegen import regenerate  # noqa: E402

DEFAULT_MANIFEST = ROOT / "src" / "looker_fields" / "manifest" / "fields.yaml"
DEFAULT_OUTPUT = ROOT / "src" / "looker_fields" / "_fieldrecord" / "types.py"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args(argv)

    try:
        path, bytes_written = regenerate(args.manifest, args.output)
    except FileNotFoundError as exc:
        print(str(exc), file=sys.stderr)
        return 2

    import yaml

    manifest = yaml.safe_load(args.manifest.read_text())
    print(
        f"[regen] manifest: {len(manifest['columns'])} direct + "
        f"{len(manifest.get('derived_columns', []))} derived -> "
        f"{path} ({bytes_written} bytes)"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
