"""Catalog integrity: series.py must stay internally consistent and in sync
with the column mappings in labor_data.py."""

from __future__ import annotations

import dataclasses

import pytest

import labor_data
from series import ALL_SIDS, BY_SID, PALETTE, SERIES, SeriesSpec, sid

PALETTE_KEYS = {"bg", "grid", "muted", "men", "women", "total", "accent"}


def test_series_sids_are_unique():
    sids = [spec.sid for spec in SERIES]
    duplicates = {s for s in sids if sids.count(s) > 1}
    assert not duplicates, f"duplicate sids in catalog: {duplicates}"


def test_by_sid_mirrors_series_tuple():
    assert set(BY_SID) == {spec.sid for spec in SERIES}
    assert len(BY_SID) == len(SERIES)


def test_all_sids_preserves_catalog_order():
    assert ALL_SIDS == tuple(spec.sid for spec in SERIES)


@pytest.mark.parametrize(
    "mapping_name",
    ["MONTHLY_COLUMNS", "QUARTERLY_COLUMNS", "HOURLY_COLUMNS"],
)
def test_labor_data_mappings_resolve_in_catalog(mapping_name):
    """Every series labor_data wants must exist in the catalog."""
    mapping = getattr(labor_data, mapping_name)
    for series_id in mapping:
        assert series_id in BY_SID, (
            f"{series_id} in {mapping_name} missing from catalog"
        )


def test_column_renames_are_unique_within_each_mapping():
    for mapping_name in ("MONTHLY_COLUMNS", "QUARTERLY_COLUMNS", "HOURLY_COLUMNS"):
        mapping = getattr(labor_data, mapping_name)
        names = list(mapping.values())
        assert len(names) == len(set(names)), f"{mapping_name} renames collide"


@pytest.mark.parametrize(
    ("sex", "track", "expected"),
    [
        ("total", "rate", "CIVPART"),
        ("men", "rate", "LNS11300001"),
        ("women", "rate", "LNS11300002"),
        ("total", "level", "CLF16OV"),
        ("men", "level", "LNS11000001"),
        ("women", "level", "LNS11000002"),
        ("total", "price", "CPIAUCSL"),
        # ("total", "earnings_nominal") is ambiguous -- see the dedicated test below.
        ("men", "earnings_nominal", "LES1252881800Q"),
        ("women", "earnings_nominal", "LES1252882700Q"),
        ("total", "earnings_real", "LES1252881600Q"),
        ("men", "earnings_real", "LES1252881900Q"),
        ("women", "earnings_real", "LES1252882800Q"),
    ],
)
def test_sid_resolves_documented_pairs(sex, track, expected):
    assert sid(sex, track) == expected


def test_sid_total_earnings_nominal_is_ambiguous():
    """Three catalog entries match ("total", "earnings_nominal"): the two hourly
    CES/AHETPI series and the weekly LES series. sid() resolves to the first in
    catalog order. This test exists to keep that landmine visible: sid() has no
    in-repo callers, so the ambiguity is latent, not active."""
    matches = [
        spec.sid
        for spec in SERIES
        if spec.sex == "total" and spec.track == "earnings_nominal"
    ]
    assert matches == ["CES0500000003", "AHETPI", "LES1252881500Q"]
    assert sid("total", "earnings_nominal") == "CES0500000003"


@pytest.mark.parametrize(
    ("sex", "track"),
    [("men", "price"), ("women", "price")],
)
def test_sid_raises_for_absent_pairs(sex, track):
    with pytest.raises(KeyError, match="No series for"):
        sid(sex, track)


def test_series_specs_are_frozen():
    spec = SERIES[0]
    with pytest.raises(dataclasses.FrozenInstanceError):
        spec.label = "mutated"  # type: ignore[misc]


def test_specs_have_non_empty_metadata():
    for spec in SERIES:
        assert spec.sid and spec.label and spec.short and spec.units
        assert spec.seasonal in {"SA", "NSA"}


def test_population_series_are_not_seasonally_adjusted():
    """AGENTS.md: LNU population levels are NSA."""
    assert BY_SID["LNU00000001"].seasonal == "NSA"
    assert BY_SID["LNU00000002"].seasonal == "NSA"
    assert BY_SID["CIVPART"].seasonal == "SA"


def test_series_spec_is_a_dataclass_with_expected_defaults():
    spec = SeriesSpec("X", "label", "short", "rate", "total", "percent")
    assert spec.seasonal == "SA"


def test_palette_has_exactly_the_expected_keys():
    assert set(PALETTE) == PALETTE_KEYS


def test_palette_values_are_hex_colors():
    for name, value in PALETTE.items():
        assert value.startswith("#"), f"{name} is not a hex color"
        assert len(value) == 7, f"{name} is not a #rrggbb color"
