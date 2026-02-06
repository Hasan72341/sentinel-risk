import unittest

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.routers.credit_exposure import router
from app.services.credit_exposure import review_book, review_exposures, sample_book


def position(name, current_mtm, previous_mtm, collateral, previous_collateral, credit_limit, required_margin, **extra):
    return {
        "counterparty": name, "current_mtm": current_mtm, "previous_mtm": previous_mtm,
        "collateral": collateral, "previous_collateral": previous_collateral,
        "credit_limit": credit_limit, "required_margin": required_margin, **extra,
    }


class CreditExposureTests(unittest.TestCase):
    def test_limit_breach_and_day_change(self):
        rows = review_exposures([
            {
                "counterparty": "Aster Bank", "current_mtm": 130,
                "previous_mtm": 100, "collateral": 20,
                "previous_collateral": 20, "credit_limit": 100,
                "required_margin": 25,
            }
        ])
        row = rows[0]
        self.assertEqual(row["net_exposure"], 110)
        self.assertEqual(row["previous_net_exposure"], 80)
        self.assertEqual(row["day_change"], 30)
        self.assertEqual(row["limit_utilization_pct"], 110)
        self.assertEqual(row["limit_breach"], 10)
        self.assertEqual(row["margin_shortfall"], 5)
        self.assertIn("rose by 30", row["commentary"])

    def test_negative_mtm_and_excess_collateral_floor_at_zero(self):
        row = review_exposures([{
            "counterparty": "Cedar Fund", "current_mtm": -20,
            "previous_mtm": 30, "collateral": 40,
            "previous_collateral": 5, "credit_limit": 50,
            "required_margin": 10,
        }])[0]
        self.assertEqual(row["net_exposure"], 0)
        self.assertEqual(row["previous_net_exposure"], 25)
        self.assertEqual(row["day_change"], -25)
        self.assertEqual(row["margin_shortfall"], 0)

    def test_invalid_limit_rejected(self):
        with self.assertRaisesRegex(ValueError, "credit_limit"):
            review_exposures([{
                "counterparty": "A", "current_mtm": 10,
                "previous_mtm": 5, "collateral": 0,
                "previous_collateral": 0, "credit_limit": 0,
                "required_margin": 0,
            }])

    def test_row_carries_exposure_margin_and_attribution(self):
        # MTM 130 -> exposure 130; collateral 20 -> net 110; requirement 25 -> excess -5.
        row = review_exposures([position("Aster Bank", 130, 100, 20, 20, 100, 25, currency="inr", country="India")])[0]
        self.assertEqual(row["exposure"], 130)
        self.assertEqual(row["collateral"], 20)
        self.assertEqual(row["margin_requirement"], 25)
        self.assertEqual(row["margin_excess"], -5)
        self.assertEqual(row["mtm_change"], 30)
        self.assertEqual(row["collateral_change"], 0)
        self.assertEqual(row["currency"], "INR")
        self.assertTrue(row["limit_breach_flag"])
        self.assertTrue(row["margin_call_flag"])
        self.assertEqual(row["limit_breach_status"], "opened")
        # Yesterday collateral 20 was already below the unchanged requirement of 25.
        self.assertEqual(row["margin_status"], "deficit_outstanding")
        self.assertIn("MTM up 30.00, collateral unchanged at 20.00 INR", row["commentary"])
        self.assertIn("Credit limit breach opened: 10.00 INR over the 100.00 INR limit (110.0% utilised)", row["commentary"])
        self.assertIn("Margin deficit outstanding", row["commentary"])

    def test_margin_call_triggered_when_requirement_rises(self):
        row = review_exposures([position("Birch Fund", 50, 50, 20, 20, 100, 25, previous_required_margin=15)])[0]
        self.assertEqual(row["margin_status"], "call_triggered")
        self.assertEqual(row["margin_shortfall"], 5)
        self.assertIn("Margin call triggered for 5.00", row["commentary"])
        self.assertIn("Net exposure was unchanged at 30.00", row["commentary"])

    def test_breach_closed_and_deficit_cured_by_collateral(self):
        # Yesterday: net 130 - 20 = 110 (> 100 limit), collateral 20 < requirement 25.
        # Today:     net 130 - 60 = 70, collateral 60 -> excess 35.
        row = review_exposures([position("Cedar Fund", 130, 130, 60, 20, 100, 25)])[0]
        self.assertEqual(row["day_change"], -40)
        self.assertEqual(row["limit_breach_status"], "closed")
        self.assertEqual(row["margin_status"], "cured")
        self.assertEqual(row["margin_excess"], 35)
        self.assertFalse(row["limit_breach_flag"])
        self.assertIn("MTM unchanged at 130.00, collateral up 40.00", row["commentary"])
        self.assertIn("Credit limit breach closed; utilisation back to 70.0%", row["commentary"])
        self.assertIn("Margin deficit cured; excess now 35.00", row["commentary"])

    def test_book_summary_converts_to_reporting_currency(self):
        book = review_book([
            position("Aster Bank", 130, 100, 20, 20, 100, 25, currency="INR", country="India"),   # net 110, prev 80
            position("Dogwood Pension", 55, 40, 10, 10, 50, 10, currency="USD", country="Japan"),  # net 45, prev 30
        ], reporting_currency="USD", fx_rates={"INR": 0.5, "USD": 1.0})
        summary = book["summary"]
        self.assertEqual(summary["reporting_currency"], "USD")
        self.assertEqual(summary["net_exposure"], 100.0)            # 110 * 0.5 + 45
        self.assertEqual(summary["previous_net_exposure"], 70.0)    # 80 * 0.5 + 30
        self.assertEqual(summary["day_change"], 30.0)
        self.assertEqual(summary["gross_exposure"], 120.0)          # 130 * 0.5 + 55
        self.assertEqual(summary["collateral"], 20.0)               # 20 * 0.5 + 10
        self.assertEqual(summary["margin_deficit"], 2.5)            # 5 * 0.5
        self.assertEqual(summary["limit_breach_count"], 1)
        self.assertEqual(summary["limit_breaches_opened"], 1)
        self.assertEqual(summary["margin_call_count"], 1)
        self.assertEqual([c["country"] for c in summary["by_country"]], ["India", "Japan"])
        self.assertIn("rose by 30.00 (42.9%) to 100.00 USD across 2 clients", summary["commentary"])
        inr_row = next(row for row in book["results"] if row["counterparty"] == "Aster Bank")
        self.assertEqual(inr_row["net_exposure_reporting"], 55.0)

    def test_breach_list_ordered_by_severity(self):
        book = review_book([
            position("Watch Co", 45, 45, 0, 0, 50, 0),            # 90% utilised -> watch
            position("Medium Co", 10, 10, 20, 20, 100, 25),       # deficit 5 / 25 = 20% -> medium
            position("Critical Co", 110, 110, 0, 0, 100, 0),      # 10% over limit -> critical, ongoing
            position("High Limit Co", 105, 90, 0, 0, 100, 0),     # 5% over limit -> high, new
            position("High Margin Co", 10, 10, 10, 10, 100, 20),  # deficit 10 / 20 = 50% -> high
        ])
        order = [(item["counterparty"], item["type"], item["severity"]) for item in book["breaches"]]
        self.assertEqual(order, [
            ("Critical Co", "limit_breach", "critical"),
            ("High Margin Co", "margin_deficit", "high"),   # amount 10 ranks above 5
            ("High Limit Co", "limit_breach", "high"),
            ("Medium Co", "margin_deficit", "medium"),
            ("Watch Co", "limit_watch", "watch"),
        ])
        statuses = {item["counterparty"]: item["status"] for item in book["breaches"]}
        self.assertEqual(statuses["Critical Co"], "ongoing")
        self.assertEqual(statuses["High Limit Co"], "new")
        self.assertIsNone(book["summary"]["reporting_currency"])

    def test_mixed_currencies_need_rates(self):
        rows = [position("A", 10, 10, 0, 0, 50, 0, currency="JPY"), position("B", 10, 10, 0, 0, 50, 0, currency="KRW")]
        with self.assertRaisesRegex(ValueError, "reporting_currency"):
            review_book(rows)
        with self.assertRaisesRegex(ValueError, "KRW"):
            review_book(rows, reporting_currency="JPY", fx_rates={})
        # Rates quoted against a third currency: 1 KRW = 0.001 USD, 1 JPY = 0.01 USD -> 1 KRW = 0.1 JPY.
        book = review_book(rows, reporting_currency="JPY", fx_rates={"KRW": 0.001, "JPY": 0.01})
        self.assertAlmostEqual(book["summary"]["net_exposure"], 11.0)

    def test_sample_book_is_fictional_multi_currency_and_reviews_cleanly(self):
        sample = sample_book()
        self.assertIn("fictional", sample["disclaimer"])
        self.assertEqual({p["country"] for p in sample["positions"]}, {"India", "China", "Japan", "South Korea"})
        self.assertTrue({"INR", "CNY", "JPY", "KRW"} <= {p["currency"] for p in sample["positions"]})
        book = review_book(sample["positions"], sample["reporting_currency"], sample["fx_rates"])
        self.assertEqual(len(book["results"]), len(sample["positions"]))
        self.assertGreater(len(book["breaches"]), 0)
        self.assertTrue(all(ord(ch) < 128 for row in book["results"] for ch in row["commentary"]))


