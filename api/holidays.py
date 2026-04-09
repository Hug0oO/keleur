"""French school holiday dates by zone (A, B, C) for filtering.

Each French city falls in one of three school zones:
  Zone A: Besançon, Bordeaux, Clermont-Ferrand, Dijon, Grenoble, Limoges, Lyon, Poitiers
  Zone B: Aix-Marseille, Amiens, Caen, Lille, Nancy-Metz, Nantes, Nice,
          Orléans-Tours, Reims, Rennes, Rouen, Strasbourg
  Zone C: Créteil, Montpellier, Paris, Toulouse, Versailles

Toussaint, Noël, and Été are the same for all zones; Hiver and Printemps differ.

Each tuple is (start_date, end_date) inclusive.
"""

# Universal periods (same for all zones)
_UNIVERSAL = [
    ("2024-10-19", "2024-11-04"),  # Toussaint 2024
    ("2024-12-21", "2025-01-06"),  # Noël 2024
    ("2025-07-05", "2025-09-01"),  # Été 2025
    ("2025-10-18", "2025-11-03"),  # Toussaint 2025
    ("2025-12-20", "2026-01-05"),  # Noël 2025
    ("2026-07-04", "2026-08-31"),  # Été 2026 (approximate)
]

# Zone-specific Hiver and Printemps periods
_ZONE_SPECIFIC: dict[str, list[tuple[str, str]]] = {
    "A": [
        ("2025-02-22", "2025-03-10"),  # Hiver 2025
        ("2025-04-19", "2025-05-05"),  # Printemps 2025
        ("2026-02-07", "2026-02-23"),  # Hiver 2026
        ("2026-04-04", "2026-04-20"),  # Printemps 2026
    ],
    "B": [
        ("2025-02-22", "2025-03-10"),  # Hiver 2025
        ("2025-04-19", "2025-05-05"),  # Printemps 2025
        ("2026-02-07", "2026-02-23"),  # Hiver 2026
        ("2026-04-11", "2026-04-27"),  # Printemps 2026
    ],
    "C": [
        ("2025-02-15", "2025-03-03"),  # Hiver 2025
        ("2025-04-12", "2025-04-28"),  # Printemps 2025
        ("2026-02-14", "2026-03-02"),  # Hiver 2026
        ("2026-04-18", "2026-05-04"),  # Printemps 2026
    ],
}


def _holidays_for_zone(zone: str) -> list[tuple[str, str]]:
    return _UNIVERSAL + _ZONE_SPECIFIC.get(zone.upper(), _ZONE_SPECIFIC["B"])


def _holiday_condition(zone: str) -> str:
    parts = [
        f"CAST(observed_at AS DATE) BETWEEN '{start}' AND '{end}'"
        for start, end in _holidays_for_zone(zone)
    ]
    return "(" + " OR ".join(parts) + ")"


def holiday_clause(mode: str, zone: str = "B") -> str:
    """Return a SQL fragment for holiday filtering.

    mode:
      "all"     -> "" (no filter)
      "only"    -> AND (... holiday ranges ...)
      "exclude" -> AND NOT (... holiday ranges ...)
    zone: "A", "B", or "C"
    """
    if mode == "all":
        return ""
    cond = _holiday_condition(zone)
    if mode == "only":
        return f"AND {cond}"
    if mode == "exclude":
        return f"AND NOT {cond}"
    return ""
