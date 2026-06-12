"""Regression tests for defects found in review. Expected values are hand-checkable."""

import asyncio
import io
import json
import os
import tempfile
import unittest
from unittest import mock

import httpx
import numpy as np
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

import app.models.models  # noqa: F401  (registers the tables on Base)
from app.models.database import Base, get_db
from app.routers import (
    analysis, benchmarking, credit_exposure, credit_rating, factor_analysis, license as license_router,
    margin_models, reports, risk_methodology, settings,
)
from app.services import asia_markets, regional
from app.services.asia_markets import parse_chart
from app.services.benchmarking import compare_against_industry
from app.services.causal_inference import causal_inference_demo
from app.services.credit_exposure import review_book
from app.services.credit_rating import score_counterparty, QUALITATIVE_FACTORS
from app.services.factor_analysis import fama_french, factor_analysis_demo
from app.services.margin_models import simulate_pfe

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def client_for(router, prefix):
    app = FastAPI()
    app.include_router(router, prefix=prefix)
    return TestClient(app)


class PotentialExposureValidationTests(unittest.TestCase):
    def test_invalid_side_is_a_value_error_naming_valid_sides(self):
        with self.assertRaisesRegex(ValueError, "pay_fixed"):
            simulate_pfe("irs", {"side": "long"}, paths=100, seed=1)
        with self.assertRaisesRegex(ValueError, "buy_protection"):
            simulate_pfe("cds", {"side": "long"}, paths=100, seed=1)

    def test_invalid_side_is_422_over_http(self):
        client = client_for(margin_models.router, "/margin-models")
        for product in ("irs", "cds"):
            response = client.post("/margin-models/pfe", json={"product": product, "params": {"side": "long"}, "paths": 100})
            self.assertEqual(response.status_code, 422, product)
            self.assertIn("side must be one of", response.json()["detail"])

    def test_payment_frequency_must_be_a_standard_whole_number(self):
        for bad in (0.5, 2.7, 3, 20000):
            with self.assertRaisesRegex(ValueError, "payments_per_year"):
                simulate_pfe("irs", {"payments_per_year": bad}, paths=100, seed=1)
        client = client_for(margin_models.router, "/margin-models")
        response = client.post("/margin-models/pfe", json={"product": "irs", "params": {"payments_per_year": 0.5}, "paths": 100})
        self.assertEqual(response.status_code, 422)
        for good in (1, 2, 4, 12):
            result = simulate_pfe("irs", {"payments_per_year": good, "maturity_years": 2}, paths=100, seed=1)
            self.assertGreater(result["uncollateralised"]["peak_pfe"], 0)

    def test_tenor_is_capped_at_50_years(self):
        with self.assertRaisesRegex(ValueError, "maturity_years cannot exceed 50"):
            simulate_pfe("bond", {"maturity_years": 3000}, horizon_years=1, paths=100, seed=1)
        with self.assertRaisesRegex(ValueError, "expiry_years cannot exceed 50"):
            simulate_pfe("equity_option", {"expiry_years": 51}, horizon_years=1, paths=100, seed=1)
        simulate_pfe("bond", {"maturity_years": 50}, horizon_years=1, paths=100, seed=1)


class SamplePortfolioBoundsTests(unittest.TestCase):
    def test_days_query_is_bounded_like_the_post_model(self):
        client = client_for(risk_methodology.router, "/risk-methodology")
        self.assertEqual(client.get("/risk-methodology/sample-portfolio?days=300000").status_code, 422)
        self.assertEqual(client.get("/risk-methodology/sample-portfolio?days=59").status_code, 422)
        self.assertEqual(client.get("/risk-methodology/sample-portfolio?days=60").status_code, 200)


def exposure_row(currency):
    # Net exposure 100 - 10 = 90 today, 90 - 10 = 80 yesterday.
    return {"counterparty": "Aster Bank (sample)", "currency": currency, "current_mtm": 100, "previous_mtm": 90,
            "collateral": 10, "previous_collateral": 10, "credit_limit": 200, "required_margin": 5}


class ExposureFxRateTests(unittest.TestCase):
    def test_conversion_by_hand(self):
        # 90 INR x 0.012 USD per INR = 1.08 USD
        book = review_book([exposure_row("INR")], "USD", {"INR": 0.012})
        self.assertAlmostEqual(book["summary"]["net_exposure"], 1.08, places=2)
        # Rates quoted against a third currency: 0.012 / 0.5 = 0.024 -> 2.16
        book = review_book([exposure_row("INR")], "USD", {"INR": 0.012, "USD": 0.5})
        self.assertAlmostEqual(book["summary"]["net_exposure"], 2.16, places=2)

    def test_reporting_currency_rate_must_be_positive(self):
        for bad in (0, -1, float("nan"), float("inf")):
            with self.assertRaisesRegex(ValueError, r"fx_rates\[USD\] must be a positive number"):
                review_book([exposure_row("INR")], "USD", {"INR": 0.012, "USD": bad})

    def test_bad_reporting_rate_is_422_over_http(self):
        client = client_for(credit_exposure.router, "/credit-exposure")
        for bad in (0, -1):
            response = client.post("/credit-exposure/review", json={
                "positions": [exposure_row("INR")], "reporting_currency": "USD",
                "fx_rates": {"INR": 0.012, "USD": bad},
            })
            self.assertEqual(response.status_code, 422, bad)


