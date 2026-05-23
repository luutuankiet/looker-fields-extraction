"""Swagger/OpenAPI spec loader with explicit resolution chain.

Precedence (first hit wins):
    1. cli_override          — ``--swagger-path PATH`` CLI flag
    2. LOOKER_SWAGGER_PATH   — env var
    3. XDG user config       — ``~/.config/looker-extractor/swagger.json`` (via platformdirs)
    4. bundled baseline      — ``looker_extractor._swagger.baseline.json`` (importlib.resources)

Env beats XDG by design: env is the explicit per-invocation override; XDG is the
"installed once, persists" config. CLI flag beats env because the flag is the most
explicit signal the user can give.
"""

from __future__ import annotations

import enum
import json
import os
from dataclasses import dataclass
from importlib import resources
from pathlib import Path
from typing import Any

import platformdirs

APP_NAME = "looker-extractor"
ENV_VAR = "LOOKER_SWAGGER_PATH"
BUNDLED_FILENAME = "baseline.json"


class SwaggerSourceKind(str, enum.Enum):
    """Where the loaded spec came from. Useful for refresh-schema diagnostics."""

    CLI = "cli"
    ENV = "env"
    XDG = "xdg"
    BUNDLED = "bundled"


@dataclass(frozen=True)
class SwaggerSource:
    kind: SwaggerSourceKind
    path: Path | None  # None only for BUNDLED before resolving the resource file

    def __str__(self) -> str:
        return f"{self.kind.value}:{self.path}"


def user_config_path() -> Path:
    """XDG-aware user config path: ~/.config/looker-extractor/swagger.json on Linux."""
    return Path(platformdirs.user_config_dir(APP_NAME, appauthor=False)) / "swagger.json"


def _bundled_path() -> Path:
    """Filesystem path to the package-bundled baseline.json.

    Uses importlib.resources to support zip-installed packages.
    """
    # files() returns a Traversable; for a real on-disk install this resolves cleanly.
    return Path(str(resources.files("looker_extractor._swagger").joinpath(BUNDLED_FILENAME)))


def resolve_swagger_source(cli_override: Path | None = None) -> SwaggerSource:
    """Walk the precedence chain and return the first source that exists.

    Raises FileNotFoundError only if even the bundled baseline is missing
    (which would be a packaging bug, not a user error).
    """
    if cli_override is not None:
        p = Path(cli_override).expanduser()
        if not p.is_file():
            raise FileNotFoundError(f"--swagger-path does not exist: {p}")
        return SwaggerSource(SwaggerSourceKind.CLI, p)

    env_val = os.environ.get(ENV_VAR)
    if env_val:
        p = Path(env_val).expanduser()
        if not p.is_file():
            raise FileNotFoundError(f"${ENV_VAR}={env_val} does not exist")
        return SwaggerSource(SwaggerSourceKind.ENV, p)

    xdg = user_config_path()
    if xdg.is_file():
        return SwaggerSource(SwaggerSourceKind.XDG, xdg)

    bundled = _bundled_path()
    if not bundled.is_file():
        raise FileNotFoundError(
            f"bundled swagger baseline missing at {bundled}; run scripts/regen_schema.py"
        )
    return SwaggerSource(SwaggerSourceKind.BUNDLED, bundled)


def load_swagger(cli_override: Path | None = None) -> dict[str, Any]:
    """Resolve + read the swagger spec. Returns parsed JSON as a dict."""
    source = resolve_swagger_source(cli_override)
    assert source.path is not None
    return json.loads(source.path.read_text())


def write_user_config(spec: dict[str, Any], path: Path | None = None) -> Path:
    """Persist ``spec`` to the XDG user config path (or ``path`` if given).

    Creates parent directories if missing. Atomic write via tempfile rename.
    """
    target = (path or user_config_path()).expanduser()
    target.parent.mkdir(parents=True, exist_ok=True)
    tmp = target.with_suffix(target.suffix + ".tmp")
    tmp.write_text(json.dumps(spec, indent=2, sort_keys=True))
    tmp.replace(target)
    return target
