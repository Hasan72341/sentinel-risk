# Public filings credit analysis

Analysis of original SEC annual filings for Coca-Cola, PepsiCo and Keurig Dr Pepper, FY2022–2024. Information cutoff: April 1, 2025. Validation recorded on October 4, 2026.

## Workflow

Open **Public Filings** from the dashboard or Credit Risk sidebar. The page loads the bundled study through the local API; no credentials or database seeding are required.

The pipeline downloads SEC companyfacts, verifies a compressed source cache, selects original annual filings and calculates financial ratios. Outputs include peer medians, monitoring screens, cited review drafts and CSV, JSON, Markdown and Excel exports.

## Results

| Measure | Result |
|---|---:|
| Issuers | 3 |
| Original annual filing periods | 9 |
| Normalized reported financial facts | 149 |
| Explicit derived liabilities values | 3 |
| Unavailable gross interest inputs | 4 |
| Field evidence records | 156 |
| Ratio definitions / populated observations | 11 / 96 |
| Annual monitoring checks / triggered research alerts | 12 / 5 |
| Generated credit review drafts | 3 |
| Excel analytical formulas | 45 |
| Files in the API download archive | 10 |

The four missing gross interest values are all three PepsiCo years plus KDP 2024. PepsiCo's reported XBRL `InterestExpense` values describe its issuer line **net interest expense and other**. They are retained separately as `net_interest_and_other`, including $919 million for FY2024; they do not enter gross interest coverage. This distinction also applies to CSV exports, so the strict existing CLI refuses incomplete PepsiCo inputs.

| FY2024, USD millions unless a ratio | Coca-Cola | PepsiCo | Keurig Dr Pepper |
|---|---:|---:|---:|
| Revenue | 47,061 | 91,854 | 15,351 |
| Operating income | 9,992 | 12,887 | 2,591 |
| Operating cash flow | 6,805 | 12,507 | 2,219 |
| Cash capital expenditure | 2,064 | 5,318 | 563 |
| CFO less capital expenditure | 4,741 | 7,189 | 1,656 |
| Operating margin | 21.23% | 14.03% | 16.88% |
| Current ratio | 1.03x | 0.82x | 0.49x |

These figures trace to [Coca-Cola's 2024 10-K](https://investors.coca-colacompany.com/filings-reports/annual-filings-10-k/content/0000021344-25-000011/ko-20241231.htm), [PepsiCo's 2024 10-K](https://www.sec.gov/Archives/edgar/data/77476/000007747625000007/pep-20241228.htm), and [KDP's 2024 10-K](https://www.sec.gov/Archives/edgar/data/1418135/000141813525000013/kdp-20241231.htm). CFO less capital expenditure is a calculation in this case; PepsiCo's own FCF definition additionally includes asset sale proceeds.

KO triggers the operating-margin and cash-flow decline screens; PEP triggers the current-ratio screen; KDP triggers current-ratio and operating-margin screens. The thresholds are visible and illustrative. No contractual covenant breach or default is inferred. KO's review cites its $6 billion tax litigation deposit; KDP's review cites company-disclosed impairments and GHOST distribution termination accrual. Reported GAAP values remain unadjusted.

## Analytical scope

| Component | Calculation or output | Limitation |
|---|---|---|
| Financial statements | Nine annual rows, accounting reconciliation and eleven ratios | US corporate filings; no bank or fund statements |
| Peer comparison | Three-company medians with valid observation counts | Business mix and fiscal calendars differ; this is a selected peer group |
| Credit reviews | Calculated performance, cited disclosures and follow-up items | Reviews are analytical drafts without calibrated ratings or PDs |
| Monitoring | Four annual screens per issuer, including changes in margin and cash flow | Thresholds are research assumptions; no facility terms are available |
| Exports | CSV, JSON, Markdown and a formula workbook | Excel formulas were structurally checked; spreadsheet recalculation was not tested |

## Reproduction and tests

From the repository root:

```bash
PYTHONPATH=src .venv/bin/python -m sentinel_risk.public_filings
PYTHONPATH=api:src .venv/bin/python -m pytest tests/test_public_filings.py -q
PYTHONPATH=api:src .venv/bin/python -m pytest tests -q
PYTHONPATH=src .venv/bin/python -m sentinel_risk.cli \
  data/public_filings/outputs/KO_statements.csv \
  --output data/public_filings/outputs/KO_cli
```

Executed results: offline rebuild produced the counts above; **20 public-filings tests passed**; the **full Python suite passed 292 tests and 15 subtests**. The existing CLI created an HTML report, chart and three annual ratio rows using actual KO figures. Legacy CLI ratios named debt/assets or debt/equity use total liabilities; the new case labels this explicitly as liabilities/assets.

For the browser test, an isolated local SQLite database was used:

```bash
SENTINEL_DATABASE_URL=sqlite:///data/public_filings/validation.db \
  PYTHONPATH=api:src .venv/bin/python -m uvicorn app.main:app \
  --host 127.0.0.1 --port 8000
```

In `desktop/`:

```bash
npm run build
npx playwright install chromium
npx playwright test e2e/public-filings.spec.ts
```

Executed results: **TypeScript and Vite production build passed**; **one Chromium test passed against the real local API**, covering dashboard navigation, all three issuer selections and ZIP download. No network response was mocked. A [captured screenshot](public-filings.png) shows the populated page and source context. The production build reports an existing large-chunk advisory; Python reports two third-party deprecation warnings. The optional `ruff` invocation could not run because that tool is not installed in this virtual environment. Native Tauri window behavior was not exercised by this browser test.

The tests verify original annual selection rather than quarterly data, no later restatement selection, exact accession/period/unit lineage, balance-sheet reconciliation including noncontrolling equity, peer math, no zero-fill for missing inputs, refusal to treat PepsiCo net interest as gross interest, Excel numeric/positive-denominator guards, source checksums, exact ticker-to-CIK identity, unique complete issuer coverage, cache path containment (including symlinks), reproducibility and API export contents.

## Files to inspect

- [`src/sentinel_risk/public_filings.py`](../../src/sentinel_risk/public_filings.py): acquisition, selection, calculations, reviews and exports.
- [`api/app/routers/public_filings.py`](../../api/app/routers/public_filings.py): case, ZIP and per-issuer CSV routes.
- [`desktop/src/renderer/pages/PublicFilings.tsx`](../../desktop/src/renderer/pages/PublicFilings.tsx): populated interactive case.
- [`data/public_filings/sources.json`](../../data/public_filings/sources.json): exact SEC URLs, retrieval dates and hashes.
- [`data/public_filings/README.md`](../../data/public_filings/README.md): selection policy, data semantics and refresh instructions.
- [`data/public_filings/outputs/case_study.json`](../../data/public_filings/outputs/case_study.json): complete case and field provenance.
- [`data/public_filings/outputs/credit_case.xlsx`](../../data/public_filings/outputs/credit_case.xlsx): financials, formulas and evidence workbook.
- [`tests/test_public_filings.py`](../../tests/test_public_filings.py) and [`desktop/e2e/public-filings.spec.ts`](../../desktop/e2e/public-filings.spec.ts): executable verification.