def weekly_payload(closes, price, interval_seconds=7 * 86400):
    start = 1790567100
    return {"chart": {"result": [{
        "meta": {"currency": "JPY", "symbol": "7203.T", "regularMarketPrice": price,
                 "regularMarketTime": start, "previousClose": 108.0, "chartPreviousClose": 50.0},
        "timestamp": [start + interval_seconds * i for i in range(len(closes))],
        "indicators": {"quote": [{"open": list(closes), "high": list(closes), "low": list(closes),
                                  "close": list(closes), "volume": [1] * len(closes)}]},
    }], "error": None}}


class WeeklyQuoteChangeTests(unittest.TestCase):
    def setUp(self):
        asia_markets.clear_cache()

    def test_weekly_bars_do_not_produce_a_change(self):
        quote = parse_chart(weekly_payload((100.0, 110.0), 110.0), "1wk")
        self.assertIsNone(quote["previous_close"])
        self.assertIsNone(quote["change"])
        self.assertIsNone(quote["change_pct"])
        self.assertEqual(len(quote["history"]), 2)
        # Daily bars still do: (110 - 100) / 100 = 10%.
        self.assertEqual(parse_chart(weekly_payload((100.0, 110.0), 110.0), "1d")["change_pct"], 10.0)

    def run_quote(self, handler, range_):
        factory = lambda: httpx.AsyncClient(transport=httpx.MockTransport(handler))  # noqa: E731
        with mock.patch.object(asia_markets, "_new_client", factory):
            return asyncio.run(asia_markets.get_quote("7203.T", range_))

    def test_weekly_range_takes_change_from_daily_bars(self):
        def handler(request):
            if request.url.params["interval"] == "1wk":
                return httpx.Response(200, json=weekly_payload((100.0, 110.0), 110.0))
            return httpx.Response(200, json=weekly_payload((107.0, 108.0, 110.0), 110.0, 86400))

        result = self.run_quote(handler, "2y")
        self.assertEqual(result["interval"], "1wk")
        self.assertEqual(len(result["history"]), 2)          # weekly history is kept
        self.assertEqual(result["previous_close"], 108.0)    # yesterday, not last week
        self.assertEqual(result["change"], 2.0)
        self.assertAlmostEqual(result["change_pct"], 1.8519, places=4)  # 2 / 108

    def test_weekly_range_without_daily_data_reports_no_change(self):
        def handler(request):
            if request.url.params["interval"] == "1wk":
                return httpx.Response(200, json=weekly_payload((100.0, 110.0), 110.0))
            return httpx.Response(429, text="Too Many Requests")

        result = self.run_quote(handler, "5y")
        self.assertEqual(result["status"], "live")
        self.assertIsNone(result["change_pct"])


class RegionalIndexTests(unittest.TestCase):
    def test_topix_is_not_listed(self):
        rows = regional.all_indices()
        self.assertNotIn("^TOPX", [row["symbol"] for row in rows])
        self.assertEqual([row["symbol"] for row in rows if row["country"] == "JP"], ["^N225"])


class BenchmarkingNegativeLeverageTests(unittest.TestCase):
    def test_negative_leverage_is_rejected_not_ranked_excellent(self):
        for name in ("debt_to_equity", "debt_to_assets"):
            with self.assertRaisesRegex(ValueError, "not meaningful"):
                compare_against_industry([{"ratio_name": name, "value": -3.0}], "automobiles", "IN")
        zero = compare_against_industry([{"ratio_name": "debt_to_equity", "value": 0.0}], "automobiles", "IN")
        self.assertEqual(zero["comparisons"][0]["rank"], "excellent")

    def test_api_returns_422_and_no_bilingual_field(self):
        client = client_for(benchmarking.router, "/benchmarking")
        response = client.post("/benchmarking/compare", json={
            "industry_id": "automobiles", "region": "IN",
            "ratios": [{"ratio_name": "debt_to_equity", "value": -3.0}],
        })
        self.assertEqual(response.status_code, 422)
        body = client.get("/benchmarking/industries").json()
        rows = body["industries"] if isinstance(body, dict) else body
        self.assertTrue(rows)
        self.assertTrue(all("name_en" not in row for row in rows))


