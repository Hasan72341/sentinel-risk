import unittest

from app.services.compliance import (
    DISCLOSURE_ITEMS, get_checks, get_compliance_standards, get_frameworks,
    resolve_framework, run_compliance_check,
)

# A small, internally consistent set of accounts (illustrative figures).
CURRENT = {
    "total_assets": 1000, "current_assets": 400, "non_current_assets": 600,
    "cash": 100, "inventory": 120, "receivables": 150,
    "total_liabilities": 600, "current_liabilities": 250, "non_current_liabilities": 350,
    "total_equity": 400,
    "revenue": 1200, "cost_of_sales": 800, "gross_profit": 400,
    "profit_before_tax": 100, "tax_expense": 25, "net_income": 75,
    "operating_cash_flow": 90, "investing_cash_flow": -50, "financing_cash_flow": -20,
    "net_change_in_cash": 20, "opening_cash": 80, "closing_cash": 100,
    "dividends": 15,
}
PRIOR = {"total_assets": 950, "total_equity": 340, "revenue": 1100}
ALL_STATEMENTS = ["balance_sheet", "income_statement", "cash_flow_statement", "changes_in_equity", "notes"]
ALL_DISCLOSED = {key: True for key, _ in DISCLOSURE_ITEMS}


def by_id(report):
    return {row["check_id"]: row for row in report["results"]}


