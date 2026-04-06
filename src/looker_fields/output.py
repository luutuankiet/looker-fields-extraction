"""Multi-sink output writers."""

from __future__ import annotations

import csv
import logging
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any, Sequence

from .schema import FieldRecord

logger = logging.getLogger(__name__)


class Writer(ABC):
    """Base class for output writers."""

    @abstractmethod
    def write_records(self, records: Sequence[FieldRecord]) -> None:
        """Write a batch of records to the output sink."""
        ...

    @abstractmethod
    def close(self) -> None:
        """Flush and close the writer."""
        ...

    def __enter__(self) -> Writer:
        return self

    def __exit__(self, *args: Any) -> None:
        self.close()


class JsonlWriter(Writer):
    """Write records as newline-delimited JSON (JSONL)."""

    def __init__(self, path: Path) -> None:
        self.path = path
        self._file = open(path, "wb")
        self._count = 0

    def write_records(self, records: Sequence[FieldRecord]) -> None:
        for record in records:
            self._file.write(record.to_jsonl())
            self._count += 1

    def close(self) -> None:
        self._file.close()
        logger.info("Wrote %d records to %s", self._count, self.path)


class CsvWriter(Writer):
    """Write records as CSV."""

    def __init__(self, path: Path) -> None:
        self.path = path
        self._file = open(path, "w", newline="", encoding="utf-8")
        self._writer: csv.DictWriter | None = None
        self._count = 0

    def write_records(self, records: Sequence[FieldRecord]) -> None:
        for record in records:
            row = record.model_dump()
            if self._writer is None:
                self._writer = csv.DictWriter(self._file, fieldnames=list(row.keys()))
                self._writer.writeheader()
            self._writer.writerow(row)
            self._count += 1

    def close(self) -> None:
        self._file.close()
        logger.info("Wrote %d records to %s", self._count, self.path)


class ParquetWriter(Writer):
    """Write records as Apache Parquet."""

    def __init__(self, path: Path) -> None:
        self.path = path
        self._records: list[dict[str, Any]] = []

    def write_records(self, records: Sequence[FieldRecord]) -> None:
        self._records.extend(r.model_dump() for r in records)

    def close(self) -> None:
        import pyarrow as pa
        import pyarrow.parquet as pq

        if not self._records:
            logger.warning("No records to write to %s", self.path)
            return

        table = pa.Table.from_pylist(self._records)
        pq.write_table(table, self.path)
        logger.info("Wrote %d records to %s", len(self._records), self.path)


class BigQueryWriter(Writer):
    """Write records to a BigQuery table."""

    def __init__(self, project: str, dataset: str, table: str) -> None:
        from google.cloud import bigquery

        self.table_ref = f"{project}.{dataset}.{table}"
        self.bq_client = bigquery.Client(project=project)
        self._records: list[dict[str, Any]] = []

    def write_records(self, records: Sequence[FieldRecord]) -> None:
        self._records.extend(r.model_dump() for r in records)

    def close(self) -> None:
        if not self._records:
            logger.warning("No records to write to %s", self.table_ref)
            return

        from google.cloud import bigquery

        job_config = bigquery.LoadJobConfig(
            write_disposition="WRITE_TRUNCATE",
            autodetect=True,
        )
        job = self.bq_client.load_table_from_json(
            self._records, self.table_ref, job_config=job_config
        )
        job.result()
        logger.info("Wrote %d records to %s", len(self._records), self.table_ref)


def get_writer(format: str, path: Path, **kwargs: Any) -> Writer:
    """Factory for creating the appropriate writer."""
    match format.lower():
        case "jsonl":
            return JsonlWriter(path)
        case "csv":
            return CsvWriter(path)
        case "parquet":
            return ParquetWriter(path)
        case "bq" | "bigquery":
            return BigQueryWriter(
                project=kwargs["bq_project"],
                dataset=kwargs["bq_dataset"],
                table=kwargs["bq_table"],
            )
        case _:
            raise ValueError(f"Unknown output format: {format}")
