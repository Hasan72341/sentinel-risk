"""English-only extraction, sentiment and copilot behaviour (India, China, Japan, South Korea wording)."""

import sys
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).parents[1]
API_ROOT = PROJECT_ROOT / "api"
if str(API_ROOT) not in sys.path:
    sys.path.insert(0, str(API_ROOT))

from app.services import document_intelligence, pdf_extractor, sentiment
from app.services.ai_copilot import FINANCIAL_ANALYST_SYSTEM_PROMPT, built_in_analysis
from app.services.document_intelligence import (
    detect_document_type,
    detect_reporting_unit,
    extract_from_text,
)
from app.services.pdf_extractor import _match_field, _parse_number
from app.services.sentiment import _score_text, analyze_sentiment, sentiment_demo


def _non_latin_letters(text: str) -> list[str]:
    """Letters outside Latin blocks; symbols, arrows and emoji are allowed."""
    return [char for char in text if char.isalpha() and ord(char) > 0x024F]


class DocumentTermTests(unittest.TestCase):
    def test_indian_statement_wording_is_extracted(self):
        text = "\n".join([
            "Statement of Profit and Loss (Rs. in crore)",
            "Revenue from operations 1,23,456.50",
            "Cost of materials consumed 80,000",
            "Finance costs (1,200)",
            "Profit before tax 9,000",
            "Profit after tax 6,750",
            "Reserves and surplus 45,000",
            "Shareholders' funds 50,000",
            "Total assets 120,000",
        ])
        data = extract_from_text(text)

        self.assertEqual(data["revenue"], 123456.5)
        self.assertEqual(data["cogs"], 80000.0)
        self.assertEqual(data["interest_expense"], 1200.0)  # cost lines stay positive
        self.assertEqual(data["ebt"], 9000.0)
        self.assertEqual(data["net_income"], 6750.0)
        self.assertEqual(data["retained_earnings"], 45000.0)
        self.assertEqual(data["total_equity"], 50000.0)
        self.assertEqual(data["gross_profit"], 123456.5 - 80000.0)
        self.assertEqual(data["total_liabilities"], 120000.0 - 50000.0)
        self.assertEqual(detect_document_type(text), "income_statement")

    def test_japanese_and_korean_english_wording(self):
        data = extract_from_text("\n".join([
            "Net sales 5,000",
            "Cost of sales 3,500",
            "Operating profit 800",
            "Ordinary income 750",
            "Profit attributable to owners of parent (120)",
            "Cash and deposits 900",
            "Total net assets 4,000",
        ]))
        self.assertEqual(data["revenue"], 5000.0)
        self.assertEqual(data["cogs"], 3500.0)  # "cost of sales" must not be read as sales
        self.assertEqual(data["ebit"], 800.0)
        self.assertEqual(data["ebt"], 750.0)
        self.assertEqual(data["net_income"], -120.0)  # a loss in parentheses is negative
        self.assertEqual(data["cash"], 900.0)
        self.assertEqual(data["total_equity"], 4000.0)

    def test_whole_word_matching(self):
        self.assertNotIn("ebit", extract_from_text("EBITDA 99"))

    def test_reporting_unit_detection(self):
        self.assertEqual(
            detect_reporting_unit("(Rs. in crore)"),
            {"currency": "INR", "unit": "crore", "multiplier": 10_000_000},
        )
        self.assertEqual(
            detect_reporting_unit("Amounts in INR lakhs"),
            {"currency": "INR", "unit": "lakh", "multiplier": 100_000},
        )
        self.assertEqual(
            detect_reporting_unit("Millions of yen"),
            {"currency": "JPY", "unit": "million", "multiplier": 1_000_000},
        )
        self.assertEqual(
            detect_reporting_unit("(KRW in millions)"),
            {"currency": "KRW", "unit": "million", "multiplier": 1_000_000},
        )
        self.assertEqual(
            detect_reporting_unit("RMB'000"),
            {"currency": "CNY", "unit": "thousand", "multiplier": 1_000},
        )
        self.assertEqual(
            detect_reporting_unit("In a million ways we grew"),
            {"currency": None, "unit": "units", "multiplier": 1},
        )

    def test_pdf_number_parsing(self):
        self.assertEqual(_parse_number("12.5 crore"), 125_000_000.0)
        self.assertEqual(_parse_number("3 lakh"), 300_000.0)
        self.assertEqual(_parse_number("Rs. 1,23,45,678"), 12_345_678.0)
        self.assertEqual(_parse_number("JPY 500 million"), 500_000_000.0)
        self.assertEqual(_parse_number("1.2bn"), 1_200_000_000.0)
        self.assertEqual(_parse_number("1.23M"), 1_230_000.0)
        self.assertEqual(_parse_number("(1,234.56)"), -1234.56)
        self.assertIsNone(_parse_number("abc"))

    def test_pdf_field_matching(self):
        self.assertEqual(_match_field("Turnover"), "revenue")
        self.assertEqual(_match_field("Sales"), "revenue")
        self.assertEqual(_match_field("Cost of sales"), "cost_of_goods_sold")
        self.assertEqual(_match_field("Profit after tax"), "net_income")
        self.assertEqual(_match_field("Reserves and surplus"), "retained_earnings")
        self.assertEqual(_match_field("Net worth"), "total_equity")
        self.assertEqual(_match_field("Total current assets"), "current_assets")
        self.assertIsNone(_match_field(""))


