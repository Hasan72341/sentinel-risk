"""Regional reference data, market hours and region-aware benchmarking."""

import unittest
from datetime import datetime, timezone

from app.services import regional
from app.services.benchmarking import (
    compare_against_industry, auto_detect_industry, get_available_industries,
    get_profile, normalize_ratio_name,
)


def utc(day, hour, minute=0):
    # October 2026: the 3rd is a Saturday, the 5th a Monday.
    return datetime(2026, 10, day, hour, minute, tzinfo=timezone.utc)


class ReferenceDataTests(unittest.TestCase):
    def test_four_countries_with_currencies_and_symbols(self):
        countries = regional.list_countries()
        self.assertEqual([c["code"] for c in countries], ["IN", "CN", "JP", "KR"])
        self.assertEqual([c["currency"]["code"] for c in countries], ["INR", "CNY", "JPY", "KRW"])
        self.assertEqual(regional.get_country("in")["locale"], "en-IN")
        self.assertEqual(regional.get_country("JP")["accounting"]["framework_id"], "JGAAP")
        with self.assertRaises(ValueError):
            regional.get_country("IR")

    def test_india_grouping_units(self):
        units = {u["name"]: u["value"] for u in regional.get_country("IN")["number_grouping"]["units"]}
        self.assertEqual(units, {"lakh": 100_000, "crore": 10_000_000})

    def test_index_and_fx_symbols(self):
        symbols = {row["name"]: row["symbol"] for row in regional.all_indices()}
        self.assertEqual(symbols, {
            "Nifty 50": "^NSEI", "Sensex": "^BSESN", "SSE Composite": "000001.SS",
            "CSI 300": "000300.SS", "Hang Seng": "^HSI", "Nikkei 225": "^N225",
            "KOSPI": "^KS11", "KOSDAQ": "^KQ11",
        })
        self.assertEqual([p["symbol"] for p in regional.fx_pairs()], ["INR=X", "CNY=X", "JPY=X", "KRW=X"])

    def test_reference_text_is_ascii_apart_from_currency_symbols(self):
        def walk(value, path=""):
            if isinstance(value, dict):
                for key, item in value.items():
                    yield from walk(item, f"{path}.{key}")
            elif isinstance(value, list):
                for item in value:
                    yield from walk(item, path)
            elif isinstance(value, str):
                yield path, value

        for path, text in walk(regional.COUNTRIES):
            if path.endswith(".currency.symbol"):
                continue
            self.assertTrue(text.isascii(), f"{path}: {text!r}")


class MarketStatusTests(unittest.TestCase):
    def test_monday_0400_utc(self):
        now = utc(5, 4)
        # 09:30 in Mumbai: open (09:15 to 15:30).
        india = regional.market_status("IN", now)
        self.assertEqual((india["status"], india["local_time"]), ("open", "2026-10-05 09:30"))
        # 12:00 in Shanghai: midday break (11:30 to 13:00).
        self.assertEqual(regional.market_status("CN", now)["status"], "break")
        # 13:00 in Tokyo and Seoul: open.
        self.assertTrue(regional.market_status("JP", now)["is_open"])
        self.assertTrue(regional.market_status("KR", now)["is_open"])

    def test_session_boundaries(self):
        # 15:29 Tokyo is open, 15:30 is closed (the end time is exclusive).
        self.assertEqual(regional.market_status("JP", utc(5, 6, 29))["status"], "open")
        closed = regional.market_status("JP", utc(5, 6, 30))
        self.assertEqual((closed["status"], closed["reason"]), ("closed", "After the close"))
        # 09:14 Mumbai (03:44 UTC) is before the open, 09:15 is open.
        before = regional.market_status("IN", utc(5, 3, 44))
        self.assertEqual((before["status"], before["reason"]), ("closed", "Before the open"))
        self.assertEqual(regional.market_status("IN", utc(5, 3, 45))["status"], "open")
        # Tokyo lunch: 11:30 to 12:30.
        self.assertEqual(regional.market_status("JP", utc(5, 2, 45))["status"], "break")

    def test_weekend_is_closed_in_local_time(self):
        saturday = regional.market_status("KR", utc(3, 2))
        self.assertEqual((saturday["status"], saturday["reason"], saturday["weekday"]),
                         ("closed", "Weekend", "Saturday"))
        # Sunday 23:30 UTC is already Monday 08:30 in Seoul: before the open, not weekend.
        monday = regional.market_status("KR", utc(4, 23, 30))
        self.assertEqual((monday["weekday"], monday["reason"]), ("Monday", "Before the open"))

    def test_all_markets_include_hong_kong_and_note(self):
        rows = regional.all_market_status(utc(5, 4))
        self.assertEqual([row["name"] for row in rows], ["India", "China", "Japan", "South Korea", "Hong Kong"])
        self.assertEqual(rows[-1]["status"], "break")  # 12:00 in Hong Kong
        self.assertIn("holidays", rows[0]["note"])

    def test_naive_datetime_is_rejected(self):
        with self.assertRaises(ValueError):
            regional.market_status("IN", datetime(2026, 10, 5, 4, 0))


