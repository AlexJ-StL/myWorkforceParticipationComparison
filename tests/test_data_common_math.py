"""Exact-math tests for the shared helpers in ``data_common.py``.

Target analysis
---------------
``data_common.py`` is at 67% coverage. The uncovered lines 22-23 and 28-29 are
``_extract_year_month`` and ``_year_month_to_ordinal``. Both feed ordinal
regressions in ``analysis.py``; an off-by-one or a silently accepted malformed
date would shift every trend slope without raising anywhere upstream.

Failure modes considered
------------------------
* Non-zero-padded month/day values (``2024-3-5``).
* Truncated or over-long date strings.
* Non-numeric components and empty strings.
* Years before 1948 (negative ordinal) and the 1948-01 zero point.
"""

from __future__ import annotations

import itertools

import pytest

from data_common import _extract_year_month, _year_month_to_ordinal


@pytest.mark.parametrize(
    ("date_str", "expected"),
    [
        ("2024-03-15", (2024, 3)),
        ("1948-01-01", (1948, 1)),
        ("2026-09-30", (2026, 9)),
        ("2024-3-5", (2024, 3)),
        ("0001-01-01", (1, 1)),
        ("9999-12-31", (9999, 12)),
    ],
)
def test_extract_year_month_exact(date_str: str, expected: tuple[int, int]):
    assert _extract_year_month(date_str) == expected


@pytest.mark.parametrize(
    "date_str",
    ["", "2024", "2024-03", "abc-def-ghi", "2024-03-15-extra", "-2024-03-15"],
)
def test_extract_year_month_rejects_malformed_strings(date_str: str):
    with pytest.raises(ValueError):
        _extract_year_month(date_str)


@pytest.mark.parametrize(
    ("year_month", "expected"),
    [
        ((1948, 1), 0.0),
        ((1948, 12), 11.0),
        ((1949, 1), 12.0),
        ((2000, 1), 624.0),
        ((2026, 9), 944.0),
        ((1947, 12), -1.0),
        ((0, 1), -23376.0),
    ],
)
def test_year_month_to_ordinal_exact(year_month: tuple[int, int], expected: float):
    assert _year_month_to_ordinal(year_month) == expected


def test_year_month_to_ordinal_is_monthly_contiguous():
    """Every adjacent month must advance the ordinal by exactly one."""
    ordinals = [
        _year_month_to_ordinal((year, month))
        for year in (1999, 2000)
        for month in range(1, 13)
    ]
    assert [b - a for a, b in itertools.pairwise(ordinals)] == [1.0] * 23
