"""Tests for field identity + dedup correctness (audit canon).

Four failure-mode categories covered (from audit findings):

F1 (grain uniqueness): same field_name across fieldsets in one explore must
    raise. Looker's validator prevents this at definition time, but
    flatten_explore defends against API anomalies / upstream bugs.

F2 / F3 (refinement drift): seen_in_* keyed by field_name alone collapses
    refinement-driven sql + tag divergence across explores. The new
    definition_hash + definition_variant_count make the drift queryable.

F5 (from: aliasing): customer.email vs representative.email are distinct
    field_names (seen_in_* keeps them separate per Looker semantics), but
    definition_appearances_count merges them via (original_view, leaf_name)
    so users can answer the cross-alias lineage question.

F7 (dynamic_fields): query-scoped fields (`dynamic: true`) have no stable
    identity across queries; excluded from seen_in_* and given empty hash.
"""

from __future__ import annotations

import pytest

from looker_fields.extract import enrich_seen_in, flatten_explore


def _explore(name: str, *, dims=None, filters_=None) -> dict:
    return {
        "name": name,
        "model_name": None,
        "project_name": "p",
        "fields": {
            "dimensions": dims or [],
            "measures": [],
            "filters": filters_ or [],
            "parameters": [],
        },
    }


def _field(name: str, **overrides) -> dict:
    base = {
        "name": name,
        "view": "users",
        "type": "string",
        "category": "dimension",
        "project_name": "p",
        "original_view": "users",
        "sql": "${TABLE}.email",
        "tags": [],
        "dynamic": False,
        "times_used": 0,
    }
    base.update(overrides)
    return base


# --------------------------------------------------------------------------
# F1 — grain uniqueness guarded by flatten_explore assertion
# --------------------------------------------------------------------------

def test_f1_grain_violation_within_explore_raises():
    """Same name in dimensions[] AND filters[] of one explore must raise.

    Looker's validator prevents this at definition time, but flatten_explore
    defends against API anomalies by raising loud.
    """
    raw = _explore(
        "test_explore",
        dims=[_field("users.email", category="dimension")],
        filters_=[_field("users.email", category="filter")],
    )
    with pytest.raises(ValueError, match="Grain violation"):
        flatten_explore(raw, "test_model")


# --------------------------------------------------------------------------
# F2 / F3 — refinement-like sql+tag divergence detected by definition_hash
# --------------------------------------------------------------------------

def test_f2_refinement_drift_visible_via_definition_hash():
    """Refinement-applied sql + tag divergence across two explores collapses
    seen_in_* (keyed by field_name) but is surfaced by definition_variant_count."""
    explore_a = _explore("explore_a", dims=[
        _field("users.email", sql="${TABLE}.email", tags=["pii"]),
    ])
    explore_b = _explore("explore_b", dims=[
        _field(
            "users.email",
            sql="REGEXP_REPLACE(${TABLE}.email, '@.*', '@redacted')",
            tags=[],
        ),
    ])

    records = (
        flatten_explore(explore_a, "model_a")
        + flatten_explore(explore_b, "model_b")
    )
    records = enrich_seen_in(records)

    # seen_in_* still collapses (legacy behavior preserved — backward compat)
    assert all(r.seen_in_model_count == 2 for r in records)
    assert all(r.seen_in_explore_count == 2 for r in records)

    # NEW: definition_hash differs per row — the drift signal
    hashes = {r.definition_hash for r in records}
    assert len(hashes) == 2, f"expected 2 distinct hashes, got {hashes}"

    # NEW: definition_variant_count makes drift queryable on every row
    assert all(r.definition_variant_count == 2 for r in records)


def test_f2_no_drift_when_definitions_identical():
    """Vanilla case: same field name with identical definition → variant_count=1."""
    explore_a = _explore("explore_a", dims=[_field("users.email")])
    explore_b = _explore("explore_b", dims=[_field("users.email")])

    records = (
        flatten_explore(explore_a, "model_a")
        + flatten_explore(explore_b, "model_b")
    )
    records = enrich_seen_in(records)

    hashes = {r.definition_hash for r in records}
    assert len(hashes) == 1
    assert all(r.definition_variant_count == 1 for r in records)