class BenchmarkingTests(unittest.TestCase):
    ratios = [
        {"ratio_name": "return_on_equity", "value": 12, "unit": "percent"},
        {"ratio_name": "Debt To Equity", "value": 1.5, "unit": "x"},
        {"ratio_name": "currentRatio", "value": 1.8, "unit": "x"},
        {"ratio_name": "working_capital", "value": 500, "unit": "$"},
    ]

    def test_regional_tilt_is_applied_to_the_base_profile(self):
        india = get_profile("automobiles", "IN")["ratios"]["return_on_equity"]
        # Base 0.06 / 0.10 / 0.15 times the India tilt of 1.15.
        self.assertAlmostEqual(india["p25"], 0.069)
        self.assertAlmostEqual(india["median"], 0.115)
        self.assertAlmostEqual(india["p75"], 0.1725)
        japan = get_profile("automobiles", "jp")["ratios"]
        self.assertAlmostEqual(japan["return_on_equity"]["median"], 0.08)   # 0.10 * 0.80
        self.assertAlmostEqual(japan["current_ratio"]["p75"], 1.955)        # 1.7 * 1.15
        self.assertAlmostEqual(japan["asset_turnover"]["median"], 1.0)      # no tilt

    def test_compare_india(self):
        result = compare_against_industry(self.ratios, "automobiles", "IN")
        rows = {row["ratio_name"]: row for row in result["comparisons"]}
        # ROE of 12 percent -> 0.12: above the 0.115 median, below the 0.1725 upper quartile.
        self.assertEqual(rows["return_on_equity"]["company_value"], 0.12)
        self.assertEqual((rows["return_on_equity"]["percentile"], rows["return_on_equity"]["rank"]),
                         (65, "above_average"))
        self.assertEqual(rows["return_on_equity"]["deviation_pct"], 4.3)   # 0.005 / 0.115
        # Debt to equity 1.5 is above the 1.30 upper quartile; lower is better.
        self.assertEqual((rows["debt_to_equity"]["percentile"], rows["debt_to_equity"]["rank"]), (10, "poor"))
        self.assertEqual(rows["debt_to_equity"]["deviation_pct"], 114.3)   # 0.8 / 0.7
        # Current ratio 1.8 is above the 1.7 upper quartile.
        self.assertEqual(rows["current_ratio"]["percentile"], 90)
        # (65 + 10 + 90) / 3 = 55
        self.assertEqual(result["overall_score"], 55)
        self.assertEqual(result["overall_rank"], "above_average")
        self.assertEqual(result["strengths"], ["Current ratio"])
        self.assertEqual(result["weaknesses"], ["Debt to equity"])
        self.assertEqual(result["unmatched_ratios"], ["working_capital"])
        self.assertTrue(result["illustrative"])
        self.assertIn("Illustrative", result["disclaimer"])

    def test_percent_sign_unit_is_a_fraction_like_the_statement_analysis(self):
        # The statement analysis sends 0.12 with unit "%"; it must not be divided by 100.
        row = compare_against_industry(
            [{"ratio_name": "return_on_equity", "value": 0.12, "unit": "%"}], "automobiles", "IN",
        )["comparisons"][0]
        self.assertEqual((row["company_value"], row["percentile"]), (0.12, 65))

    def test_same_company_ranks_differently_in_japan(self):
        result = compare_against_industry(self.ratios, "automobiles", "JP")
        rows = {row["ratio_name"]: row for row in result["comparisons"]}
        self.assertEqual(rows["return_on_equity"]["percentile"], 90)   # 0.12 >= 0.15 * 0.8
        self.assertEqual(rows["current_ratio"]["percentile"], 65)      # 1.495 <= 1.8 < 1.955
        self.assertEqual(rows["debt_to_equity"]["percentile"], 10)     # 1.5 > 1.3 * 0.85
        self.assertEqual(result["region_name"], "Japan")

    def test_lower_is_better_bands(self):
        def band(value):
            return compare_against_industry(
                [{"ratio_name": "debt_to_equity", "value": value}], "automobiles", "IN",
            )["comparisons"][0]["percentile"]

        # India automobiles debt to equity: 0.30 / 0.70 / 1.30.
        self.assertEqual([band(0.30), band(0.70), band(1.30), band(1.31)], [90, 65, 35, 10])

    def test_no_matching_ratios_is_not_scored(self):
        result = compare_against_industry([{"ratio_name": "unknown", "value": 1}], "chemicals", "KR")
        self.assertEqual((result["overall_score"], result["overall_rank"], result["ratios_compared"]),
                         (0, "not_scored", 0))

    def test_invalid_inputs(self):
        with self.assertRaises(ValueError):
            compare_against_industry(self.ratios, "automobiles", "IR")
        with self.assertRaises(ValueError):
            compare_against_industry(self.ratios, "banking", "IN")
        with self.assertRaises(ValueError):
            compare_against_industry([{"ratio_name": "current_ratio", "value": float("nan")}], "chemicals", "IN")

    def test_profiles_are_ordered_and_named(self):
        self.assertEqual(normalize_ratio_name("Gross Profit-Margin"), "gross_profit_margin")
        for sector in get_available_industries():
            for region in ("IN", "CN", "JP", "KR"):
                for name, bench in get_profile(sector["id"], region)["ratios"].items():
                    self.assertLess(bench["p25"], bench["median"], f"{sector['id']} {name}")
                    self.assertLess(bench["median"], bench["p75"], f"{sector['id']} {name}")

    def test_auto_detect_by_keyword(self):
        self.assertEqual(auto_detect_industry("Sample Steel Works", []), "steel_metals")
        self.assertIsNone(auto_detect_industry("Sample Holdings", []))


if __name__ == "__main__":
    unittest.main()
