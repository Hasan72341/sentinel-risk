# Architecture Overview

## Product scope

Sentinel Risk is an English-only risk-management workbench for analysts covering India, China, Japan and South Korea (INR, CNY, JPY, KRW, with USD reporting). The UI is organised into three desks:

| Desk | What it covers |
|------|----------------|
| Credit Risk | Financial statement analysis, internal rating scorecards, peer and sector comparison, onboarding due diligence, credit limits and breach investigation, counterparty monitoring, written credit reviews |
| Risk Methodology | VaR and margin-model backtesting, market and counterparty stress testing, economic capital and expected shortfall, prototype models, model performance monitoring |
| Exposure Management | Daily client portfolio monitoring (exposure, risk profile, margin), day-on-day commentary, potential exposure models, initial margin calculation and calibration |

Models are simplified, for analysis and learning; they are not regulatory calculations. Bundled demo counterparties are fictional sample data.

> The desktop shell is now Tauri 2 (`desktop/src-tauri/`). References to Electron below describe the earlier scaffold and are kept for history.

Sentinel Risk uses a hybrid architecture combining Electron for the desktop shell, React for the UI layer, and a FastAPI Python backend that wraps the existing CLI analysis engine.

## System Architecture

```
┌─────────────────────────────────────────────────────┐
│                   Electron Shell                     │
│  ┌───────────────────────────────────────────────┐  │
│  │           React + TypeScript UI                │  │
│  │  ┌──────────┐ ┌──────────┐ ┌──────────────┐  │  │
│  │  │ Dashboard │ │ Analysis │ │   Reports    │  │  │
│  │  │   Page    │ │   Page   │ │    Page      │  │  │
│  │  └────┬─────┘ └────┬─────┘ └──────┬───────┘  │  │
│  │       └────────────┼──────────────┘           │  │
│  │                    │                          │  │
│  │            API Client Layer                    │  │
│  │         (Axios / Fetch)                        │  │
│  └────────────────────┼──────────────────────────┘  │
│                       │ IPC / HTTP                   │
│  ┌────────────────────┼──────────────────────────┐  │
│  │         FastAPI Backend (Python)               │  │
│  │  ┌──────────┐ ┌──────────┐ ┌──────────────┐  │  │
│  │  │  Routers  │ │ Services │ │    Models    │  │  │
│  │  └────┬─────┘ └────┬─────┘ └──────┬───────┘  │  │
│  │       └────────────┼──────────────┘           │  │
│  │                    │                          │  │
│  │         Core Analysis Engine                   │  │
│  │      (wraps src/sentinel_risk/*)                    │  │
│  └────────────────────┼──────────────────────────┘  │
│                       │                             │
│  ┌────────────────────┼──────────────────────────┐  │
│  │              SQLite Database                   │  │
│  │        (SQLAlchemy ORM)                        │  │
│  └───────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────┘
```

## Key Design Decisions

1. **Electron + React**: Cross-platform desktop with web-standard UI tooling
2. **FastAPI Backend**: Reuses existing Python analysis code without rewriting
3. **SQLite**: Zero-config embedded database, perfect for single-user desktop
4. **IPC Bridge**: Electron's IPC for local communication, HTTP fallback for dev

## Data Flow

1. User imports a CSV/XLSX financial statement via the UI
2. React sends file to FastAPI via IPC
3. FastAPI parses the file, runs all 15+ financial ratios
4. Results stored in SQLite for history/caching
5. Results returned to React, rendered as interactive charts and tables
6. User can export reports as PDF, XLSX, or HTML

## Module Responsibilities

| Module | Responsibility |
|--------|---------------|
| `desktop/electron/` | App lifecycle, window management, IPC, auto-updater |
| `desktop/src/renderer/` | All UI: pages, components, hooks, state management |
| `api/app/routers/` | HTTP endpoints for analysis, files, settings |
| `api/app/services/` | Business logic wrapping `src/sentinel_risk/` engine |
| `api/app/models/` | SQLAlchemy ORM models and Pydantic schemas |
| `src/sentinel_risk/` | Core calculation engine (shared with CLI) |
