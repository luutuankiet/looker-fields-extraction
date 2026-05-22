"""Diff extracted JSONL output against a live API response.

The extractor (extract.flatten_explore) is the source of truth for how an
API response becomes FieldRecord rows. Verification re-runs that flattening
on a fresh API response and diffs the result against what the user previously
dumped to disk — catching extractor regressions, schema drift, and stale outputs.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import orjson

from .extract import flatten_explore
from .schema import FieldRecord

# Columns excluded from value diff:
#   - extracted_at:           re-derived expected has fresh timestamp
#   - seen_in_*, total_times_used, seen_models, seen_explores, definition_*:
#       computed POST-extraction by enrich_seen_in(); expected (single-explore)
#       won't have them populated yet.
NON_DETERMINISTIC_COLUMNS: frozenset[str] = frozenset({
    "extracted_at",
    "seen_in_model_count",
    "seen_in_explore_count",
    "total_times_used",
    "seen_models",
    "seen_explores",
    "definition_hash",
    "definition_variant_count",
    "definition_appearances_count",
})


@dataclass
class FieldDiff:
    """One column's mismatch on one field."""

    field_name: str
    column: str
    extracted: Any
    expected: Any

    def render(self) -> str:
        return (
            f"  {self.field_name}.{self.column}: "
            f"extracted={self.extracted!r} expected={self.expected!r}"
        )


@dataclass
class DiffReport:
    """Aggregate diff outcome for one model::explore pair."""

    model: str
    explore: str
    extracted_count: int = 0
    expected_count: int = 0
    matching_field_count: int = 0
    only_in_extracted: list[str] = field(default_factory=list)
    only_in_expected: list[str] = field(default_factory=list)
    field_diffs: list[FieldDiff] = field(default_factory=list)

    @property
    def is_clean(self) -> bool:
        return (
            not self.only_in_extracted
            and not self.only_in_expected
            and not self.field_diffs
        )

    def render(self, max_items: int = 20) -> str:
        lines = [
            f"# Verify report: {self.model}::{self.explore}",
            f"  extracted: {self.extracted_count} fields",
            f"  expected:  {self.expected_count} fields",
            f"  matching keys: {self.matching_field_count}",
        ]
        if self.only_in_extracted:
            lines.append(f"  ONLY IN EXTRACTED ({len(self.only_in_extracted)}):")
            for n in self.only_in_extracted[:max_items]:
                lines.append(f"    - {n}")
            if len(self.only_in_extracted) > max_items:
                lines.append(f"    ... +{len(self.only_in_extracted) - max_items} more")
        if self.only_in_expected:
            lines.append(f"  ONLY IN EXPECTED  ({len(self.only_in_expected)}):")
            for n in self.only_in_expected[:max_items]:
                lines.append(f"    - {n}")
            if len(self.only_in_expected) > max_items:
                lines.append(f"    ... +{len(self.only_in_expected) - max_items} more")
        if self.field_diffs:
            lines.append(f"  VALUE MISMATCHES ({len(self.field_diffs)}):")
            for d in self.field_diffs[:max_items]:
                lines.append(d.render())
            if len(self.field_diffs) > max_items:
                lines.append(f"    ... +{len(self.field_diffs) - max_items} more")
        if self.is_clean:
            lines.append("  CLEAN: all fields match.")
        return "\n".join(lines)


def load_extracted_records(
    jsonl_path: Path,
    model: str,
    explore: str,
) -> list[FieldRecord]:
    """Read JSONL output and filter rows to the given model+explore pair."""
    out: list[FieldRecord] = []
    with jsonl_path.open("rb") as f:
        for raw in f:
            line = raw.strip()
            if not line:
                continue
            data = orjson.loads(line)
            if data.get("model_name") == model and data.get("explore_name") == explore:
                out.append(FieldRecord(**data))
    return out


def diff_extracted_vs_raw(
    extracted: list[FieldRecord],
    raw_explore: dict[str, Any],
    model: str,
    manifest: Any = None,
) -> DiffReport:
    """Compare extracted records against a freshly-derived expected set.

    The expected set is built by re-running ``flatten_explore`` over the raw
    API response. Diff covers:
        * key membership on ``field_name`` (what's only in one side)
        * per-field column values (excluding ``NON_DETERMINISTIC_COLUMNS``)
    """
    explore_name = raw_explore.get("name", "?")
    expected = flatten_explore(raw_explore, model, manifest)

    report = DiffReport(
        model=model,
        explore=explore_name,
        extracted_count=len(extracted),
        expected_count=len(expected),
    )

    ex_by_name = {r.field_name: r for r in extracted}
    exp_by_name = {r.field_name: r for r in expected}

    ex_keys = set(ex_by_name)
    exp_keys = set(exp_by_name)
    report.only_in_extracted = sorted(ex_keys - exp_keys)
    report.only_in_expected = sorted(exp_keys - ex_keys)

    columns_to_diff = [
        name for name in FieldRecord.model_fields if name not in NON_DETERMINISTIC_COLUMNS
    ]

    for name in sorted(ex_keys & exp_keys):
        report.matching_field_count += 1
        ex_dump = ex_by_name[name].model_dump()
        exp_dump = exp_by_name[name].model_dump()
        for col in columns_to_diff:
            ev = ex_dump.get(col)
            xv = exp_dump.get(col)
            if ev != xv:
                report.field_diffs.append(
                    FieldDiff(
                        field_name=name,
                        column=col,
                        extracted=ev,
                        expected=xv,
                    )
                )

    return report
