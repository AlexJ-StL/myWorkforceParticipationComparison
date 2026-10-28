# U.S. Workforce Participation: Findings

Generated 2026-10-25 22:23 UTC from 38 FRED series and 4 BLS series (1939-01..2026-09 monthly, 1966-01..2026-04 quarterly earnings).

**Data gap:** no CPS field work was conducted in October 2025 (2025 federal government shutdown), so every monthly series is missing that month. Gaps are left as-is, never interpolated.

**New in this release:** Added prime-age participation and sector headcount/wage comparisons. Weekly-hours values are omitted because the configured BLS series are not hours measures.

## Participation levels

| | first | peak | latest | change since first | change since peak |
|---|---|---|---|---|---|
| All | 58.6% (1948-01) | 67.3% (2000-01) | 61.8% (2026-09) | +3.2 pp | -5.5 pp |
| Men | 86.7% (1948-01) | 87.4% (1949-10) | 67.2% (2026-09) | -19.5 pp | -20.2 pp |
| Women | 32.0% (1948-01) | 60.3% (2000-04) | 56.7% (2026-09) | +24.7 pp | -3.6 pp |
| **Gender gap** (men - women) | 54.7 pp (1948-01) | 54.7 pp (1948-01) | 10.5 pp (2026-09) | -44.2 pp | -44.2 pp |

The gender gap peaked at 54.7 pp in 1948-01 and stands at 10.5 pp in 2026-09 -- a narrowing of 44.2 pp. Men's rate fell 19.5 pp from its 1949-10 peak of 87.4% while women's rose 24.7 pp from 32.0%. Total participation is 5.5 pp below its 2000-01 peak of 67.3%.

## Prime-Age (25–54) Participation vs. Demographic Aging

Participation levels (percent):

| Group | First | Peak | Latest |
|---|---|---|---|
| Overall 16+ | 58.6% (1948-01) | 67.3% (2000-01) | 61.8% (2026-09) |
| Prime-age total | 64.2% (1948-01) | 84.6% (1999-01) | 83.7% (2026-09) |
| Prime-age men | 96.7% (1948-01) | 97.9% (1954-09) | 89.5% (2026-09) |
| Prime-age women | 33.5% (1948-01) | 78.5% (2026-03) | 78.0% (2026-09) |

OLS trends (percentage points per year):

| Period | Overall 16+ | Prime-age total | Prime-age men | Prime-age women |
|---|---:|---:|---:|---:|
| 1948-2000 | +0.194 pp/yr | +0.426 pp/yr | -0.118 pp/yr | +0.924 pp/yr |
| 2000-2019 | -0.261 pp/yr | -0.127 pp/yr | -0.171 pp/yr | -0.084 pp/yr |
| 2019-2026 | -0.026 pp/yr | +0.314 pp/yr | +0.174 pp/yr | +0.443 pp/yr |

From 2000-04 to the latest common observation (2026-09), the 16+ participation rate changed -5.50 pp and prime-age participation changed -0.70 pp. The difference in declines (16+ minus prime-age) was +4.80 pp.

## Trend regimes (OLS on monthly observations)

| period | men | women | total | gap |
|---|---|---|---|---|
| 1948-2000 | -0.248 pp/yr (R2 0.94) | +0.596 pp/yr (R2 0.98) | +0.194 pp/yr (R2 0.90) | -0.844 pp/yr (R2 0.99) |
| 2000-2019 | -0.349 pp/yr (R2 0.93) | -0.182 pp/yr (R2 0.84) | -0.261 pp/yr (R2 0.91) | -0.167 pp/yr (R2 0.89) |
| 2019-2026 | -0.143 pp/yr (R2 0.25) | +0.077 pp/yr (R2 0.07) | -0.026 pp/yr (R2 0.01) | -0.220 pp/yr (R2 0.76) |

Women's participation rose steadily through 2000 and then turned negative at -0.182 pp/yr (2000-2019). Men's decline continued at roughly -0.349 pp/yr. The gap closed fastest in the earlier era, when women's gains and men's declines reinforced each other; after 2000 both genders drifted down together.

## COVID-19 shock and recovery

| | Dec 2019 | 2020 trough | latest | vs baseline | recovered |
|---|---|---|---|---|---|
| All | 63.3% | 60.1% (2020-04, -3.2 pp) | 61.8% | -1.5 pp | not yet |
| Men | 69.2% | 66.1% (2020-04, -3.1 pp) | 67.2% | -2.0 pp | not yet |
| Women | 57.8% | 54.6% (2020-04, -3.2 pp) | 56.7% | -1.1 pp | 2024-08 (+52 mo) |

April 2020 was the sharpest monthly break in the entire 78-year series. By the latest observation the level has recovered toward, but not back to, the pre-pandemic baseline.

## Median usual weekly earnings (full-time wage & salary workers)

