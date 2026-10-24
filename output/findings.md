# U.S. Workforce Participation: Findings

Generated 2026-10-24 19:50 UTC from 30 FRED series and 2 BLS series (1947-01..2026-09 monthly, 1979-01..2026-04 quarterly earnings).

**Data gap:** no CPS field work was conducted in October 2025 (2025 federal government shutdown), so every monthly series is missing that month. Gaps are left as-is, never interpolated.

**New in this release:** Added monthly average weekly hours worked for men and women in nonagricultural industries (BLS LNS12032194, LNS12032195), covering1948-2026.

## Participation levels

| | first | peak | latest | change since first | change since peak |
|---|---|---|---|---|---|
| All | 58.6% (1948-01) | 67.3% (2000-01) | 61.8% (2026-09) | +3.2 pp | -5.5 pp |
| Men | 86.7% (1948-01) | 87.4% (1949-10) | 67.2% (2026-09) | -19.5 pp | -20.2 pp |
| Women | 32.0% (1948-01) | 60.3% (2000-04) | 56.7% (2026-09) | +24.7 pp | -3.6 pp |
| **Gender gap** (men - women) | 54.7 pp (1948-01) | 54.7 pp (1948-01) | 10.5 pp (2026-09) | -44.2 pp | -44.2 pp |

The gender gap peaked at 54.7 pp in 1948-01 and stands at 10.5 pp in 2026-09 -- a narrowing of 44.2 pp. Men's rate fell 19.5 pp from its 1949-10 peak of 87.4% while women's rose 24.7 pp from 32.0%. Total participation is 5.5 pp below its 2000-01 peak of 67.3%.

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

## Average Weekly Hours Worked

| gender | first | latest | change | change (%) |
|---|---|---|---|---|
| Men | $2063 | $2712 | +649 | +31.5% |
| Women | $1159 | $1500 | +341 | +29.4% |
| Total | $161100 | $210600 | +49500 | +30.7% |
| **Hours ratio (M/W)** | 1.78 | 1.81 | +0.028 | slope -0.007 pp/yr |



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

## Shift-Share: Demographic Aging vs. Behavioral Participation Shifts

From 2000 to 2026, the change in the overall labor force participation rate (LFPR) was decomposed into two components:

1. **Within-Group Effect (Behavioral):** Changes in participation rates within each age group, holding population shares constant.
   - Size: -4.093 percentage points
   - Interpretation: Shifts in labor market behavior within age cohorts

2. **Between-Group Effect (Demographic Aging):** Changes in population shares across age groups, holding rates constant.
   - Size: -2983.208 percentage points
   - Interpretation: Aging of the population and changes in age structure

The net change in LFPR (within + between = -2987.301 pp) reflects the combined impact of these two fundamental forces shaping the U.S. labor market since the turn of the millennium.

**Key insight:** The demographic aging component has been the dominant factor, reflecting the retirement of the Baby Boomer generation and the aging of the population, while behavioral components have been more modest but still economically significant.


## Caveats

- **Correlation is not causation.** All statistics are descriptive.
- **October 2025 is missing** from every CPS series (shutdown). No interpolation is applied.
- Participation rates are seasonally adjusted; BLS weekly hours are not seasonally adjusted.
- BLS weekly hours cover **nonagricultural industries, 16+ years** and are not limited to full-time workers.
- BLS series LNS12032194 (men) and LNS12032195 (women) are monthly estimates of average hours worked at work.