FUND = {"net_asset_value": 1000, "gross_exposure": 3500, "liquid_assets_7d": 450,
        "redemption_notice_days": 45.5, "top5_investor_share": 0.5, "net_flows_12m_pct": -0.10,
        "annualised_volatility": 0.17, "max_drawdown": 0.225}
QUAL = {spec["key"]: 3 for spec in QUALITATIVE_FACTORS}


class FundInputRangeTests(unittest.TestCase):
    def test_percentages_typed_instead_of_decimals_are_rejected(self):
        self.assertEqual(score_counterparty("fund", "Mid Fund", "KR", FUND, QUAL)["total_score"], 50.0)
        for key, bad in (("top5_investor_share", 7.5), ("max_drawdown", 4), ("annualised_volatility", 9),
                         ("top5_investor_share", 18), ("net_flows_12m_pct", -25)):
            with self.assertRaisesRegex(ValueError, f"'{key}' must be between .* decimals"):
                score_counterparty("fund", "X", "KR", dict(FUND, **{key: bad}), QUAL)

    def test_liquid_assets_cannot_exceed_the_fund(self):
        with self.assertRaisesRegex(ValueError, "liquid_assets_7d"):
            score_counterparty("fund", "X", "KR", dict(FUND, liquid_assets_7d=1e9), QUAL)
        # Boundary: equal to gross exposure is accepted.
        score_counterparty("fund", "X", "KR", dict(FUND, liquid_assets_7d=3500), QUAL)

    def test_api_returns_422(self):
        client = client_for(credit_rating.router, "/credit-rating")
        response = client.post("/credit-rating/score", json={
            "counterparty_type": "fund", "name": "X", "country": "KR",
            "financials": dict(FUND, top5_investor_share=7.5), "qualitative": QUAL,
        })
        self.assertEqual(response.status_code, 422)


class FactorAnalysisTests(unittest.TestCase):
    def test_size_and_value_factors_by_hand(self):
        # Two assets, three days. Asset 0 is small and high book-to-market.
        returns = [[0.03, 0.01], [0.00, 0.02], [-0.02, 0.01]]
        market = [0.02, 0.01, -0.005]
        result = fama_french(returns, market, ["Small Value", "Big Growth"], [10, 100], [1.5, 0.5])
        smb = np.array([0.02, -0.02, -0.03])     # asset 0 minus asset 1 each day
        stats = {row["factor"]: row for row in result["factor_statistics"]}
        expected_mean = round(float(smb.mean() * 252 * 100), 2)      # -252.0
        self.assertEqual(expected_mean, -252.0)
        self.assertEqual(stats["SMB (Size)"]["mean_annual_pct"], expected_mean)
        self.assertEqual(stats["HML (Value)"]["mean_annual_pct"], expected_mean)
        self.assertGreater(stats["SMB (Size)"]["volatility_annual_pct"], 0)
        self.assertEqual(result["factor_correlation"][1][2], 1.0)    # SMB and HML are identical here

    def test_size_proxy_without_market_caps_varies_over_time(self):
        rng = np.random.default_rng(3)
        returns = rng.normal(0, [0.01, 0.01, 0.03, 0.03], size=(60, 4))
        result = fama_french(returns.tolist(), returns.mean(axis=1).tolist())
        stats = {row["factor"]: row for row in result["factor_statistics"]}
        self.assertGreater(stats["SMB (Size)"]["volatility_annual_pct"], 0)
        json.dumps(result, allow_nan=False)

    def test_constant_factor_gives_finite_correlations(self):
        returns = [[0.01, 0.01], [0.02, 0.02], [-0.01, -0.01]]     # identical assets: SMB = HML = 0
        result = fama_french(returns, [0.01, 0.02, -0.01], None, [10, 100], [1.5, 0.5])
        json.dumps(result, allow_nan=False)
        self.assertEqual(result["factor_correlation"][0], [1.0, 0.0, 0.0])

    def test_demo_is_json_safe_and_served(self):
        demo = factor_analysis_demo()
        json.dumps(demo, allow_nan=False)
        stats = {row["factor"]: row for row in demo["fama_french"]["factor_statistics"]}
        self.assertGreater(stats["SMB (Size)"]["volatility_annual_pct"], 0)
        self.assertGreater(stats["HML (Value)"]["volatility_annual_pct"], 0)
        self.assertLess(abs(stats["MKT (Market)"]["mean_annual_pct"]), 100)   # decimal returns, not percent
        client = client_for(factor_analysis.router, "/factor-analysis")
        self.assertEqual(client.get("/factor-analysis/demo").status_code, 200)


