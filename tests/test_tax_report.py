import tempfile
import unittest
from pathlib import Path

from reportlab.pdfgen import canvas

from sentinel_risk.evidence import extract_tax_report_evidence
from sentinel_risk.evidence.tax_report import (
    _concept_for,
    _detect_currency,
    _parse_number,
    _period_for,
)


class TaxReportEvidenceTests(unittest.TestCase):
    def _create_tax_report(self, rows: list[str]) -> Path:
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        path = Path(directory.name) / "tax_audit_2025.pdf"
        pdf = canvas.Canvas(str(path))
        y_position = 760
        for row in rows:
            pdf.drawString(72, y_position, row)
            y_position -= 28
        pdf.save()
        return path

    def test_extracts_tax_facts_with_page_level_provenance(self):
        report = self._create_tax_report([
            "Tax Audit Report 2025 (USD)",
            "Declared Tax: 1,000",
            "Tax Adjustment: 250",
            "Assessed Tax: 1,250",
            "Tax Penalty: (50)",
        ])

        result = extract_tax_report_evidence(report)
        facts = {fact.concept_id: fact for fact in result.facts}

        self.assertTrue(result.is_ready_for_review)
        self.assertEqual(result.manifest.source_type, "pdf")
        self.assertEqual(facts["tax_declared"].value, 1000.0)
        self.assertEqual(facts["tax_adjustment"].value, 250.0)
        self.assertEqual(facts["tax_assessed"].value, 1250.0)
        self.assertEqual(facts["tax_penalty"].value, -50.0)
        self.assertEqual(facts["tax_assessed"].period, "2025")
        self.assertEqual(facts["tax_assessed"].locations[0].page_number, 1)
        self.assertEqual(facts["tax_assessed"].locations[0].sheet_name, "PDF")

    def test_marks_reconciliation_difference_for_reviewer(self):
        report = self._create_tax_report([
            "Tax Audit Report 2025 (USD)",
            "Declared Tax: 1,000",
            "Tax Adjustment: 250",
            "Assessed Tax: 1,100",
        ])

        result = extract_tax_report_evidence(report)

        self.assertIn("tax_assessment_reconciliation_difference", {issue.rule_id for issue in result.issues})

    def test_indian_filing_wording_units_and_fiscal_year(self):
        report = self._create_tax_report([
            "Assessment Order FY 2024-25 (Rs. in crore)",
            "Tax as per return: 12.5 crore",
            "Tax deducted at source: 3 lakh",
            "GST payable: 1,25,000",
            "Tax demand: 2 crore",
        ])

        result = extract_tax_report_evidence(report)
        facts = {fact.concept_id: fact for fact in result.facts}

        self.assertEqual(result.manifest.detected_locale, "en")
        self.assertEqual(facts["tax_declared"].value, 125_000_000.0)
        self.assertEqual(facts["withholding_tax"].value, 300_000.0)
        self.assertEqual(facts["vat_payable"].value, 125_000.0)
        self.assertEqual(facts["tax_payable"].value, 20_000_000.0)
        self.assertEqual(facts["tax_declared"].currency, "INR")
        self.assertEqual(facts["tax_declared"].period, "2024-25")

    def test_currency_detection_covers_target_markets(self):
        self.assertEqual(_detect_currency("Amounts in INR lakhs"), "INR")
        self.assertEqual(_detect_currency("Figures in Rs. crore"), "INR")
        self.assertEqual(_detect_currency("Unit: RMB thousand"), "CNY")
        self.assertEqual(_detect_currency("Millions of yen"), "JPY")
        self.assertEqual(_detect_currency("In millions of Korean won"), "KRW")
        self.assertEqual(_detect_currency("Tax Audit Report 2025 (USD)"), "USD")
        self.assertIsNone(_detect_currency("Tax Audit Report 2025"))

    def test_number_parsing_handles_units_and_grouping(self):
        self.assertEqual(_parse_number("1,23,45,678"), 12_345_678.0)
        self.assertEqual(_parse_number("2.5 crore"), 25_000_000.0)
        self.assertEqual(_parse_number("4 lakhs"), 400_000.0)
        self.assertEqual(_parse_number("1.5 bn"), 1_500_000_000.0)
        self.assertEqual(_parse_number("3M"), 3_000_000.0)
        self.assertEqual(_parse_number("(50)"), -50.0)
        self.assertIsNone(_parse_number("n/a"))

    def test_concept_matching_uses_whole_english_words(self):
        self.assertEqual(_concept_for("Consumption tax payable"), "vat_payable")
        self.assertEqual(_concept_for("Late payment surcharge"), "late_payment_interest")
        self.assertEqual(_concept_for("TDS"), "withholding_tax")
        self.assertIsNone(_concept_for(""))
        self.assertIsNone(_concept_for("Accounting standards applied"))

    def test_period_detection(self):
        self.assertEqual(_period_for("Assessment year 2025/2026"), "2025-26")
        self.assertEqual(_period_for("Fiscal year ended March 31, 2025"), "2025")
        self.assertEqual(_period_for("Report dated 2025-03-31"), "2025")
        self.assertEqual(_period_for("no year here"), "unknown")


if __name__ == "__main__":
    unittest.main()
