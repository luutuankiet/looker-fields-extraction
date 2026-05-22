"""Manifest loader with explicit 4-step resolution chain.

Mirrors src/looker_fields/_swagger/loader.py — the manifest YAML and the
swagger JSON share the same precedence/source pattern by design (one mental
model for all bundled-with-override config artifacts).

Precedence (first hit wins):
    1. cli_override            — ``--manifest-path PATH`` CLI flag
    2. LOOKER_FIELDS_MANIFEST  — env var
    3. XDG user config         — ``~/.config/looker-fields/manifest.yaml``
    4. bundled default         — ``looker_fields.manifest.fields.yaml``

Env beats XDG by design: env is the explicit per-invocation override; XDG is
the "installed once, persists" config. CLI flag beats env because the flag
is the most explicit signal the user can give.
"""

from __future__ import annotations

import enum
import os
from dataclasses import dataclass
from importlib import resources
from pathlib import Path
from typing import Any

import platformdirs
import yaml

APP_NAME = "looker-fields"
ENV_VAR = "LOOKER_FIELDS_MANIFEST"
BUNDLED_FILENAME = "fields.yaml"


class ManifestSourceKind(str, enum.Enum):
    """Where the loaded manifest came from. Useful for refresh-manifest diagnostics."""

    CLI = "cli"
    ENV = "env"
    XDG = "xdg"
    BUNDLED = "bundled"


@dataclass(frozen=True)
class ManifestSource:
    kind: ManifestSourceKind
    path: Path | None  # None only for BUNDLED before resolving the resource file

    def __str__(self) -> str:
        return f"{self.kind.value}:{self.path}"


def user_config_path() -> Path:
    """XDG-aware user config path: ~/.config/looker-fields/manifest.yaml on Linux."""
    return Path(platformdirs.user_config_dir(APP_NAME, appauthor=False)) / "manifest.yaml"


def _bundled_path() -> Path:
    """Filesystem path to the package-bundled fields.yaml.

    Uses importlib.resources to support zip-installed packages.
    """
    return Path(str(resources.files("looker_fields.manifest").joinpath(BUNDLED_FILENAME)))


def resolve_manifest_source(cli_override: Path | None = None) -> ManifestSource:
    """Walk the precedence chain and return the first source that exists.

    Raises FileNotFoundError only if even the bundled default is missing
    (which would be a packaging bug, not a user error).
    """
    if cli_override is not None:
        p = Path(cli_override).expanduser()
        if not p.is_file():
            raise FileNotFoundError(f"--manifest-path does not exist: {p}")
        return ManifestSource(ManifestSourceKind.CLI, p)

    env_val = os.environ.get(ENV_VAR)
    if env_val:
        p = Path(env_val).expanduser()
        if not p.is_file():
            raise FileNotFoundError(f"${ENV_VAR}={env_val} does not exist")
        return ManifestSource(ManifestSourceKind.ENV, p)

    xdg = user_config_path()
    if xdg.is_file():
        return ManifestSource(ManifestSourceKind.XDG, xdg)

    bundled = _bundled_path()
    if not bundled.is_file():
        raise FileNotFoundError(
            f"bundled manifest missing at {bundled}; run "
            f"scripts/parse_field_spec_to_manifest.py"
        )
    return ManifestSource(ManifestSourceKind.BUNDLED, bundled)


def load_manifest(cli_override: Path | None = None) -> dict[str, Any]:
    """Resolve + read the manifest YAML. Returns parsed dict.

    Does NOT validate against ManifestSpec — caller chooses whether to
    incur pydantic validation cost (e.g. CLI startup: yes; hot path: no).
    """
    source = resolve_manifest_source(cli_override)
    assert source.path is not None
    return yaml.safe_load(source.path.read_text())


def write_user_config(spec: dict[str, Any], path: Path | None = None) -> Path:
    """Persist ``spec`` to the XDG user config path (or ``path`` if given).

    Creates parent directories if missing. Atomic write via tempfile rename.
    Emits YAML with stable key ordering (sort_keys=False) to keep diffs clean.
    """
    target = (path or user_config_path()).expanduser()
    target.parent.mkdir(parents=True, exist_ok=True)
    tmp = target.with_suffix(target.suffix + ".tmp")
    tmp.write_text(
        yaml.safe_dump(spec, sort_keys=False, default_flow_style=False, width=120)
    )
    tmp.replace(target)
    return target
