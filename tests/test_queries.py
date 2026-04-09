"""Tests for FilterParams and the WHERE-clause builder.

These guard the multi-network refactor: every clause must scope by network_id
so a query against `tan` can never leak rows from `ilevia`. Param-count must
also match the placeholder count exactly.
"""

from api.queries import FilterParams, _build_filters


def _placeholder_count(where: str) -> int:
    """Count `?` placeholders in a WHERE string. Inlined holiday clauses
    contain literal date strings, not `?`, so this should match `len(params)`.
    """
    return where.count("?")


# ── Network scoping ───────────────────────────────────────────────────


def test_minimal_filter_scopes_by_network():
    f = FilterParams(network_id="ilevia", route_id="R1")
    where, params = _build_filters(f)
    assert "network_id = ?" in where
    assert params[0] == "ilevia"
    assert params[1] == "R1"
    assert _placeholder_count(where) == len(params)


def test_stop_filter_passes_network_three_times():
    """The stop subquery joins stops twice + filters by network — 3 network refs."""
    f = FilterParams(network_id="tan", route_id="R1", stop_id="STOP_A")
    where, params = _build_filters(f)
    # network_id appears in: main WHERE, s2 lookup, s1 lookup
    assert params.count("tan") == 3
    assert _placeholder_count(where) == len(params)


def test_headsign_filter_includes_network_id():
    f = FilterParams(network_id="ilevia", route_id="R1", headsign="LILLE")
    where, params = _build_filters(f)
    assert "trips t" in where
    assert "t.network_id = ?" in where
    assert "LILLE" in params
    assert _placeholder_count(where) == len(params)


def test_all_filters_combined_param_count_matches():
    f = FilterParams(
        network_id="ilevia",
        route_id="R1",
        stop_id="S1",
        headsign="HS",
        days=14,
        time_from="07:00",
        time_to="09:30",
        days_of_week=[1, 2, 3, 4, 5],
        holidays="exclude",
    )
    where, params = _build_filters(f)
    assert _placeholder_count(where) == len(params)
    assert "07:00:00" in params
    assert "09:30:00" in params
    assert 14 in params


# ── include_stop / include_days_of_week toggles ───────────────────────


def test_include_stop_false_skips_stop_clause():
    f = FilterParams(network_id="ilevia", route_id="R1", stop_id="S1")
    where, params = _build_filters(f, include_stop=False)
    assert "s1.stop_id" not in where
    assert "S1" not in params
    assert _placeholder_count(where) == len(params)


def test_include_days_of_week_false_skips_dow_clause():
    f = FilterParams(
        network_id="ilevia", route_id="R1", days_of_week=[1, 2, 3]
    )
    where, params = _build_filters(f, include_days_of_week=False)
    assert "dayofweek" not in where
    assert _placeholder_count(where) == len(params)


# ── Holiday clause is inlined SQL, no params ─────────────────────────


def test_holiday_clause_does_not_add_params():
    f1 = FilterParams(network_id="ilevia", route_id="R1", holidays="all")
    w1, p1 = _build_filters(f1)
    f2 = FilterParams(network_id="ilevia", route_id="R1", holidays="exclude")
    w2, p2 = _build_filters(f2)
    f3 = FilterParams(network_id="ilevia", route_id="R1", holidays="only")
    w3, p3 = _build_filters(f3)

    # Holiday strings are inlined, so param lists must be identical
    assert p1 == p2 == p3
    assert "BETWEEN" not in w1  # "all" mode adds nothing
    assert "AND NOT" in w2
    assert "AND (" in w3


def test_holiday_clause_uses_network_zone():
    """Toulouse is zone C — its Hiver/Printemps dates differ from zone A/B."""
    # Toulouse is enabled=False but registered, so .get() returns it
    f = FilterParams(network_id="tisseo", route_id="R1", holidays="exclude")
    where, _ = _build_filters(f)
    # Zone C Hiver 2025 starts on 2025-02-15, not 2025-02-22 (zones A/B)
    assert "2025-02-15" in where


def test_unknown_network_falls_back_to_zone_b():
    f = FilterParams(network_id="nonexistent", route_id="R1", holidays="exclude")
    where, _ = _build_filters(f)
    # Zone B Hiver 2025
    assert "2025-02-22" in where