class SentimentTests(unittest.TestCase):
    def test_phrase_and_token_scores(self):
        # One positive phrase (1.5) and nothing else.
        score = _score_text("Profit after tax rose 40 percent")
        self.assertEqual((score["pos_score"], score["neg_score"], score["label"]), (1.5, 0.0, "positive"))

        # "strong" (1.0) vs "weak" (1.0): (1 - 1) / 2 = 0.
        mixed = _score_text("strong sales but weak margins")
        self.assertEqual(mixed["sentiment_score"], 0.0)
        self.assertEqual(mixed["label"], "neutral")

    def test_negation_intensifier_and_inflection(self):
        # "not" flips "profitable" to negative at 0.8.
        self.assertEqual(_score_text("not profitable")["neg_score"], 0.8)
        # "very" multiplies "weak" by 1.5.
        self.assertEqual(_score_text("very weak")["neg_score"], 1.5)
        # "increased" is matched through "increase".
        self.assertEqual(_score_text("exports increased")["pos_words"], ["increase"])

    def test_batch_distribution(self):
        result = analyze_sentiment(["Rating downgrade after bad loans", "Upward revision announced", "Meeting held"])
        self.assertEqual(result["distribution"], {"positive": 1, "negative": 1, "neutral": 1})
        self.assertEqual([item["lang"] for item in result["texts"]], ["en", "en", "en"])

    def test_demo_is_english_sample_data(self):
        demo = sentiment_demo()
        self.assertTrue(demo["demo_info"]["is_sample_data"])
        self.assertIn("Illustrative sample data", demo["demo_info"]["description"])
        self.assertEqual(demo["demo_info"]["news_count"], 12)
        self.assertEqual(len(demo["per_stock"]), 5)


class CopilotTests(unittest.TestCase):
    ANALYSIS = {
        "company_name": "Sample Co",
        "period": "FY2025",
        "ratios": [
            {"category": "liquidity", "ratio_name": "current_ratio", "value": 0.8, "unit": "x", "status": "critical"},
            {"category": "profitability", "ratio_name": "net_margin", "value": 0.12, "unit": "%", "status": "good"},
        ],
    }

    def test_overall_summary_scores(self):
        text = built_in_analysis("Give me the overall health", self.ANALYSIS)["response"]
        self.assertIn("**Profitability**: 100/100", text)
        self.assertIn("**Liquidity**: 30/100", text)
        self.assertIn("**Overall Score**", text)
        self.assertIn("50%", text)  # 1 good ratio out of 2

    def test_question_routing(self):
        self.assertIn("# Areas of Concern", built_in_analysis("Which ratios need attention?", self.ANALYSIS)["response"])
        self.assertIn("# Liquidity Analysis", built_in_analysis("Check working capital", self.ANALYSIS)["response"])
        self.assertIn("# Improvement Recommendations", built_in_analysis("What do you suggest?", self.ANALYSIS)["response"])
        self.assertIn("Could you be more specific", built_in_analysis("hello", None, {"models": []})["response"])

    def test_prompt_and_replies_are_english_only(self):
        self.assertIn("Always respond in English", FINANCIAL_ANALYST_SYSTEM_PROMPT)
        self.assertEqual(_non_latin_letters(FINANCIAL_ANALYST_SYSTEM_PROMPT), [])
        self.assertEqual(_non_latin_letters(built_in_analysis("hello")["response"]), [])


class SourceLanguageTests(unittest.TestCase):
    def test_service_sources_contain_no_non_latin_letters(self):
        for module in (document_intelligence, pdf_extractor, sentiment):
            source = Path(module.__file__).read_text(encoding="utf-8")
            self.assertEqual(_non_latin_letters(source), [], module.__name__)


if __name__ == "__main__":
    unittest.main()
