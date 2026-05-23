"""Swagger/OpenAPI loader (4-step resolution chain).

Plugin-agnostic loader for the live or bundled Looker OpenAPI spec. Each
plugin bundles its own per-entity swagger types + baseline.json subset, but
the loader resolution mechanism is shared here.

Public surface (mirrors the previous top-level ``_swagger`` package):
    load_swagger(cli_override) -> dict
    resolve_swagger_source(cli_override) -> SwaggerSource
    user_config_path() -> Path
    write_user_config(spec) -> Path
"""

from __future__ import annotations

from .loader import (
    SwaggerSource,
    SwaggerSourceKind,
    load_swagger,
    resolve_swagger_source,
    user_config_path,
    write_user_config,
)

__all__ = [
    "SwaggerSource",
    "SwaggerSourceKind",
    "load_swagger",
    "resolve_swagger_source",
    "user_config_path",
    "write_user_config",
]
