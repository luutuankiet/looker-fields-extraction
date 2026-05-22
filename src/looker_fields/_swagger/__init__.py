"""Bundled OpenAPI spec + generated Pydantic types for Looker LookmlModelExplore.

Public surface:
    load_swagger(cli_override) -> dict — resolve and load the spec
    resolve_swagger_source(cli_override) -> SwaggerSource — describe where it came from
    user_config_path() -> Path — XDG location for user-managed override
    write_user_config(spec) -> Path — persist a fresh spec to the XDG location

Generated Pydantic v2 types live in ``looker_fields._swagger.types``.
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