| | 1979 real | latest real | real change | 1979 nominal | latest nominal |
|---|---|---|---|---|---|
| Men | $408 | $414 | +1.5% | $282 | $1380 (+389%) |
| Women | $251 | $341 | +35.9% | $174 | $1136 (+553%) |
| Total | $335 | $378 | +12.8% | $232 | $1258 (+442%) |

Women's real median weekly earnings grew +35.9% since 1979 while men's changed +1.5% -- men are essentially flat in real terms over 47 years. The women-to-men earnings ratio rose from 61.7% (1979-01) to 82.3% (2026-04), +20.6 pp.

**Association with the participation gap:** the earnings ratio and the participation gap move together over 1979-2026 (correlation r = -0.97 contemporaneous, n = 189). This is an association, not evidence of causation.

## Average Weekly Hours Worked: Not Reported

The configured BLS series LNS12032194 and LNS12032195 are employment levels for part-time work for economic reasons, not average weekly hours. Their cached values are excluded from this report until valid hours series are selected.

## Counts and composition

| | 1948 | latest | growth |
|---|---|---|---|
| Labor force total | 60.1M | 170.3M | 2.83x |
| Labor force men | 43.2M | 89.4M | 2.07x |
| Labor force women | 16.9M | 80.9M | 4.79x |
| Employment total | 58.1M | 163.2M | 2.81x |

Women's share of the labor force went from 28.1% (1948-01) to 47.5% (2026-09). The employment-population ratio stands at 59.2% versus 56.6% in 1948.

## Internal consistency checks

| check | mean abs. diff | max abs. diff |
|---|---|---|
| men + women = total labor force (thousands) | 0.1 | 1.0 |
| implied vs published rate, total (pp) | 0.03 | 0.05 |
| implied vs published rate, men (pp) | 0.02 | 0.07 |
| implied vs published rate, women (pp) | 0.03 | 0.21 |

Labor force levels by gender sum to the published total almost exactly. Implied rates (labor force / population) track the published rates within rounding; the residual differences come from seasonal adjustment and the not-seasonally-adjusted population levels.

## Shift-Share: Not Reported

The current decomposition is not publishable: its between-group term uses population levels instead of population shares, and its youth/prime-age terms overlap. The diagnostic values remain in `summary.json` with status `not_publishable`; do not interpret or cite them.

## Macroeconomic Context: Purchasing Power & Sector Distribution

**Purchasing Power Trajectory:** The purchasing power index went from 8.08 (1964-01) to 9.69 (2026-09), a change of +19.97%. Over the same span, CPI-U grew +986.94% while nominal average hourly earnings (AHETPI) grew +1204.00%.

**Private Employment per Capita:** Private payroll employment equaled 52.79% of the civilian population at its 1999-12 peak and 49.25% in 2026-09. The share is +29.39% above its 1948-01 level.

**Public Sector Share:** Government employment as a share of total payrolls peaked at 19.36% in 1975-07 and stands at 14.67% in 2026-09. The change from earliest available data (1939-01) is +1.34 percentage points.

**Public Debt to GDP Ratio:** The earliest recorded value is 40.34% (1966-01), with a peak of 132.66% in 2020-04 and a latest value of 122.59% (2026-01).


## Sector Headcount & Physical Labor Wage Dynamics

Headcount levels (thousands of persons):

| Sector | Peak (thousands) | Latest (thousands) |
|---|---:|---:|
| Manufacturing | 19,553.0 (1979-06) | 12,652.0 (2026-09) |
| Construction | 8,364.0 (2026-09) | 8,364.0 (2026-09) |
| Agriculture | 9,058.0 (1949-06) | 2,636.0 (2026-09) |

Real hourly wages, adjusted by CPI-U:

| Sector | First real hourly wage | Latest real hourly wage | Total change vs. CPI-U |
|---|---:|---:|---:|
| Construction | $4.80 (1947-01) | $11.66 (2026-09) | +143.09% |
| Manufacturing | $4.80 (1947-01) | $8.98 (2026-09) | +87.34% |

Sector wage as a percentage of private-sector average hourly earnings:

| Sector | Peak ratio to private AHE | Current ratio to private AHE |
|---|---:|---:|
| Construction | 145.16% (1973-01) | 120.25% (2026-09) |
| Manufacturing | 107.78% (1985-07) | 92.67% (2026-09) |

## Caveats

- **Correlation is not causation.** All statistics are descriptive.
- **October 2025 is missing** from every CPS series (shutdown). No interpolation is applied.
- Participation rates are seasonally adjusted.
- Prime-age sex-specific LFPR uses BLS observations fetched in bounded year windows; missing observations remain missing.
- BLS weekly-hours figures are omitted: LNS12032194/195 are employment levels for part-time work for economic reasons, not hours.
- The shift-share decomposition is omitted from reported results because its between-group and age-group terms are currently invalid.