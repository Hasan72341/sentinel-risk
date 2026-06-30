# Contributing to Sentinel Risk

Thank you for your interest in contributing to Sentinel Risk! This document provides guidelines for contributing to both the open-source CLI and the commercial desktop application.

## Project Structure

```
sentinel-risk/
├── src/sentinel_risk/          # CLI tool (MIT License)
│   ├── cli.py             # Command-line interface
│   ├── ratios.py          # Financial ratio calculations
│   ├── charts.py          # Chart generation (matplotlib)
│   ├── io.py              # CSV/XLSX parsing
│   └── report.py          # HTML report generation
├── tests/                 # CLI tests
├── desktop/               # Tauri + React desktop app (Proprietary)
│   ├── src-tauri/         # Tauri shell (Rust)
│   ├── src/main/          # React entry point
│   └── src/renderer/      # React UI components
├── api/                   # FastAPI backend (Proprietary)
│   └── app/               # API routes, services, models
├── docs/                  # Documentation
└── .github/               # CI/CD and templates
```

## Licensing

| Component | License | Contribution Rules |
|-----------|---------|-------------------|
| `src/sentinel_risk/`, `tests/` | MIT | Open contributions welcome |
| `desktop/`, `api/` | Proprietary | Contributors must sign CLA |

## How to Contribute

### Reporting Bugs

Use the [Bug Report template](.github/ISSUE_TEMPLATE/bug_report.yml). Include:
- Steps to reproduce
- Expected vs. actual behavior
- App version and OS
- Log output or screenshots

### Suggesting Features

Use the [Feature Request template](.github/ISSUE_TEMPLATE/feature_request.yml). Clearly describe the problem and your proposed solution.

### Pull Request Workflow

1. **Fork** the repository
2. **Branch** from `develop`: `git checkout -b feature/your-feature develop`
3. **Commit** using [Conventional Commits](https://www.conventionalcommits.org/):
   - `feat: add current ratio calculation`
   - `fix: handle empty CSV rows gracefully`
   - `docs: update README installation guide`
4. **Push** to your fork
5. **Open PR** against the `develop` branch

### Development Setup

#### CLI (Python)

```bash
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate
pip install -e ".[dev]"
pip install -r api/requirements.txt   # the API tests import the backend
PYTHONPATH=api:src python -m pytest tests -q
```

#### Desktop App (Node.js + Python)

```bash
# Frontend
cd desktop
npm install
npm run tauri:dev   # desktop window; use `npm run dev` for the renderer alone in a browser

# Backend API
cd api
pip install -r requirements.txt
uvicorn app.main:app --reload
```

## Code Standards

### Python (CLI & API)
- Format with `ruff format .`
- Lint with `ruff check .`
- Type hints required for API code
- Docstrings for all public functions

### TypeScript (Desktop)
- Format with `prettier --write .`
- Lint with `eslint .`
- Strict mode enabled in `tsconfig.json`
- Use Tailwind CSS utility classes

## Code of Conduct

- Be respectful and inclusive
- Focus on constructive feedback
- No harassment or discriminatory language
- Maintainers reserve the right to remove contributions that violate these standards

## Questions?

Open a [Discussion](https://github.com/Ali-Marandi/finsight-pro/discussions) or reach out to the maintainers.
