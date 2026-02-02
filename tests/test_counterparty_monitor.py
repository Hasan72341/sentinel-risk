import unittest
from datetime import date

from app.services.counterparty_monitor import add_months, review_portfolio, sample_portfolio

AS_OF = "2026-06-30"


def cp(name="Alpha (test)", **overrides):
    row = {
        "name": name, "counterparty_type": "corporate", "country": "IN",
        "rating": "IR4", "previous_rating": "IR4", "review_frequency": "annual",
        "last_review_date": "2026-01-15", "limit": 100.0, "utilisation": 50.0,
    }
    row.update(overrides)
    return row


def only(rows, **kwargs):
    return review_portfolio(rows if isinstance(rows, list) else [rows], kwargs.get("as_of", AS_OF))


class AddMonthsTests(unittest.TestCase):
    def test_add_months(self):
        self.assertEqual(add_months(date(2026, 1, 15), 6), date(2026, 7, 15))
        self.assertEqual(add_months(date(2025, 8, 31), 6), date(2026, 2, 28))
        self.assertEqual(add_months(date(2024, 2, 29), 12), date(2025, 2, 28))
        self.assertEqual(add_months(date(2025, 12, 1), 12), date(2026, 12, 1))


class ReviewPortfolioTests(unittest.TestCase):
    def test_clean_counterparty_has_no_actions(self):
        row = only(cp())["counterparties"][0]
        self.assertEqual(row["next_review_date"], "2027-01-15")
        self.assertEqual(row["days_to_review"], 199)  # 30 Jun 2026 -> 15 Jan 2027
        self.assertEqual(row["review_status"], "current")
        self.assertEqual(row["utilisation_pct"], 50.0)
        self.assertEqual(row["headroom"], 50.0)
        self.assertEqual(row["migration"], "stable")
        self.assertFalse(row["watchlist"])
        self.assertEqual((row["priority_score"], row["priority"], row["actions"]), (0, "None", []))

    def test_overdue_semi_annual_review(self):
        # Last review 1 Dec 2025 + 6 months = 1 Jun 2026, 29 days before 30 Jun.
        out = only(cp(review_frequency="semi_annual", last_review_date="2025-12-01"))
        row = out["counterparties"][0]
        self.assertEqual(row["next_review_date"], "2026-06-01")
        self.assertEqual(row["days_to_review"], -29)
        self.assertEqual(row["review_status"], "overdue")
        self.assertEqual(row["watchlist_flags"], ["Review overdue"])
        self.assertEqual((row["priority_score"], row["priority"]), (60, "Medium"))
        self.assertIn("overdue by 29 days", row["actions"][0])
        self.assertEqual(out["summary"]["reviews_overdue"], 1)
        self.assertEqual(len(out["reviews_due"]), 1)

    def test_due_soon_boundary(self):
        # Annual review due 30 Jul 2026 = exactly 30 days ahead -> due soon; 31 days -> current.
        row = only(cp(last_review_date="2025-07-30"))["counterparties"][0]
        self.assertEqual((row["days_to_review"], row["review_status"]), (30, "due_soon"))
        self.assertEqual((row["priority_score"], row["priority"]), (20, "Low"))
        self.assertFalse(row["watchlist"])
        row = only(cp(last_review_date="2025-07-31"))["counterparties"][0]
        self.assertEqual((row["days_to_review"], row["review_status"]), (31, "current"))
        # Due today is not overdue.
        row = only(cp(last_review_date="2025-06-30"))["counterparties"][0]
        self.assertEqual((row["days_to_review"], row["review_status"]), (0, "due_soon"))

    def test_limit_breach_and_high_utilisation(self):
        row = only(cp(utilisation=112.5))["counterparties"][0]
        self.assertEqual(row["limit_breach"], 12.5)
        self.assertEqual(row["utilisation_pct"], 112.5)
        self.assertEqual(row["watchlist_flags"], ["Limit breach"])
        self.assertEqual((row["priority_score"], row["priority"]), (100, "High"))

        row = only(cp(utilisation=90))["counterparties"][0]
        self.assertEqual(row["watchlist_flags"], ["High utilisation"])
        self.assertEqual(row["priority_score"], 30)
        # Exactly at the limit is high utilisation, not a breach.
        row = only(cp(utilisation=100))["counterparties"][0]
        self.assertEqual((row["limit_breach"], row["watchlist_flags"]), (0, ["High utilisation"]))
        row = only(cp(utilisation=89.9))["counterparties"][0]
        self.assertFalse(row["watchlist"])

    def test_migrations(self):
        out = only([
            cp("Down Two (test)", rating="IR6", previous_rating="IR4"),
            cp("Down One (test)", rating="IR5", previous_rating="IR4"),
            cp("Up One (test)", rating="IR3", previous_rating="IR4"),
            cp("Stable (test)"),
            cp("No History (test)", previous_rating=None),
        ])
        rows = {r["name"]: r for r in out["counterparties"]}
        self.assertEqual(rows["Down Two (test)"]["migration_notches"], 2)
        self.assertEqual(rows["Down Two (test)"]["watchlist_flags"], ["Downgraded 2 notches"])
        self.assertEqual(rows["Down Two (test)"]["priority_score"], 50)
        self.assertEqual(rows["Down One (test)"]["priority_score"], 15)
        self.assertFalse(rows["Down One (test)"]["watchlist"])
        self.assertEqual(rows["Up One (test)"]["migration"], "upgrade")
        self.assertEqual(rows["Up One (test)"]["migration_notches"], -1)
        self.assertEqual(rows["No History (test)"]["migration"], "stable")
        self.assertEqual([r["name"] for r in out["migrations"]],
                         ["Down Two (test)", "Down One (test)", "Up One (test)"])
        self.assertEqual((out["summary"]["upgrades"], out["summary"]["downgrades"]), (1, 2))

    def test_weak_grade_and_combined_priority(self):
        # Breach 100 + overdue 60 + two-notch downgrade 50 + weak grade 40 = 250.
        out = only([
            cp("Stressed (test)", rating="IR8", previous_rating="IR6", utilisation=120,
               review_frequency="semi_annual", last_review_date="2025-10-01"),
            cp("Weak Only (test)", rating="IR7", previous_rating="IR7"),
            cp("Clean (test)"),
        ])
        first = out["counterparties"][0]
        self.assertEqual(first["name"], "Stressed (test)")
        self.assertEqual((first["priority_score"], first["priority"]), (250, "High"))
        self.assertEqual(len(first["actions"]), 4)
        second = out["counterparties"][1]
        self.assertEqual((second["name"], second["priority_score"], second["priority"]),
                         ("Weak Only (test)", 40, "Medium"))
        self.assertEqual([a["name"] for a in out["actions"]], ["Stressed (test)"] * 4 + ["Weak Only (test)"])
        self.assertEqual([r["name"] for r in out["watchlist"]], ["Stressed (test)", "Weak Only (test)"])
        self.assertEqual(out["summary"]["watchlist"], 2)

    def test_summary_totals_and_breakdowns(self):
        out = only([
            cp("A (test)", limit=100, utilisation=40),
            cp("B (test)", country="JP", counterparty_type="fund", limit=300, utilisation=60),
        ])
        summary = out["summary"]
        self.assertEqual((summary["total_limit"], summary["total_utilisation"], summary["utilisation_pct"]),
                         (400.0, 100.0, 25.0))
        by_country = {g["key"]: g for g in summary["by_country"]}
        self.assertEqual(by_country["JP"], {"key": "JP", "label": "Japan", "count": 1, "limit": 300.0, "utilisation": 60.0})
        self.assertEqual({g["key"] for g in summary["by_type"]}, {"corporate", "fund"})
        self.assertEqual(out["as_of"], AS_OF)

    def test_validation(self):
        bad = [
            cp(name=" "), cp(rating="AA"), cp(country="US"), cp(counterparty_type="sovereign"),
            cp(review_frequency="monthly"), cp(limit=0), cp(utilisation=-1),
            cp(last_review_date="not-a-date"), cp(last_review_date="2026-07-01"),
        ]
        for row in bad:
            with self.assertRaises(ValueError, msg=row):
                only(row)
        with self.assertRaises(ValueError):
            only([cp(), cp()])  # duplicate names
        with self.assertRaises(ValueError):
            review_portfolio([], AS_OF)


class SamplePortfolioTests(unittest.TestCase):
    def test_sample_covers_countries_and_types(self):
        sample = sample_portfolio(AS_OF)
        rows = sample["counterparties"]
        self.assertEqual({r["country"] for r in rows}, {"IN", "CN", "JP", "KR"})
        self.assertEqual({r["counterparty_type"] for r in rows}, {"corporate", "financial_institution", "fund"})
        self.assertTrue(all("(sample)" in r["name"] and r["name"].isascii() for r in rows))
        self.assertIn("fictional", sample["note"])

    def test_sample_review_is_stable_relative_to_as_of(self):
        for as_of in ("2026-06-30", "2028-02-29"):
            out = review_portfolio(sample_portfolio(as_of)["counterparties"], as_of)
            summary = out["summary"]
            self.assertEqual(summary["counterparties"], 13)
            self.assertEqual(summary["limit_breaches"], 1)
            self.assertGreaterEqual(summary["reviews_overdue"], 1)
            self.assertGreaterEqual(summary["downgrades"], 1)
            self.assertEqual(out["counterparties"][0]["priority"], "High")


if __name__ == "__main__":
    unittest.main()
