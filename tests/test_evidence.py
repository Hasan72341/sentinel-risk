import tempfile
import unittest
from pathlib import Path

import pandas as pd

from sentinel_risk.evidence import MappingStatus, inspect_statement
from sentinel_risk.evidence.intake import normalize_label, propose_mappings


STATEMENT = {
    "period": ["2024", "2025"],
    "revenue": [1_000, 1_200],
    "gross_profit": [400, 540],
    "operating_income": [200, 264],
    "net_income": [120, 156],
    "total_assets": [2_000, 2_200],
    "current_assets": [800, 900],
    "inventory": [200, 240],
    "cash": [150, 180],
    "total_liabilities": [900, 950],
    "current_liabilities": [400, 450],
    "equity": [1_100, 1_250],
    "operating_cash_flow": [180, 210],
    "interest_expense": [40, 44],
    "cost_of_goods_sold": [600, 660],
    "accounts_receivable": [125, 150],
}


class EvidenceCompilerTests(unittest.TestCase):
    def _write_statement(self, data: dict[str, list[object]]) -> Path:
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        path = Path(directory.name) / "statement.csv"
        pd.DataFrame(data).to_csv(path, index=False)
        return path

    def test_exact_canonical_file_is_analysis_ready_and_traceable(self):
        result = inspect_statement(self._write_statement(STATEMENT))

        self.assertTrue(result.is_ready_for_analysis)
        self.assertEqual(result.health_summary["blocking"], 0)
        self.assertEqual(len(result.facts), 30)
        self.assertEqual(result.facts[0].locations[0].file_name, "statement.csv")
        self.assertEqual(result.facts[0].locations[0].row_number, 2)

    def test_alias_mapping_requires_explicit_reviewer_confirmation(self):
        aliased = {("Sales" if key == "revenue" else key): value for key, value in STATEMENT.items()}
        path = self._write_statement(aliased)

        initial = inspect_statement(path)
        sales_mapping = next(mapping for mapping in initial.mappings if mapping.source_column == "Sales")
        self.assertEqual(sales_mapping.concept_id, "revenue")
        self.assertEqual(sales_mapping.status, MappingStatus.SUGGESTED)
        self.assertFalse(initial.is_ready_for_analysis)

        reviewed = inspect_statement(path, mapping_overrides={"Sales": "revenue"})
        self.assertTrue(reviewed.is_ready_for_analysis)
        self.assertEqual(next(mapping for mapping in reviewed.mappings if mapping.source_column == "Sales").status, MappingStatus.CONFIRMED)

    def test_unbalanced_statement_blocks_analysis(self):
        unbalanced = {key: list(value) for key, value in STATEMENT.items()}
        unbalanced["equity"][1] = 1_200

        result = inspect_statement(self._write_statement(unbalanced))

        self.assertFalse(result.is_ready_for_analysis)
        self.assertIn("balance_sheet_not_balanced", {issue.rule_id for issue in result.issues})

    def test_missing_required_concept_is_reported(self):
        incomplete = {key: value for key, value in STATEMENT.items() if key != "accounts_receivable"}

        result = inspect_statement(self._write_statement(incomplete))

        self.assertFalse(result.is_ready_for_analysis)
        missing_issue = next(issue for issue in result.issues if issue.rule_id == "missing_required_concepts")
        self.assertIn("accounts_receivable", missing_issue.message)

    def test_regional_english_headers_are_suggested_not_auto_confirmed(self):
        headers = [
            "Financial Year", "Turnover", "Profit After Tax", "Net Worth",
            "Sundry Debtors", "Cash and Deposits", "Finance Costs", "Shareholders' Funds",
            "Revenue (INR crore)", "Mystery Column",
        ]
        mappings = {mapping.source_column: mapping for mapping in propose_mappings(headers)}

        expected = {
            "Financial Year": "period",
            "Turnover": "revenue",
            "Profit After Tax": "net_income",
            "Net Worth": "equity",
            "Sundry Debtors": "accounts_receivable",
            "Cash and Deposits": "cash",
            "Finance Costs": "interest_expense",
            "Shareholders' Funds": "equity",
            "Revenue (INR crore)": "revenue",
        }
        for header, concept in expected.items():
            self.assertEqual(mappings[header].concept_id, concept, header)
            self.assertEqual(mappings[header].status, MappingStatus.SUGGESTED, header)
        self.assertEqual(mappings["Revenue (INR crore)"].confidence, 0.85)
        self.assertIsNone(mappings["Mystery Column"].concept_id)
        self.assertEqual(mappings["Mystery Column"].status, MappingStatus.NEEDS_REVIEW)

    def test_label_normalization_and_english_locale(self):
        self.assertEqual(normalize_label("  Net  Sales "), "net_sales")
        self.assertEqual(normalize_label("Shareholders' Funds"), "shareholders_funds")
        result = inspect_statement(self._write_statement(STATEMENT))
        self.assertEqual(result.manifest.detected_locale, "en")


if __name__ == "__main__":
    unittest.main()