class CausalDemoTests(unittest.TestCase):
    def test_lagged_links_are_recovered(self):
        demo = causal_inference_demo()
        recovered = {row["known_causal_link"]: row["recovered"] for row in demo["granger_causality"]["recovery_analysis"]}
        for link in ("Oil -> PetroBank", "Oil -> OilTech", "FX -> LotusBank"):
            self.assertTrue(recovered[link], link)
        # p-values are stored as [effect][cause]: Oil (3) -> PetroBank (0).
        self.assertLess(demo["granger_causality"]["causality_pvalues"][0][3], 0.05)


class DesktopApiShapeTests(unittest.TestCase):
    """Pins the response shapes the desktop client (lib/api.ts) maps from."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        engine = create_engine(f"sqlite:///{os.path.join(self.tmp.name, 'test.db')}",
                               connect_args={"check_same_thread": False})
        Base.metadata.create_all(engine)
        session_factory = sessionmaker(bind=engine)

        def get_test_db():
            db = session_factory()
            try:
                yield db
            finally:
                db.close()

        app = FastAPI()
        for module, prefix in ((analysis, "/analysis"), (reports, "/reports"), (settings, "/settings"),
                               (license_router, "/license")):
            app.include_router(module.router, prefix=prefix)
        app.dependency_overrides[get_db] = get_test_db
        self.client = TestClient(app)
        self.engine = engine
        self.home = mock.patch.dict(os.environ, {"HOME": self.tmp.name})
        self.home.start()

    def tearDown(self):
        self.home.stop()
        self.engine.dispose()
        self.tmp.cleanup()

    def upload(self):
        with open(os.path.join(ROOT, "examples", "sample_statement.csv"), "rb") as handle:
            response = self.client.post("/analysis/upload", files={"file": ("sample_statement.csv", handle, "text/csv")})
        self.assertEqual(response.status_code, 200)
        return response.json()

    def test_analysis_upload_history_and_detail(self):
        body = self.upload()
        self.assertEqual(set(body), {"analysis_id", "company_name", "period", "file_name", "created_at", "ratios"})
        self.assertEqual(set(body["ratios"][0]) >= {"category", "ratio_name", "value", "unit", "status"}, True)
        history = self.client.get("/analysis/history").json()
        self.assertIsInstance(history, list)
        self.assertEqual(set(history[0]), {"analysis_id", "company_name", "period", "file_name", "created_at", "summary"})
        self.assertEqual(history[0]["analysis_id"], body["analysis_id"])
        detail = self.client.get(f"/analysis/{body['analysis_id']}").json()
        self.assertEqual(len(detail["ratios"]), len(body["ratios"]))
        self.assertEqual(self.client.delete(f"/analysis/{body['analysis_id']}").json(), {"status": "deleted"})

    def test_report_generate_returns_the_file_itself(self):
        analysis_id = self.upload()["analysis_id"]
        pdf = self.client.post("/reports/generate", json={"analysis_id": analysis_id, "format": "pdf"})
        self.assertEqual(pdf.status_code, 200)
        self.assertEqual(pdf.headers["content-type"], "application/pdf")
        self.assertTrue(pdf.content.startswith(b"%PDF"))
        xlsx = self.client.post("/reports/generate", json={"analysis_id": analysis_id, "format": "xlsx"})
        self.assertEqual(xlsx.status_code, 200)
        self.assertIn("spreadsheetml", xlsx.headers["content-type"])
        self.assertTrue(xlsx.content.startswith(b"PK"))      # XLSX is a zip container
        import pandas as pd
        self.assertEqual(list(pd.read_excel(io.BytesIO(xlsx.content)).columns),
                         ["Category", "Ratio", "Value", "Unit", "Benchmark", "Status"])
        self.assertEqual(self.client.post("/reports/generate", json={"analysis_id": analysis_id, "format": "html"}).status_code, 422)
        self.assertEqual(self.client.post("/reports/generate", json={"analysis_id": "missing"}).status_code, 404)

    def test_preferences_round_trip_in_snake_case(self):
        sent = {"default_language": "en", "chart_theme": "dark", "decimal_places": 4, "auto_save": False}
        self.assertEqual(self.client.put("/settings/preferences", json=sent).json(), sent)
        self.assertEqual(self.client.get("/settings/preferences").json(), sent)

    def test_license_shape_and_prefix(self):
        body = self.client.post("/license/validate", json={"key": "SR-PRO-1234567"}).json()
        self.assertEqual(set(body), {"valid", "tier", "expires_at", "features"})
        self.assertTrue(body["valid"])
        self.assertEqual(body["tier"], "pro")
        self.assertEqual(self.client.post("/license/validate", json={"key": "SR-ENT-1234567"}).json()["tier"], "enterprise")
        self.assertFalse(self.client.post("/license/validate", json={"key": "FSP-PRO-1234567"}).json()["valid"])


if __name__ == "__main__":
    unittest.main()
