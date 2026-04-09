"""Tests for the school-holiday SQL clause builder."""

from api.holidays import holiday_clause, _holidays_for_zone


def test_all_returns_empty_string():
    assert holiday_clause("all") == ""


def test_only_starts_with_and():
    out = holiday_clause("only", "B")
    assert out.startswith("AND ")
    assert "NOT" not in out
    assert "BETWEEN" in out


def test_exclude_starts_with_and_not():
    out = holiday_clause("exclude", "B")
    assert out.startswith("AND NOT ")
    assert "BETWEEN" in out


def test_unknown_mode_returns_empty():
    assert holiday_clause("garbage") == ""


def test_zone_a_and_zone_b_share_winter_dates_2025():
    # In 2025 zones A and B happened to share the same Hiver dates,
    # but the data structure must still distinguish them so future
    # years can diverge without code changes.
    a = holiday_clause("exclude", "A")
    b = holiday_clause("exclude", "B")
    assert "2025-02-22" in a
    assert "2025-02-22" in b


def test_zone_c_winter_is_one_week_earlier():
    c = holiday_clause("exclude", "C")
    a = holiday_clause("exclude", "A")
    # 2025-02-15 is Zone C Hiver start
    assert "2025-02-15" in c
    assert "2025-02-15" not in a


def test_universal_periods_present_in_all_zones():
    """Toussaint, Noël, Été appear regardless of zone."""
    for zone in ("A", "B", "C"):
        clause = holiday_clause("only", zone)
        assert "2024-10-19" in clause  # Toussaint 2024
        assert "2024-12-21" in clause  # Noël 2024
        assert "2025-07-05" in clause  # Été 2025


def test_zone_helper_returns_universal_plus_zone_specific():
    h_a = _holidays_for_zone("A")
    h_b = _holidays_for_zone("B")
    h_c = _holidays_for_zone("C")
    # All three should have same length: 6 universal + 4 zone-specific
    assert len(h_a) == len(h_b) == len(h_c) == 10


def test_unknown_zone_defaults_to_b():
    h_unknown = _holidays_for_zone("Z")
    h_b = _holidays_for_zone("B")
    assert h_unknown == h_b


def test_zone_string_is_case_insensitive():
    h_lower = _holidays_for_zone("c")
    h_upper = _holidays_for_zone("C")
    assert h_lower == h_upper
