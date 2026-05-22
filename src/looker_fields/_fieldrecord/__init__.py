"""Generated FieldRecord package -- re-exports the active FieldRecord type.

Resolution: checks the XDG user cache for a custom-regenerated types.py
first; falls back to the bundled types.py if no override exists.

XDG cache location (when present):
    ~/.cache/looker-fields/_fieldrecord/types.py

Write the cache via ``looker-fields regen-types``; revert by deleting it.

Consumers import the symbol through schema.py (which re-exports from here):

    from looker_fields.schema import FieldRecord
"""

from __future__ import annotations

import importlib.util
import logging
from pathlib import Path
from typing import Any

import platformdirs

_logger = logging.getLogger(__name__)


def _xdg_types_path() -> Path:
    return (
        Path(platformdirs.user_cache_dir("looker-fields", appauthor=False))
        / "_fieldrecord"
        / "types.py"
    )


def _load_xdg_field_record() -> Any | None:
    """Dynamic-import the XDG-cached types.py if present.

    Returns FieldRecord or None (cache absent / unreadable / malformed).
    Logs at WARNING+ on partial failure so silent override fallback is
    debuggable.
    """
    path = _xdg_types_path()
    if not path.is_file():
        return None
    spec = importlib.util.spec_from_file_location(
        "looker_fields._fieldrecord._xdg_types", path
    )
    if spec is None or spec.loader is None:
        _logger.warning(
            "XDG types.py found at %s but spec_from_file_location failed", path
        )
        return None
    module = importlib.util.module_from_spec(spec)
    try:
        spec.loader.exec_module(module)
    except Exception as exc:
        _logger.error(
            "Failed to load XDG types.py at %s: %s -- falling back to bundled",
            path,
            exc,
        )
        return None
    fr = getattr(module, "FieldRecord", None)
    if fr is None:
        _logger.warning(
            "XDG types.py at %s lacks FieldRecord symbol -- falling back to bundled",
            path,
        )
        return None
    _logger.info("Loaded FieldRecord from XDG cache: %s", path)
    return fr


_xdg_fr = _load_xdg_field_record()
if _xdg_fr is not None:
    FieldRecord = _xdg_fr
else:
    from .types import FieldRecord  # noqa: F401

__all__ = ["FieldRecord"]
