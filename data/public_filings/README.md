# Public filings credit case

This directory contains an offline, historical corporate credit case using the SEC's public companyfacts XBRL API. It is separate from the workbench's fictional counterparty books and illustrative ratings.

| Issuer | CIK | Fiscal years | Original 2024 filing |
|---|---|---|---|
| The Coca-Cola Company (KO) | 0000021344 | 2022–2024 | [2024 Form 10-K](https://investors.coca-colacompany.com/filings-reports/annual-filings-10-k/content/0000021344-25-000011/ko-20241231.htm) |
| PepsiCo, Inc. (PEP) | 0000077476 | 2022–2024 | [2024 Form 10-K](https://www.sec.gov/Archives/edgar/data/77476/000007747625000007/pep-20241228.htm) |
| Keurig Dr Pepper Inc. (KDP) | 0001418135 | 2022–2024 | [2024 Form 10-K](https://www.sec.gov/Archives/edgar/data/1418135/000141813525000013/kdp-20241231.htm) |

The SEC describes companyfacts and its standard-taxonomy/entity-wide coverage in its [API documentation](https://www.sec.gov/search-filings/edgar-application-programming-interfaces). No credentials are needed for the bundled cache.

## Reproduce

Run from the repository root:

```bash
PYTHONPATH=src .venv/bin/python -m sentinel_risk.public_filings
```

This verifies each uncompressed source SHA256, rebuilds the case offline, and writes `outputs/`. `sources.json` records the exact URL, issuer, retrieval timestamp, raw byte count, compressed cache path and SHA256. The three gzip files contain complete API responses. Opening the app and rebuilding the default case use this local cache.

To deliberately refresh the raw caches, identify your project and actual contact to the SEC:

```bash
PYTHONPATH=src .venv/bin/python -m sentinel_risk.public_filings --refresh \
  --user-agent 'YourProject your-real-contact@example.org'
```

Replace the example contact before use. The fixed study cutoff remains April 1, 2025 even after a refresh. Preserve the current cache/manifest if you need the identical historical artifact; SEC may revise its API data. Refresh writes content-addressed files and only replaces the source manifest after all three downloads succeed. Requests are sequential with a pause; access failures stop the refresh with an error.

## Selection and accounting

- Information cutoff: `2025-04-01`. Annual periods end in 2022, 2023 and 2024.
- Select the earliest eligible Form 10-K accession carrying an annual revenue period of 330–400 days ending in the target year. The XBRL `fy` field is not treated as the fact's period year.
- For every other field, require that same accession, the exact balance-sheet end date and, for income/cash flow, the same start and end dates. Only USD facts are eligible. Later comparative restatements, amendments, quarters and other units are excluded.
- Duplicate conflicting values fail explicitly. Missing fields remain null. No missing observation becomes zero. Three Coca-Cola liabilities values are derived as assets less consolidated equity, which includes noncontrolling interests.
- PepsiCo uses `PaymentsToAcquireProductiveAssets` for capital spending; the mapping is checked against its cash-flow statement. The cash flows in this case are not adjusted for asset disposal proceeds, so PepsiCo's issuer-defined non-GAAP FCF differs from the study's CFO less capital expenditure.
- PepsiCo reports `InterestExpense` as net interest expense and other. This is preserved under `net_interest_and_other`, while canonical gross `interest_expense` stays null in all three years, including CSV exports. KDP's 2024 gross interest-expense concept is unavailable in the chosen standard taxonomy/filing. It stays null. No net-interest or lease-interest value is substituted, and interest coverage is omitted from the peer metrics.
- USD are preserved in exports; the UI divides monetary values by one million for display. Ratios are fractions in JSON/CSV. Percentage presentation multiplies by 100. Balance sheet ratios use period-end balances.
- Eleven ratio definitions produce 96 numeric observations over nine rows; first-year growth lacks a prior-year observation in the study and remains null. Formulas are in the JSON and UI. The peer median includes all three selected issuers; valid observation counts are shown.

## Analytical scope

149 reported fields, 3 labeled derivations and 4 missing gross-interest fields cover P&L, balance sheet and cash flow. Twelve monitoring checks (four per issuer) create five research alerts. Those thresholds are illustrative analyst screens, not loan covenants or external credit ratings.

This is a selected US corporate case. PepsiCo includes foods, and its fiscal year differs from the calendar year. KO's concentrate/bottling model and KDP's coffee mix limit comparability. The dataset covers these three US issuers and excludes bank, fund, news and client-exposure data.

The generated reviews combine calculated results with brief cited company context, including KO's tax litigation deposit and KDP's impairments. They are analyst drafts. They do not assign PDs, agency grades, internal ratings, lending limits or onboarding decisions.

## Outputs

- `case_study.json`: all source metadata, field-level lineage, formulas, peer medians, monitoring and review drafts.
- `ratios.csv`: nine company-year rows with the eleven ratio columns.
- `KO_statements.csv`, `PEP_statements.csv`, `KDP_statements.csv`: annual financials in USD. Missing gross interest remains blank for all PepsiCo years and KDP 2024; the legacy CLI requires complete inputs and rejects these rows.
- Three `*_credit_review.md` files: review drafts with cited company disclosures.
- `credit_case.xlsx`: financials, 45 Excel ratio formulas, 156 provenance rows and a limitations sheet. Every formula requires numeric inputs and a strictly positive denominator, matching Python missing-value handling. Excel/LibreOffice recalculates formulas on opening; Python does not execute the Excel formulas. The JSON/CSV calculated results are already populated.
- `KO_cli/`: outputs from the CLI, with ratio CSV, chart and HTML report for three annual rows. Its benchmark assessments remain illustrative, and legacy CLI columns named debt/assets or debt/equity use total liabilities rather than interest-bearing debt; use the explicitly named public-case ratios for the credit review.

The app downloads a ZIP containing the nine standard output files plus the source manifest. Full raw caches remain in this directory; they are not duplicated in each ZIP.
