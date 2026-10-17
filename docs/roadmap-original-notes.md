# Master Data Retrieval & Audit Roadmap (original notes)

> **Archived.** This is the original working note, retained for provenance. Its
> content is consolidated and expanded in [roadmap.md](roadmap.md); prefer that
> page.

---

#### 1. Macro Labor Force Participation (1950–Present)

* **Primary Source:** Federal Reserve Economic Data (FRED) / Bureau of Labor Statistics (BLS)
* **Direct CSV Downloads / API Series IDs:**
* `LNS11300001` — Male Labor Force Participation Rate (Monthly)
* `LNS11300002` — Female Labor Force Participation Rate (Monthly)
* `CIVPART` — Total Civilian Labor Force Participation Rate (Monthly)

* **Execution Step:** Pull series, resample to annual averages (`.resample('YE').mean()`), and plot male vs. female participation rates against aggregate workforce capacity to model the labor substitution effect.

---

#### 2. Survey Wage & Income Data (BLS / Census CPS)

* **Primary Source:** St. Louis Fed (FRED) & U.S. Census Bureau
* **Weekly Earnings (Quarterly FRED Series):**
* `LEU0252881900Q` — Men's Nominal Median Weekly Earnings (Full-Time)
* `LEU0252882800Q` — Women's Nominal Median Weekly Earnings (Full-Time)
* `LES1252881900Q` — Men's Real Median Weekly Earnings (1982–84 Constant $)
* `LES1252882800Q` — Women's Real Median Weekly Earnings (1982–84 Constant $)

* **Annual Census P-Series Tables (Census ASEC):**
* **Table P-8:** *Income Distribution by Sex (Full-Time, Year-Round Workers)*
* **Table P-10:** *Mean and Median Income by Sex and Age* (Used to audit the gap between average and median male earnings caused by top-tail outliers)

---

#### 3. Unfiltered Record-Level Microdata & Truncation (IPUMS CPS)

* **Primary Source:** Integrated Public Use Microdata Series (`cps.ipums.org`)
* **Extract Variables to Select:**
* `YEAR` & `MONTH` — Survey period
* `SEX` — Respondent gender designation
* `PAIDHOUR` — Hourly status indicator (`2` = Paid hourly, `1` = Non-hourly/salaried)
* `HOURWAGE` — Reported hourly pay rate
* `INCWAGE` — Total annual wage/salary income
* `EARNWT` / `ASECWTH` — Sampling weights required for proper national expansion

* **Execution Step:** Load raw microdata into Python, filter out non-hourly or non-working respondents, calculate top 1% cutoffs per group (`df['INCWAGE'].quantile(0.99)`), and compare trimmed means against raw medians.

---

#### 4. Administrative Tax Record Data (Social Security Administration)

* **Primary Source:** SSA Office of Research, Evaluation, and Statistics (`ssa.gov/policy/docs/statcomps/supplement/`)
* **Target Section:** *Annual Statistical Supplement* — Section 4.B (Employment and Earnings)
* **Target Tables:**
* **Table 4.B3:** Total covered worker counts, aggregate wage volume, mean earnings, and median earnings by sex and age.
* **Table 4.B7:** Distribution of workers classified by exact wage brackets (e.g., $5k increments) separated by sex.
* **Table 4.B9:** Counts and percentages of male vs. female earners reaching or exceeding the Social Security taxable wage cap.

* **Execution Step:** Download Table 4.B3 and 4.B7 XLS/CSV files. Compare SSA tax-file median earnings directly against Census/BLS survey medians to identify survey non-response bias, sampling skew, or underreporting.