class CreditExposureApiTests(unittest.TestCase):
    def setUp(self):
        app = FastAPI()
        app.include_router(router, prefix="/credit-exposure")
        self.client = TestClient(app)

    def test_legacy_request_shape_still_works(self):
        response = self.client.post("/credit-exposure/review", json={"positions": [
            position("Aster Bank", 130, 100, 20, 20, 100, 25),
        ]})
        self.assertEqual(response.status_code, 200)
        body = response.json()
        row = body["results"][0]
        for key in ("counterparty", "net_exposure", "previous_net_exposure", "day_change",
                    "limit_utilization_pct", "limit_breach", "margin_shortfall", "commentary"):
            self.assertIn(key, row)
        self.assertEqual(row["net_exposure"], 110)
        self.assertEqual(body["summary"]["net_exposure"], 110)
        self.assertEqual(len(body["breaches"]), 2)

    def test_sample_book_round_trip_and_validation(self):
        sample = self.client.get("/credit-exposure/sample-book").json()
        response = self.client.post("/credit-exposure/review", json={
            "positions": sample["positions"], "reporting_currency": "USD", "fx_rates": sample["fx_rates"],
        })
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["summary"]["clients"], len(sample["positions"]))
        missing = self.client.post("/credit-exposure/review", json={
            "positions": sample["positions"], "reporting_currency": "USD", "fx_rates": {},
        })
        self.assertEqual(missing.status_code, 422)


if __name__ == "__main__":
    unittest.main()
