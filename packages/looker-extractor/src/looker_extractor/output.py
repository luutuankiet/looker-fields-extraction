"""Output writers -- semi-structured passthru to JSONL or Parquet.

Post-pivot: the writer takes raw dicts (from extract.py's ``model_dump()``)
and emits them as-is. No projection, no column flattening, no schema
enforcement. Parquet uses pyarrow's inference to preserve nested struct/list
shape; the downstream warehouse handles flattening.

Only two formats survive:
  JSONL   : default, lossless, easy to inspect/grep
  Parquet : columnar, preserves nesting, ready for warehouse load

CSV is gone (lossy on nested structures). BigQuery is gone (downstream
loader's job, not ours -- \"do one thing well\").
"""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any, Sequence

import orjson

logger = logging.getLogger(__name__)


class Writer(ABC):
    """Base class for output writers -- operates on raw passthru dicts."""

    @abstractmethod
    def write_records(self, records: Sequence[dict[str, Any]]) -> None:
        ...

    @abstractmethod
    def close(self) -> None:
        ...

    def __enter__(self) -> "Writer":
        return self

    def __exit__(self, *args: Any) -> None:
        self.close()


class JsonlWriter(Writer):
    """Newline-delimited JSON. Lossless passthru."""

    def __init__(self, path: Path) -> None:
        self.path = path
        self._file = open(path, "wb")
        self._count = 0

    def write_records(self, records: Sequence[dict[str, Any]]) -> None:
        for record in records:
            self._file.write(orjson.dumps(record))
            self._file.write(b"\n")
            self._count += 1

    def close(self) -> None:
        self._file.close()
        logger.info("Wrote %d records to %s", self._count, self.path)


class ParquetWriter(Writer):
    """Apache Parquet via pyarrow. Preserves nested struct/list shape.

    Uses ``pa.Table.from_pylist`` with pyarrow's inference. For mixed/sparse
    nested dicts (common from passthru), pyarrow may produce struct schemas
    with many nullable fields -- that's the cost of preserving the natural
    shape. The downstream warehouse can flatten via UNNEST/dot-notation.
    """

    def __init__(self, path: Path) -> None:
        self.path = path
        self._records: list[dict[str, Any]] = []

    def write_records(self, records: Sequence[dict[str, Any]]) -> None:
        self._records.extend(records)

    def close(self) -> None:
        import pyarrow as pa
        import pyarrow.parquet as pq

        if not self._records:
            logger.warning("No records to write to %s", self.path)
            return

        table = pa.Table.from_pylist(self._records)
        pq.write_table(table, self.path)
        logger.info("Wrote %d records to %s", len(self._records), self.path)


def get_writer(format: str, path: Path) -> Writer:
    """Factory for the supported writers."""
    match format.lower():
        case "jsonl":
            return JsonlWriter(path)
        case "parquet":
            return ParquetWriter(path)
        case _:
            raise ValueError(
                f"Unknown output format: {format!r}. Supported: jsonl, parquet."
            )
