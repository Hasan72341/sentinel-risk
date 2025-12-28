"""Database migration and seed tests, run in a subprocess against a temporary database."""
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

API_DIR = Path(__file__).resolve().parents[1] / "api"

SCRIPT = """
import json, sys
from sqlalchemy import inspect, text
from app.models.database import Base, SessionLocal, engine, init_db
from app.models import models
from app import seed

mode = sys.argv[1]
if mode == "legacy":
    # A database created by create_all() before migrations existed
    Base.metadata.create_all(bind=engine)

init_db()
init_db()  # running twice must be harmless

inspector = inspect(engine)
out = {"tables": sorted(inspector.get_table_names())}
with engine.connect() as conn:
    out["revision"] = conn.execute(text("select version_num from alembic_version")).scalar()
out["missing_columns"] = {
    table.name: sorted(
        {c.name for c in table.columns} - {c["name"] for c in inspector.get_columns(table.name)}
    )
    for table in Base.metadata.sorted_tables
}

db = SessionLocal()
out["first"] = seed.seed(db)
out["second"] = seed.seed(db)
out["analyses"] = db.query(models.AnalysisModel).count()
out["ratios"] = db.query(models.RatioResultModel).count()
out["settings"] = db.query(models.SettingsModel).count()
out["reset"] = seed.seed(db, reset=True)
out["analyses_after_reset"] = db.query(models.AnalysisModel).count()
out["ratios_after_reset"] = db.query(models.RatioResultModel).count()
db.close()
print("RESULT" + json.dumps(out))
"""


def run_against_fresh_database(mode: str) -> dict:
    with tempfile.TemporaryDirectory() as tmp:
        env = {
            **os.environ,
            "SENTINEL_DATABASE_URL": f"sqlite:///{tmp}/test.db",
            "PYTHONPATH": str(API_DIR),
        }
        proc = subprocess.run(
            [sys.executable, "-c", SCRIPT, mode],
            cwd=API_DIR, env=env, capture_output=True, text=True, timeout=120,
        )
        if proc.returncode != 0:
            raise AssertionError(proc.stderr)
        line = next(l for l in proc.stdout.splitlines() if l.startswith("RESULT"))
        return json.loads(line[len("RESULT"):])


class MigrationAndSeedTests(unittest.TestCase):
    EXPECTED_TABLES = {
        "alembic_version", "analyses", "licenses", "ratio_results",
        "reports", "settings", "sync_events",
    }

    def check(self, out: dict) -> None:
        self.assertEqual(set(out["tables"]), self.EXPECTED_TABLES)
        self.assertEqual(out["revision"], "0001")
        # Every model column exists in the migrated schema
        self.assertTrue(all(not missing for missing in out["missing_columns"].values()),
                        out["missing_columns"])
        self.assertEqual(out["first"]["analyses_added"], 4)
        self.assertEqual(out["first"]["preferences_added"], 4)
        # Seeding again adds nothing
        self.assertEqual(out["second"]["analyses_added"], 0)
        self.assertEqual(out["second"]["preferences_added"], 0)
        self.assertEqual(out["analyses"], 4)
        self.assertGreater(out["ratios"], 0)
        self.assertEqual(out["settings"], 4)
        # Reset replaces the seeded rows without duplicating them
        self.assertEqual(out["reset"]["analyses_removed"], 4)
        self.assertEqual(out["analyses_after_reset"], 4)
        self.assertEqual(out["ratios_after_reset"], out["ratios"])

    def test_fresh_database(self):
        self.check(run_against_fresh_database("fresh"))

    def test_database_created_before_migrations(self):
        self.check(run_against_fresh_database("legacy"))


if __name__ == "__main__":
    unittest.main()