class ComplianceTests(unittest.TestCase):
    def test_clean_accounts_pass_every_check(self):
        report = run_compliance_check(CURRENT, "IND_AS", PRIOR, ALL_DISCLOSED, ALL_STATEMENTS)
        self.assertEqual(report["total_checks"], 22)  # 13 consistency checks + 9 checklist items
        self.assertEqual((report["passed"], report["failed"], report["not_applicable"]), (22, 0, 0))
        self.assertEqual(report["compliance_score"], 100)
        self.assertEqual(report["status"], "compliant")
        self.assertEqual(report["framework"]["id"], "IND_AS")
        self.assertTrue(report["simplified"])
        self.assertIn("Not an audit", report["disclaimer"])

    def test_unanswered_items_are_not_counted_in_the_score(self):
        report = run_compliance_check(CURRENT, "IFRS", PRIOR)
        rows = by_id(report)
        # Statement presence is only inferred for three statements, and the nine
        # checklist items are unanswered: ten manual items, twelve passes.
        self.assertEqual((report["passed"], report["failed"], report["not_applicable"]), (12, 0, 10))
        self.assertEqual(report["compliance_score"], 100)
        self.assertEqual(rows["PRES_01"]["status"], "not_applicable")
        self.assertEqual(rows["DISC_01"]["status"], "not_applicable")
        self.assertEqual(report["recommendations"][-1]["title"], "Complete the manual review items")

    def test_unbalanced_balance_sheet_is_blocking(self):
        # Liabilities 600 + equity 390 = 990 against assets of 1000: 1% out, tolerance 0.5%.
        report = run_compliance_check({**CURRENT, "total_equity": 390}, "IFRS", PRIOR,
                                      ALL_DISCLOSED, ALL_STATEMENTS)
        rows = by_id(report)
        self.assertEqual(rows["BS_01"]["status"], "fail")
        self.assertIn("components give 990.00, reported 1,000.00 (difference 10.00)", rows["BS_01"]["message"])
        # Equity roll-forward: 340 + 75 - 15 = 400 against 390 reported.
        self.assertEqual(rows["COMP_02"]["status"], "fail")
        self.assertIn("gives 400.00, reported 390.00 (unexplained -10.00)", rows["COMP_02"]["message"])
        self.assertEqual((report["passed"], report["failed"]), (20, 2))
        self.assertEqual(report["compliance_score"], 91)  # 20 / 22
        # A blocking failure overrides the score.
        self.assertEqual(report["status"], "non_compliant")
        self.assertEqual(len(report["critical_issues"]), 1)
        self.assertEqual(report["recommendations"][0]["priority"], "critical")

    def test_rounding_tolerance(self):
        # 600 + 396 = 996: 0.4% out, inside the 0.5% tolerance.
        within = run_compliance_check({**CURRENT, "total_equity": 396}, "CAS")
        self.assertEqual(by_id(within)["BS_01"]["status"], "pass")
        # The same gap fails at a 0.1% tolerance.
        strict = run_compliance_check({**CURRENT, "total_equity": 396}, "CAS", tolerance_pct=0.1)
        self.assertEqual(by_id(strict)["BS_01"]["status"], "fail")

    def test_subtotal_checks(self):
        data = {**CURRENT, "gross_profit": 450, "net_income": 60, "net_change_in_cash": 30,
                "non_current_assets": 650}
        rows = by_id(run_compliance_check(data, "KIFRS"))
        self.assertEqual(rows["IS_01"]["status"], "fail")   # 1200 - 800 = 400, not 450
        self.assertIn("components give 400.00, reported 450.00", rows["IS_01"]["message"])
        self.assertEqual(rows["IS_02"]["status"], "fail")   # 100 - 25 = 75, not 60
        self.assertEqual(rows["CF_01"]["status"], "fail")   # 90 - 50 - 20 = 20, not 30
        self.assertEqual(rows["CF_02"]["status"], "fail")   # 80 + 30 = 110, not 100
        self.assertEqual(rows["BS_02"]["status"], "fail")   # 400 + 650 = 1050, not 1000
        self.assertEqual(rows["BS_03"]["status"], "pass")   # 250 + 350 = 600

    def test_fx_effect_is_included_in_cash_reconciliation(self):
        data = {**CURRENT, "fx_effect_on_cash": 5, "net_change_in_cash": 25, "closing_cash": 105}
        rows = by_id(run_compliance_check(data, "JGAAP"))
        self.assertEqual(rows["CF_01"]["status"], "pass")   # 90 - 50 - 20 + 5 = 25
        self.assertEqual(rows["CF_02"]["status"], "pass")   # 80 + 25 = 105

    def test_sign_and_component_checks(self):
        rows = by_id(run_compliance_check(
            {"total_assets": 500, "current_assets": 600, "cash": -10, "total_equity": -40,
             "total_liabilities": 540}, "IFRS"))
        self.assertEqual(rows["SIGN_01"]["status"], "fail")
        self.assertIn("cash", rows["SIGN_01"]["message"])
        self.assertEqual(rows["SIGN_02"]["status"], "fail")
        self.assertIn("current_assets exceeds total_assets", rows["SIGN_02"]["message"])
        self.assertEqual(rows["SIGN_03"]["status"], "fail")
        self.assertEqual(rows["BS_01"]["status"], "pass")   # 540 - 40 = 500

    def test_statements_and_comparatives(self):
        report = run_compliance_check(CURRENT, "JGAAP", None, None, ["balance_sheet", "income_statement", "notes"])
        rows = by_id(report)
        self.assertEqual(rows["PRES_01"]["status"], "fail")
        self.assertIn("Statement of cash flows", rows["PRES_01"]["message"])
        # J-GAAP names the equity statement differently.
        self.assertIn("Statement of changes in net assets", rows["PRES_01"]["message"])
        self.assertEqual(rows["COMP_01"]["status"], "fail")
        self.assertEqual(rows["COMP_02"]["status"], "not_applicable")
        self.assertEqual(report["status"], "non_compliant")  # PRES_01 is blocking

    def test_disclosure_checklist(self):
        report = run_compliance_check(CURRENT, "IFRS", PRIOR,
                                      {"related_parties": False, "going_concern": True})
        rows = by_id(report)
        self.assertEqual(rows["DISC_03"]["status"], "pass")            # going concern
        self.assertEqual(rows["DISC_04"]["status"], "fail")            # related parties
        self.assertEqual(rows["DISC_05"]["status"], "not_applicable")  # unanswered
        # 12 consistency passes + 1 checklist pass, 1 failure: 13 / 14 = 93%.
        self.assertEqual(report["compliance_score"], 93)
        self.assertEqual(report["status"], "compliant")
        self.assertEqual(len(report["warnings"]), 1)

    def test_no_data(self):
        report = run_compliance_check({}, "IFRS", statements_present=ALL_STATEMENTS)
        self.assertEqual(by_id(report)["BS_01"]["status"], "not_applicable")
        empty = run_compliance_check({"note": None}, "IFRS", {"total_assets": 1})
        self.assertEqual(by_id(empty)["PRES_01"]["status"], "fail")

    def test_frameworks_and_catalogue(self):
        self.assertEqual([f["id"] for f in get_frameworks()], ["IFRS", "IND_AS", "CAS", "JGAAP", "KIFRS"])
        self.assertEqual(resolve_framework("Ind AS")["id"], "IND_AS")
        self.assertEqual(resolve_framework("j-gaap")["id"], "JGAAP")
        self.assertEqual(resolve_framework("K-IFRS")["id"], "KIFRS")
        self.assertEqual(len(get_checks()), 22)
        self.assertEqual(sum(s["check_count"] for s in get_compliance_standards()), 22)

    def test_invalid_inputs(self):
        with self.assertRaises(ValueError):
            run_compliance_check(CURRENT, "XX_GAAP")
        with self.assertRaises(ValueError):
            run_compliance_check({**CURRENT, "cash": float("inf")}, "IFRS")
        with self.assertRaises(ValueError):
            run_compliance_check(CURRENT, "IFRS", disclosures={"made_up": True})
        with self.assertRaises(ValueError):
            run_compliance_check(CURRENT, "IFRS", statements_present=["ledger"])
        with self.assertRaises(ValueError):
            run_compliance_check(CURRENT, "IFRS", tolerance_pct=10)


if __name__ == "__main__":
    unittest.main()
