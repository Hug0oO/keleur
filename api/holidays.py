"""Zone B (Lille) school holiday dates for filtering."""

# Each tuple is (start_date, end_date) inclusive
ZONE_B_HOLIDAYS = [
    # 2024-2025
    ("2024-10-19", "2024-11-04"),  # Toussaint 2024
    ("2024-12-21", "2025-01-06"),  # Noel 2024
    ("2025-02-22", "2025-03-10"),  # Hiver 2025 (Zone B)
    ("2025-04-19", "2025-05-05"),  # Printemps 2025 (Zone B)
    ("2025-07-05", "2025-09-01"),  # Ete 2025
    # 2025-2026
    ("2025-10-18", "2025-11-03"),  # Toussaint 2025
    ("2025-12-20", "2026-01-05"),  # Noel 2025
    ("2026-02-07", "2026-02-23"),  # Hiver 2026 (Zone B)
    ("2026-04-11", "2026-04-27"),  # Printemps 2026 (Zone B)
]


def _holiday_condition() -> str:
    """Build the OR-joined BETWEEN clauses for all holiday periods."""
    parts = [
        f"CAST(observed_at AS DATE) BETWEEN '{start}' AND '{end}'"
        for start, end in ZONE_B_HOLIDAYS
    ]
    return "(" + " OR ".join(parts) + ")"


def holiday_clause(mode: str) -> str:
    """Return a SQL fragment for holiday filtering.

    mode:
      "all"     -> "" (no filter)
      "only"    -> AND (... holiday ranges ...)
      "exclude" -> AND NOT (... holiday ranges ...)
    """
    if mode == "all":
        return ""
    cond = _holiday_condition()
    if mode == "only":
        return f"AND {cond}"
    if mode == "exclude":
        return f"AND NOT {cond}"
    return ""
