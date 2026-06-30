# Changelog

All notable changes to Sentinel Risk will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added
- **Credit Risk desk**: Credit Rating page (scorecards for corporates, financial institutions and funds on an internal IR1 to IR10 scale, peer comparison, proposed limit, drafted written review, onboarding due-diligence checklist) and Counterparty Monitor page; API groups `/credit-rating` and `/counterparty-monitor`
- **Risk Methodology desk**: VaR Backtesting (Kupiec, Christoffersen, traffic-light zone, expected shortfall, FRTB-style liquidity-horizon ES), Stress Testing (scenario library, reverse stress, economic capital) and Model Monitoring pages; API group `/risk-methodology`
- **Exposure Management desk**: Potential Exposure and Initial Margin pages (historical and parametric margin, calibration comparison, backtest, market-data helper) for equity, bonds, interest rate swaps, CDS, equity options and FX; API group `/margin-models`
- **Asia Markets** page with index and FX boards and exchange hours for India, China, Japan and South Korea; API groups `/asia-markets` and `/regional`
- Unit tests with hand-checkable expected values for every new calculation; CI now runs the whole `tests/` directory
- Database migrations with Alembic (`api/migrations/`, applied on API startup) and a seed command (`python -m app.seed`) that adds four fictional sample analyses for India, China, Japan and South Korea

### Changed
- Product reshaped as a risk workbench for three desks and four markets (INR, CNY, JPY, KRW, with USD as reporting currency)
- Sidebar regrouped into Overview, Credit Risk, Risk Methodology, Exposure Management, Markets, Quant Lab and Workspace; dashboard rebuilt as a workbench landing page with one card per desk
- Exposure Monitoring (formerly Credit Exposure) now reports collateral, margin excess or deficit, limit utilisation, breach status against the previous day, multi-currency conversion and written day-on-day commentary
- Compliance checks rewritten around IFRS, Ind AS, Chinese Accounting Standards (CAS), Japanese GAAP and K-IFRS; sector benchmarking rewritten with regional profiles
- Document extraction, sentiment and the copilot are English only; OCR uses the English language pack; reporting units such as crore, lakh and millions of yen are detected
- All demo issuers, counterparties and portfolios are fictional and labelled as illustrative sample data; simplified models say so in the UI and docstrings
- **Desktop shell migrated from Electron to Tauri 2** — run with `npm run tauri:dev` on Windows, macOS, or Linux
- The desktop shell no longer starts the FastAPI backend; run the API separately on port 8000
- Report export now writes the file to the location chosen in the save dialog: `/reports/generate` accepts `format` (`pdf` or `xlsx`) and returns the file itself; the HTML export option, which was never implemented, is gone
- The API reports version 0.6.0, the same as the desktop and CLI packages, until this work is released
- Demo license keys use the `SR-PRO-` and `SR-ENT-` prefixes

### Fixed
- Statement Analysis, History, license activation and preferences now read and write the backend's actual response shapes, so uploads show their results, saved analyses load and settings persist
- Stochastic, Network, Advanced Optimisation and Causal pages render the demo responses through typed adapters instead of showing empty charts; the Factor Analysis demo no longer fails
- The causal demo's known links are lagged by one day so the Granger test can detect them
- Potential exposure inputs are validated (valid side per product, payment frequency of 1, 2, 4 or 12, tenor up to 50 years); exposure conversion rates must be positive, including the reporting currency's
- Fund scorecard decimals are range-checked, negative leverage ratios are rejected by sector benchmarking, and the day-on-day change on weekly-bar quotes is taken from daily bars
- TOPIX removed from the index board because the data source does not serve it
- Bundled sample analyses are named and badged as sample data and shown only when no saved analysis exists

### Removed
- All non-English language support (lexicons, OCR language pack, bilingual labels, language options)
- The former single-exchange market-data page, its API group and country-specific compliance rules, replaced by Asia Markets and the framework checks above
- Electron main/preload process, `electron-builder` packaging, and the Windows release workflow

## [0.6.0] - 2026-08-25

### Added
- **Time Series Analysis Engine** — ARIMA(5,1,0) forecasting, GARCH(1,1) volatility modeling, time series decomposition, full pipeline
- **Financial Engineering Engine** — VaR/CVaR (3 methods), Monte Carlo simulation, Black-Scholes with Greeks, Markowitz portfolio optimization
- 10 new API endpoints, 2 new frontend pages, 100+ TypeScript interfaces, 8 API client functions
- `statsmodels`, `arch`, `scipy`, `numpy` backend dependencies

### Fixed
- **CI Pipeline** — Fixed YAML branches syntax, restored 6 minified Python files, split CLI tests
- All 5 CI jobs pass: CLI Tests, API Tests, Type Check, Desktop Build, Ruff Lint

### Strategic Research
- 33 financial science techniques analyzed across 5 categories with ROI scoring
- 4-phase roadmap: Phase 1 (GARCH, VaR, Markowitz, ARIMA — implemented), Phase 2 (Monte Carlo, BS, PCA, LSTM, Fuzzy), Phase 3 (RL, NLP, Causal ML), Phase 4 (Quantum, TDA, Federated)

## [0.4.0] - 2026-08-22

### Added
- **Document Intelligence Engine** — OCR extraction from PDF, scanned docs & images
- **Industry Benchmarking Engine** — Compare against 8 industry profiles with percentile rankings
- **Compliance Engine** — 12+ automated checks against IAS and IFRS (since rewritten, see Unreleased)
- **Consolidation Engine** — Multi-company financial statement consolidation with eliminations
- Live market data page for a single exchange (since replaced by Asia Markets, see Unreleased)
- **AI Financial Copilot** — Chat with financial data (built-in + LLM connect)
- **Bankruptcy Prediction** — 5 statistical models (Altman, Springate, Ohlson, Grover) with consensus
- 5 new frontend pages (DocumentIntelligence, Benchmarking, Compliance, Consolidation, market data)
- 5 new API routers and service modules
- Dashboard expanded to 10 feature cards
- Navigation expanded to 12 items
- GitHub Pages landing page
- GitHub Topics (20 SEO-optimized topics)
- Professional README with comparison table and CI badges

### Changed
- Version bumped to 0.4.0
- API version updated to 0.4.0
- Electron main process updated for PDF + image file formats

## [0.1.0] - Desktop preview

### Added
- Desktop application scaffold (Electron + React + TypeScript)
- FastAPI backend with financial analysis endpoints
- Validation landing page with waitlist
- GitHub CI/CD workflows

---

Earlier releases of the standalone CLI, which used its own 1.x version numbers before the desktop app restarted the numbering at 0.x:

## [1.2.0] - 2024-12-15

### Added
- Debt-to-Equity ratio calculation
- Interest Coverage Ratio
- Export to XLSX format support

### Fixed
- CSV parsing for multi-line headers
- Chart rendering with missing data points

## [1.1.0] - 2024-10-01

### Added
- Quick Ratio and Cash Ratio
- Vertical analysis (common-size statements)
- Color-coded HTML reports

### Changed
- Improved error messages for invalid file formats

## [1.0.0] - 2024-07-20

### Added
- Initial CLI release
- 15 financial ratios (profitability, liquidity, leverage, efficiency)
- CSV and XLSX file input support
- Matplotlib chart generation
- Jinja2 HTML report output
- Basic test suite
