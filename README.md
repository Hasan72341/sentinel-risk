# Sentinel Risk

A local application for financial statement analysis, corporate credit review, portfolio
exposure and risk-model diagnostics. The interface uses React and TypeScript, the API uses
FastAPI, and Tauri provides an optional desktop shell.

## Contributors

Sentinel Risk is a shared project built by all five contributors. **Hasan coordinates
integration and delivery.** The table summarises each contributor's primary areas of
work; responsibility for the overall project is shared.

| Contributor | Primary responsibility | Contributions |
|---|---|---|
| [Hasan (@Hasan72341)](https://github.com/Hasan72341) | Integration and delivery | Connected the API, CLI and React application; built the dashboard and shared interface; packaged the Tauri desktop shell; maintained CI, architecture documentation and verification evidence. |
| [Gopesh (@CodeCrusherG)](https://github.com/CodeCrusherG) | Data ingestion, persistence and evidence | Implemented statement ingestion, database models and migrations, evidence intake and field validation, and counterparty monitoring; prepared the SEC filings cache with source checksums. |
| [Prateek (@PrateekIITMandi)](https://github.com/PrateekIITMandi) | Financial analysis and public filings | Implemented financial ratios, credit scorecards and peer benchmarks; developed the public-filings analysis pipeline and its tests; prepared issuer statements and credit-review outputs. |
| [Manav (@manav-bidawat)](https://github.com/manav-bidawat) | Exposure analytics and model diagnostics | Implemented netting, collateral and potential-exposure models; developed VaR/ES diagnostics, backtest exception monitoring and portfolio optimisation; added financial reports and load-test scenarios. |
| [Abhay (@immortal-coder-abhay)](https://github.com/immortal-coder-abhay) | Margin, stress testing and evidence exports | Implemented initial-margin and sensitivity scenarios, stress and reverse-stress analysis; prepared financial-review evidence and Excel exports; added dashboard, settings and API-wiring checks. |

## Public filings study

The **Public Filings** page analyses Coca-Cola, PepsiCo and Keurig Dr Pepper over
FY2022–2024, using original SEC annual filings available by **April 1, 2025**.

| Dataset | Count |
|---|---:|
| Issuers / annual statements | 3 / 9 |
| Reported financial facts | 149 |
| Derived liabilities values | 3 |
| Missing gross interest-expense inputs | 4 |
| Ratio definitions / calculated observations | 11 / 96 |
| Monitoring checks / triggered screens | 12 / 5 |
| Credit review drafts | 3 |

Every reported financial fact carries its filing accession, period, unit and source.
Derived fields record their formulas; unavailable fields record the reason. The study
compares liquidity, margins, leverage and cash flow across the three issuers, with
cited company disclosures in the reports.

PepsiCo's reported net interest expense and other is stored separately from gross
interest expense. Missing gross interest values remain blank and are excluded from
coverage calculations. Monitoring thresholds are research screens;
the study does not assign credit ratings or default probabilities.

Read the [analysis and validation](docs/evidence/public-filings-case.md) and
[dataset methodology](data/public_filings/README.md). The [source manifest](data/public_filings/sources.json)
records retrieval details and SHA-256 checksums.

## Setup

Requirements: Python 3.12 and Node.js with npm. Run from this project folder:

```bash
python3.12 -m venv .venv
.venv/bin/python -m pip install -r api/requirements.txt
.venv/bin/python -m pip install -e '.[dev]'
npm --prefix desktop ci
```

The bundled filings case needs no API credentials or database seed. Start the backend:

```bash
PYTHONPATH=api:src .venv/bin/python -m uvicorn app.main:app \
  --host 127.0.0.1 --port 8000
```

In a second terminal, from this project folder:

```bash
npm --prefix desktop run dev -- --host 127.0.0.1 --port 5173
```

Open [Public Filings](http://127.0.0.1:5173/#/public-filings).
The API documentation is at [localhost:8000/docs](http://127.0.0.1:8000/docs).

### Desktop shell

With Rust and the [Tauri system dependencies](https://tauri.app/start/prerequisites/)
installed, run:

```bash
npm --prefix desktop run tauri:dev
```

Keep the API running on port 8000; the desktop shell connects to that process.

## Rebuild and export

Rebuild the study from the bundled SEC cache:

```bash
PYTHONPATH=src .venv/bin/python -m sentinel_risk.public_filings
```

Outputs are written to `data/public_filings/outputs/`. The **Export evidence pack**
button downloads financial CSVs, ratios, credit-review Markdown files, provenance JSON
and an Excel workbook containing 45 analytical formulas and field-level sources.
Raw source checksums are verified before calculation.

| API route | Result |
|---|---|
| `GET /api/v1/public-filings/case` | Financials, ratios, peer comparisons, monitoring and sources |
| `GET /api/v1/public-filings/{ticker}/statements` | Annual financial statements as CSV |
| `GET /api/v1/public-filings/export` | ZIP of study outputs and source manifest |

To analyse a complete statement CSV through the CLI:

```bash
PYTHONPATH=src .venv/bin/python -m sentinel_risk.cli \
  data/public_filings/outputs/KO_statements.csv --output output/ko
```

## Other analysis tools

| Area | Tools |
|---|---|
| Financial statements | CSV, Excel and PDF extraction; evidence review; profitability, liquidity, leverage and efficiency ratios |
| Credit review | Illustrative scorecards, peer profiles, counterparty monitoring and review drafts |
| Market risk | VaR/ES, Kupiec and Christoffersen tests, rolling exceptions, stress and reverse stress |
| Exposure | Position and collateral monitoring, limit utilisation, potential exposure and initial-margin simulations |
| Quantitative analysis | Time series, factor analysis, portfolio optimisation and pricing examples |

The sample counterparty books, price histories, scorecard parameters, sector profiles
and stress shocks in these tools are illustrative. Their assumptions are displayed
alongside the calculations. Market quotes use a delayed public source and may be
unavailable when the provider rate-limits requests.

Core calculations run in the local API. Optional hosted LLM and cloud integrations
send data to their configured providers.

## Tests

From this project folder:

```bash
PYTHONPATH=api:src .venv/bin/python -m pytest tests -q
npm --prefix desktop run build
```

With the API running on port 8000, run the filings browser test:

```bash
cd desktop
npx playwright install chromium
npx playwright test e2e/public-filings.spec.ts
```

Recorded validation: **292 Python tests and 15 subtests passed**, including 20 filings
tests; TypeScript/Vite build and 17 Chromium tests passed. See
[validation details](docs/evidence/verification.json) for commands and output checksums.
The browser test covers the web interface; native Tauri behaviour was not tested.

## Project layout

```text
api/app/                 FastAPI routes, services, models and migrations
desktop/                 React interface and Tauri shell
src/sentinel_risk/       CLI, calculations and public-filings pipeline
data/public_filings/     SEC cache, source manifest and generated study
tests/                   Python tests
desktop/e2e/             Browser tests
docs/                    Architecture, API and methodology
```

## Attribution and licence

Based on [FinSight Pro by Ali Marandi](https://github.com/Ali-Marandi/finsight-pro).
This source tree includes the Sentinel Risk interface and public-filings study.

- CLI (`src/sentinel_risk/`): [MIT licence](LICENSE).
- Desktop and API: [commercial licence](docs/legal/LICENSE-COMMERCIAL).

Install this checkout from source: the `sentinel-risk` name on PyPI is used by a separate
package. See [Contributing](CONTRIBUTING.md) for development conventions.
