"""Seed the database with default preferences and sample analyses.

Run from the api/ directory:

    python -m app.seed            # add anything that is missing
    python -m app.seed --reset    # remove seeded rows first, then add them again

The sample companies are fictional. Their ratios are computed by the real
analyzer from the statements below, so seeded rows match what an upload of the
same figures would produce.
"""
import argparse
import hashlib
import json
from datetime import datetime

from sqlalchemy.orm import Session

from app.models.database import SessionLocal, init_db
from app.models.models import AnalysisModel, RatioResultModel, SettingsModel
from app.services.analyzer import analyze_financial_statement

SEED_NOTE = "Sample data (fictional company) added by the seed command."

DEFAULT_PREFERENCES = {
    "default_language": "en",
    "chart_theme": "light",
    "decimal_places": 2,
    "auto_save": True,
}

STATEMENT_COLUMNS = (
    "revenue", "cost_of_goods_sold", "gross_profit", "operating_income", "net_income",
    "interest_expense", "income_tax", "total_assets", "current_assets", "inventory",
    "cash", "accounts_receivable", "total_liabilities", "current_liabilities",
    "total_equity",
)

# Figures are in millions of the local currency.
SAMPLE_STATEMENTS = [
    {
        "id": "seed-sahyadri-fy2025",
        "company_name": "Sahyadri Auto Components Ltd (India)",
        "period": "FY 2025 (INR m)",
        "file_name": "sahyadri_auto_components_fy2025.csv",
        "created_at": datetime(2026, 9, 28, 10, 30),
        "figures": (48200, 33740, 14460, 5780, 3610, 720, 1210, 61500, 24800, 7900,
                    3400, 9100, 33900, 15200, 27600),
    },
    {
        "id": "seed-jiangnan-fy2025",
        "company_name": "Jiangnan Precision Machinery Co (China)",
        "period": "FY 2025 (CNY m)",
        "file_name": "jiangnan_precision_machinery_fy2025.csv",
        "created_at": datetime(2026, 9, 21, 14, 15),
        "figures": (12850, 10020, 2830, 940, 520, 310, 170, 21400, 9300, 3900,
                    1250, 3600, 14700, 8100, 6700),
    },
    {
        "id": "seed-hokuto-fy2025",
        "company_name": "Hokuto Trading KK (Japan)",
        "period": "FY 2025 (JPY m)",
        "file_name": "hokuto_trading_fy2025.csv",
        "created_at": datetime(2026, 9, 14, 9, 45),
        "figures": (386000, 331900, 54100, 14600, 9800, 1900, 4100, 298000, 171000, 42000,
                    38500, 76000, 176000, 109000, 122000),
    },
    {
        "id": "seed-hanbit-fy2025",
        "company_name": "Hanbit Display Materials Co (South Korea)",
        "period": "FY 2025 (KRW m)",
        "file_name": "hanbit_display_materials_fy2025.csv",
        "created_at": datetime(2026, 9, 7, 16, 5),
        "figures": (2140000, 1819000, 321000, 42000, -18500, 61000, 3500, 3980000, 1210000, 468000,
                    152000, 395000, 2890000, 1385000, 1090000),
    },
]


def _statement_csv(figures: tuple) -> bytes:
    header = ",".join(STATEMENT_COLUMNS)
    row = ",".join(str(value) for value in figures)
    return f"{header}\n{row}\n".encode()


def seed_preferences(db: Session) -> int:
    added = 0
    for key, value in DEFAULT_PREFERENCES.items():
        if db.query(SettingsModel).filter(SettingsModel.key == key).first() is None:
            db.add(SettingsModel(key=key, value=json.dumps(value)))
            added += 1
    return added


def seed_analyses(db: Session) -> int:
    added = 0
    for sample in SAMPLE_STATEMENTS:
        if db.query(AnalysisModel).filter(AnalysisModel.id == sample["id"]).first() is not None:
            continue
        content = _statement_csv(sample["figures"])
        result = analyze_financial_statement(
            file_content=content,
            filename=sample["file_name"],
            extension="csv",
        )
        db.add(AnalysisModel(
            id=sample["id"],
            company_name=sample["company_name"],
            period=sample["period"],
            file_name=sample["file_name"],
            file_hash=hashlib.sha256(content).hexdigest(),
            notes=SEED_NOTE,
            created_at=sample["created_at"],
            updated_at=sample["created_at"],
        ))
        for ratio in result.get("ratios", []):
            db.add(RatioResultModel(
                analysis_id=sample["id"],
                category=ratio["category"],
                ratio_name=ratio["ratio_name"],
                value=ratio["value"],
                unit=ratio["unit"],
                benchmark=ratio.get("benchmark"),
                status=ratio["status"],
            ))
        added += 1
    return added


def remove_seeded_analyses(db: Session) -> int:
    seed_ids = [sample["id"] for sample in SAMPLE_STATEMENTS]
    db.query(RatioResultModel).filter(RatioResultModel.analysis_id.in_(seed_ids)).delete(
        synchronize_session=False
    )
    return db.query(AnalysisModel).filter(AnalysisModel.id.in_(seed_ids)).delete(
        synchronize_session=False
    )


def seed(db: Session, reset: bool = False) -> dict:
    removed = remove_seeded_analyses(db) if reset else 0
    counts = {
        "analyses_removed": removed,
        "preferences_added": seed_preferences(db),
        "analyses_added": seed_analyses(db),
    }
    db.commit()
    return counts


def main() -> None:
    parser = argparse.ArgumentParser(description="Seed the Sentinel Risk database")
    parser.add_argument(
        "--reset", action="store_true",
        help="remove previously seeded analyses before adding them again",
    )
    args = parser.parse_args()

    init_db()
    db = SessionLocal()
    try:
        counts = seed(db, reset=args.reset)
    finally:
        db.close()
    print(
        f"Seed complete: {counts['analyses_added']} analyses added, "
        f"{counts['preferences_added']} preferences added, "
        f"{counts['analyses_removed']} seeded analyses removed."
    )


if __name__ == "__main__":
    main()