def test_definition_hash_whitespace_normalized():
    """Cosmetic sql whitespace must not split semantically-identical definitions."""
    explore_a = _explore("explore_a", dims=[
        _field("users.email", sql="${TABLE}.email"),
    ])
    explore_b = _explore("explore_b", dims=[
        _field("users.email", sql="  ${TABLE}.email  "),
    ])
    explore_c = _explore("explore_c", dims=[
        _field("users.email", sql="${TABLE}.email\n"),
    ])

    records = (
        flatten_explore(explore_a, "model_a")
        + flatten_explore(explore_b, "model_b")
        + flatten_explore(explore_c, "model_c")
    )
    records = enrich_seen_in(records)

    hashes = {r.definition_hash for r in records}
    assert len(hashes) == 1, f"whitespace-only diff split hashes: {hashes}"


# --------------------------------------------------------------------------
# F5 — from: aliasing cross-alias aggregation via (original_view, leaf)
# --------------------------------------------------------------------------

def test_f5_from_aliasing_distinct_seen_in_but_merged_definition_appearances():
    """`person` joined as `customer` AND `representative` → distinct field_names
    (seen_in_* separate per Looker semantics) BUT definition_appearances_count
    merges them via (original_view='person', leaf_name='email')."""
    # customer.email — alias view, original_view=person
    explore_a = _explore("explore_a", dims=[
        _field("customer.email", view="customer", original_view="person"),
    ])
    # representative.email — different alias, same source view
    explore_b = _explore("explore_b", dims=[
        _field(
            "representative.email",
            view="representative",
            original_view="person",
        ),
    ])

    records = (
        flatten_explore(explore_a, "model_a")
        + flatten_explore(explore_b, "model_b")
    )
    records = enrich_seen_in(records)

    by_name = {r.field_name: r for r in records}

    # seen_in_* keeps them separate (different field_name)
    assert by_name["customer.email"].seen_in_model_count == 1
    assert by_name["representative.email"].seen_in_model_count == 1

    # NEW: definition_appearances_count merges via (original_view='person', leaf='email')
    assert by_name["customer.email"].definition_appearances_count == 2
    assert by_name["representative.email"].definition_appearances_count == 2


# --------------------------------------------------------------------------
# F7 — dynamic_fields excluded from seen_in_* aggregation
# --------------------------------------------------------------------------

def test_f7_dynamic_fields_excluded_from_seen_in():
    """Query-scoped dynamic fields have no stable identity across queries;
    excluded from seen_in_* counts (zeroed) and definition_hash (empty)."""
    explore_a = _explore("explore_a", dims=[
        _field("calc.revenue_x2", dynamic=True),
    ])
    explore_b = _explore("explore_b", dims=[
        _field("calc.revenue_x2", dynamic=True),
    ])

    records = (
        flatten_explore(explore_a, "model_a")
        + flatten_explore(explore_b, "model_b")
    )
    records = enrich_seen_in(records)

    for r in records:
        assert r.dynamic is True
        assert r.seen_in_model_count == 0, "dynamic must be excluded from seen_in_*"
        assert r.seen_in_explore_count == 0
        assert r.total_times_used == 0
        assert r.seen_models == []
        assert r.seen_explores == []
        assert r.definition_hash == "", "dynamic gets empty hash"
        assert r.definition_variant_count == 0
        assert r.definition_appearances_count == 0


def test_f7_static_fields_unaffected_when_dynamic_present():
    """Static fields aggregate normally even when dynamic fields are mixed in."""
    explore_static = _explore("static_explore", dims=[
        _field("users.email"),
    ])
    explore_dynamic = _explore("dynamic_explore", dims=[
        _field("calc.revenue_x2", dynamic=True),
    ])

    records = (
        flatten_explore(explore_static, "m1")
        + flatten_explore(explore_dynamic, "m2")
    )
    records = enrich_seen_in(records)

    by_name = {r.field_name: r for r in records}
    # static field aggregates normally
    assert by_name["users.email"].seen_in_model_count == 1
    assert by_name["users.email"].definition_variant_count == 1
    # dynamic still excluded
    assert by_name["calc.revenue_x2"].seen_in_model_count == 0
