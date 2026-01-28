import unittest

from app.services.credit_rating import (
    COUNTERPARTY_TYPES,
    COUNTRIES,
    QUALITATIVE_FACTORS,
    QUANTITATIVE_FACTORS,
    SAMPLE_COUNTERPARTIES,
    assess_due_diligence,
    due_diligence_checklist,
    generate_credit_review,
    grade_for_score,
    interpolate_score,
    methodology,
    propose_limit,
    qualitative_score,
    review_frequency_for_grade,
    sample_peers,
    score_counterparty,
)

# Every corporate factor sits exactly halfway between its anchors:
# revenue 1000 (log10 midpoint of 100 and 10000), EBITDA margin 17.5%,
# ROA 5%, debt/EBITDA 3.5x, coverage 4.5x, debt/capital 50%,
# current ratio 1.4x, FCF/debt 15%.
MID_CORPORATE = {
    "revenue": 1000, "ebitda": 175, "operating_income": 90, "interest_expense": 20,
    "net_income": 50, "total_assets": 1000, "current_assets": 140, "cash": 61.25,
    "current_liabilities": 100, "total_debt": 612.5, "equity": 612.5,
    "operating_cash_flow": 141.875, "capex": 50,
}
# Every corporate factor at or beyond its strong anchor.
STRONG_CORPORATE = {
    "revenue": 10000, "ebitda": 3000, "operating_income": 2400, "interest_expense": 100,
    "net_income": 1500, "total_assets": 15000, "current_assets": 4000, "cash": 1000,
    "current_liabilities": 2000, "total_debt": 3000, "equity": 12000,
    "operating_cash_flow": 1800, "capex": 900,
}
# Every FI factor halfway between anchors: CET1 11.5%, equity/assets 6.5%,
# NPL 4.5%, coverage 95%, loans/deposits 100%, liquidity 120%, ROA 0.75%, C/I 60%.
MID_FI = {
    "operating_income": 100, "operating_expenses": 60, "net_income": 7.5,
    "total_assets": 1000, "gross_loans": 600, "non_performing_loans": 27,
    "loan_loss_reserves": 25.65, "customer_deposits": 600, "total_equity": 65,
    "cet1_capital": 57.5, "risk_weighted_assets": 500, "liquid_assets": 120,
    "net_cash_outflows_30d": 100,
}
# Every fund factor halfway: NAV 1000, leverage 3.5x, liquid 45%, notice 45.5d,
# volatility 17%, drawdown 22.5%, top-5 50%, flows -10%.
MID_FUND = {
    "net_asset_value": 1000, "gross_exposure": 3500, "liquid_assets_7d": 450,
    "redemption_notice_days": 45.5, "top5_investor_share": 0.5, "net_flows_12m_pct": -0.10,
    "annualised_volatility": 0.17, "max_drawdown": 0.225,
}


def qual(value):
    return {spec["key"]: value for spec in QUALITATIVE_FACTORS}


def factor(result, key):
    return next(f for f in result["factors"] if f["key"] == key)


class ScoringPrimitiveTests(unittest.TestCase):
    def test_interpolation_between_anchors(self):
        self.assertAlmostEqual(interpolate_score(0.175, 0.05, 0.30), 50.0)
        self.assertAlmostEqual(interpolate_score(0.10, 0.05, 0.30), 20.0)
        # Lower-is-better factor: 2x between weak 6x and strong 1x = 4/5 of the way.
        self.assertAlmostEqual(interpolate_score(2.0, 6.0, 1.0), 80.0)

    def test_interpolation_is_capped(self):
        self.assertEqual(interpolate_score(0.50, 0.05, 0.30), 100.0)
        self.assertEqual(interpolate_score(-0.10, 0.05, 0.30), 0.0)
        self.assertEqual(interpolate_score(9.0, 6.0, 1.0), 0.0)

    def test_log_scale(self):
        self.assertAlmostEqual(interpolate_score(1000, 100, 10000, log_scale=True), 50.0)
        self.assertEqual(interpolate_score(0, 100, 10000, log_scale=True), 0.0)

    def test_qualitative_score(self):
        self.assertEqual([qualitative_score(a) for a in (1, 2, 3, 4, 5)], [0, 25, 50, 75, 100])
        with self.assertRaises(ValueError):
            qualitative_score(6)

    def test_grade_bands(self):
        expected = {100: "IR1", 90: "IR1", 89.99: "IR2", 80: "IR2", 70: "IR3", 62: "IR4",
                    54: "IR5", 50: "IR6", 46: "IR6", 45.99: "IR7", 38: "IR7", 30: "IR8",
                    20: "IR9", 19.99: "IR10", 0: "IR10"}
        for score, grade in expected.items():
            self.assertEqual(grade_for_score(score)["grade"], grade, score)
        self.assertEqual(grade_for_score(50)["pd_1y"], 0.025)

    def test_pd_increases_as_grade_weakens(self):
        pds = [row["pd_1y"] for row in methodology()["rating_scale"]]
        self.assertEqual(pds, sorted(pds))

    def test_review_frequency(self):
        self.assertEqual(review_frequency_for_grade("IR5"), "annual")
        self.assertEqual(review_frequency_for_grade("IR6"), "semi_annual")

    def test_weights_sum_to_100(self):
        qualitative = sum(spec["weight"] for spec in QUALITATIVE_FACTORS)
        self.assertEqual(qualitative, 30)
        for kind in COUNTERPARTY_TYPES:
            self.assertEqual(sum(spec[2] for spec in QUANTITATIVE_FACTORS[kind]), 70, kind)

    def test_limit(self):
        # IR3 = 6% of equity; funds use half the percentage of NAV.
        self.assertEqual(propose_limit("corporate", "IR3", 1000)["proposed_limit"], 60)
        self.assertEqual(propose_limit("fund", "IR3", 1000)["proposed_limit"], 30)
        self.assertEqual(propose_limit("financial_institution", "IR9", 1000)["proposed_limit"], 0)


class ScorecardTests(unittest.TestCase):
    def test_corporate_midpoint_scores_50(self):
        result = score_counterparty("corporate", "Mid Co", "IN", MID_CORPORATE, qual(3))
        for item in result["factors"]:
            self.assertAlmostEqual(item["score"], 50.0, places=2, msg=item["key"])
        self.assertEqual(result["total_score"], 50.0)
        self.assertEqual(result["grade"], "IR6")
        self.assertEqual(result["pd_1y"], 0.025)
        self.assertEqual(result["review_frequency"], "semi_annual")
        self.assertEqual(result["strengths"], [])
        self.assertEqual(result["concerns"], [])
        # IR6 = 3% of equity 612.5
        self.assertEqual(result["limit"]["proposed_limit"], 18.38)
        self.assertAlmostEqual(factor(result, "debt_to_ebitda")["value"], 3.5)
        self.assertEqual(factor(result, "debt_to_ebitda")["weighted_score"], 7.5)
        self.assertIsNone(result["peer_comparison"])

    def test_corporate_all_strong_is_ir1(self):
        result = score_counterparty("corporate", "Strong Co", "JP", STRONG_CORPORATE, qual(5))
        self.assertEqual(result["total_score"], 100.0)
        self.assertEqual(result["grade"], "IR1")
        self.assertEqual(result["recommendation"], "Approve")
        self.assertEqual(len(result["strengths"]), 12)
        # IR1 = 10% of equity 12000
        self.assertEqual(result["limit"]["proposed_limit"], 1200.0)
        self.assertEqual(result["local_currency"], "JPY")

    def test_qualitative_shift_changes_total_by_weight(self):
        # Quant all 50 (35 points); qualitative all 5 adds 30 points -> 65 -> IR4.
        result = score_counterparty("corporate", "Mid Co", "KR", MID_CORPORATE, qual(5))
        self.assertEqual(result["total_score"], 65.0)
        self.assertEqual(result["quantitative_score"], 50.0)
        self.assertEqual(result["qualitative_score"], 100.0)
        self.assertEqual(result["grade"], "IR4")

    def test_corporate_edge_cases(self):
        loss_making = dict(MID_CORPORATE, ebitda=-10)
        result = score_counterparty("corporate", "Loss Co", "CN", loss_making, qual(3))
        self.assertEqual(factor(result, "debt_to_ebitda")["score"], 0.0)
        self.assertIsNone(factor(result, "debt_to_ebitda")["value"])

        debt_free = dict(MID_CORPORATE, total_debt=0, interest_expense=0)
        result = score_counterparty("corporate", "Debt Free Co", "CN", debt_free, qual(3))
        for key in ("debt_to_ebitda", "interest_coverage", "debt_to_capital", "fcf_to_debt"):
            self.assertEqual(factor(result, key)["score"], 100.0, key)

    def test_fi_midpoint_scores_50(self):
        result = score_counterparty("financial_institution", "Mid Bank", "CN", MID_FI, qual(3))
        for item in result["factors"]:
            self.assertAlmostEqual(item["score"], 50.0, places=2, msg=item["key"])
        self.assertEqual(result["total_score"], 50.0)
        self.assertAlmostEqual(factor(result, "cet1_ratio")["value"], 0.115)
        self.assertEqual(factor(result, "cet1_ratio")["display_value"], "11.5%")

    def test_fi_single_factor_by_hand(self):
        # CET1 16% -> 100 on a 15-point weight: total rises by 15 * 50 / 100 = 7.5.
        result = score_counterparty("financial_institution", "Bank", "IN", dict(MID_FI, cet1_capital=80), qual(3))
        self.assertEqual(factor(result, "cet1_ratio")["score"], 100.0)
        self.assertEqual(result["total_score"], 57.5)
        self.assertEqual(result["grade"], "IR5")
        self.assertEqual(len(result["strengths"]), 1)

    def test_fund_midpoint_scores_50(self):
        result = score_counterparty("fund", "Mid Fund", "KR", MID_FUND, qual(3))
        for item in result["factors"]:
            self.assertAlmostEqual(item["score"], 50.0, places=2, msg=item["key"])
        self.assertEqual(result["total_score"], 50.0)
        # IR6 = 3% x 0.5 of NAV 1000
        self.assertEqual(result["limit"]["proposed_limit"], 15.0)
        self.assertEqual(result["limit"]["capital_base_label"], "Net asset value")

    def test_fund_leverage_concern(self):
        # Leverage 6x -> score 0 on a 15-point weight: total falls by 7.5 to 42.5 (IR7).
        result = score_counterparty("fund", "Levered Fund", "JP", dict(MID_FUND, gross_exposure=6000), qual(3))
        self.assertEqual(factor(result, "gross_leverage")["score"], 0.0)
        self.assertEqual(result["total_score"], 42.5)
        self.assertEqual(result["grade"], "IR7")
        self.assertTrue(result["concerns"][0].startswith("Gross leverage"))

    def test_validation(self):
        with self.assertRaises(ValueError):
            score_counterparty("sovereign", "X", "IN", MID_CORPORATE, qual(3))
        with self.assertRaises(ValueError):
            score_counterparty("corporate", "X", "US", MID_CORPORATE, qual(3))
        with self.assertRaises(ValueError):
            score_counterparty("corporate", " ", "IN", MID_CORPORATE, qual(3))
        missing = {k: v for k, v in MID_CORPORATE.items() if k != "capex"}
        with self.assertRaisesRegex(ValueError, "capex"):
            score_counterparty("corporate", "X", "IN", missing, qual(3))
        with self.assertRaisesRegex(ValueError, "revenue"):
            score_counterparty("corporate", "X", "IN", dict(MID_CORPORATE, revenue=0), qual(3))
        with self.assertRaisesRegex(ValueError, "negative"):
            score_counterparty("corporate", "X", "IN", dict(MID_CORPORATE, total_debt=-1), qual(3))
        with self.assertRaises(ValueError):
            score_counterparty("corporate", "X", "IN", MID_CORPORATE, dict(qual(3), country=0))
        with self.assertRaisesRegex(ValueError, "finite"):
            score_counterparty("corporate", "X", "IN", dict(MID_CORPORATE, cash=float("nan")), qual(3))


class PeerComparisonTests(unittest.TestCase):
    def setUp(self):
        self.peers = [
            {"name": "Strong Peer", "country": "JP", "sector": "Industrials",
             "financials": STRONG_CORPORATE, "qualitative": qual(5)},
            {"name": "Mid Peer", "country": "IN", "sector": "Utilities",
             "financials": MID_CORPORATE, "qualitative": qual(3)},
            {"name": "Lower Margin Peer", "country": "KR", "sector": "Industrials",
             "financials": dict(MID_CORPORATE, ebitda=122.5), "qualitative": qual(3)},
        ]

    def test_rank_and_metric_positions(self):
        subject = dict(MID_CORPORATE, ebitda=245)  # margin 24.5%, debt/EBITDA 2.5x
        result = score_counterparty("corporate", "Subject", "IN", subject, qual(3), sector="Industrials", peers=self.peers)
        peer = result["peer_comparison"]
        self.assertEqual(peer["peer_count"], 3)
        self.assertEqual(peer["same_sector_peers"], 2)
        # Peer scores: 100, 50 and below 50 -> median 50; subject is above 50 so ranks 2 of 4.
        self.assertEqual(peer["peer_median_score"], 50.0)
        self.assertEqual((peer["rank"], peer["rank_out_of"]), (2, 4))
        self.assertEqual(peer["peers"][0]["name"], "Strong Peer")

        margin = next(m for m in peer["metrics"] if m["key"] == "ebitda_margin")
        # Peer margins 30%, 17.5%, 12.25% -> median 17.5%; subject 24.5% beats two peers.
        self.assertAlmostEqual(margin["peer_median"], 0.175)
        self.assertEqual(margin["peers_outperformed"], 2)
        self.assertEqual(margin["position"], "stronger")

        leverage = next(m for m in peer["metrics"] if m["key"] == "debt_to_ebitda")
        # Peer debt/EBITDA 1.0x, 3.5x, 5.0x -> median 3.5x; subject 2.5x is lower, so stronger.
        self.assertAlmostEqual(leverage["peer_median"], 3.5)
        self.assertEqual(leverage["position"], "stronger")
        self.assertEqual(leverage["peers_outperformed"], 2)

        current = next(m for m in peer["metrics"] if m["key"] == "current_ratio")
        self.assertEqual(current["position"], "in line")

    def test_sample_peers_exclude_subject(self):
        for kind in COUNTERPARTY_TYPES:
            name = SAMPLE_COUNTERPARTIES[kind][0]["name"]
            peers = sample_peers(kind, name)
            self.assertEqual(len(peers), len(SAMPLE_COUNTERPARTIES[kind]) - 1)
            self.assertNotIn(name, [p["name"] for p in peers])

    def test_all_samples_score_and_are_labelled(self):
        countries = set()
        for kind in COUNTERPARTY_TYPES:
            for row in SAMPLE_COUNTERPARTIES[kind]:
                self.assertIn("(sample)", row["name"])
                self.assertTrue(row["name"].isascii())
                countries.add(row["country"])
                result = score_counterparty(kind, row["name"], row["country"], row["financials"],
                                            row["qualitative"], row["sector"], sample_peers(kind, row["name"]))
                self.assertTrue(0 <= result["total_score"] <= 100)
                self.assertEqual(result["peer_comparison"]["peer_count"], 4)
        self.assertEqual(countries, set(COUNTRIES))


class CreditReviewTests(unittest.TestCase):
    def test_sections_and_content(self):
        scorecard = score_counterparty("corporate", "Mid Co", "IN", MID_CORPORATE, qual(3), sector="Industrials")
        review = generate_credit_review(scorecard)
        self.assertEqual([s["title"] for s in review["sections"]], [
            "Summary and recommendation", "Business profile", "Financial analysis",
            "Peer and sector comparison", "Risks and mitigants", "Rating rationale",
            "Proposed limit and review frequency",
        ])
        body = {s["title"]: s["body"] for s in review["sections"]}
        self.assertIn("total score of 50.0 out of 100", body["Summary and recommendation"])
        self.assertIn("grade IR6", body["Summary and recommendation"])
        self.assertIn("2.50%", body["Summary and recommendation"])
        self.assertIn("domiciled in India", body["Summary and recommendation"])
        self.assertIn("3.50x (adequate)", body["Financial analysis"])
        self.assertIn("covers 10% of total debt", body["Financial analysis"])
        self.assertIn("No peer set was supplied", body["Peer and sector comparison"])
        self.assertIn("USD 18.4 mn", body["Proposed limit and review frequency"])
        self.assertIn("semi-annual", body["Proposed limit and review frequency"])
        self.assertTrue(review["text"].startswith("CREDIT REVIEW DRAFT: Mid Co"))
        self.assertEqual(review, generate_credit_review(scorecard))  # deterministic

    def test_review_for_each_sample_type(self):
        for kind in COUNTERPARTY_TYPES:
            row = SAMPLE_COUNTERPARTIES[kind][3]
            scorecard = score_counterparty(kind, row["name"], row["country"], row["financials"],
                                           row["qualitative"], row["sector"], sample_peers(kind, row["name"]))
            review = generate_credit_review(scorecard)
            self.assertEqual(len(review["sections"]), 7)
            self.assertIn("ranks", review["text"])
            self.assertTrue(review["text"].isascii())

    def test_no_limit_for_weakest_grades(self):
        weak = dict(MID_FUND, gross_exposure=6000, liquid_assets_7d=100, annualised_volatility=0.30,
                    max_drawdown=0.40, net_asset_value=100)
        scorecard = score_counterparty("fund", "Weak Fund", "CN", weak, qual(1))
        self.assertIn(scorecard["grade"], ("IR9", "IR10"))
        self.assertIn("No limit is proposed", generate_credit_review(scorecard)["text"])


class DueDiligenceTests(unittest.TestCase):
    def test_checklist_composition(self):
        for kind in COUNTERPARTY_TYPES:
            for country in COUNTRIES:
                checklist = due_diligence_checklist(kind, country)
                ids = [item["id"] for item in checklist["items"]]
                self.assertEqual(len(ids), len(set(ids)))
                self.assertTrue(any(i.startswith(country.lower() + "_") for i in ids))
                self.assertTrue(all(item["text"].isascii() for item in checklist["items"]))
        # 12 common + 3 corporate + 3 India items
        self.assertEqual(len(due_diligence_checklist("corporate", "IN")["items"]), 18)
        # 12 common + 5 fund + 3 Japan items
        self.assertEqual(len(due_diligence_checklist("fund", "JP")["items"]), 20)
        with self.assertRaises(ValueError):
            due_diligence_checklist("corporate", "US")

    def test_readiness_states(self):
        items = due_diligence_checklist("corporate", "IN")["items"]
        empty = assess_due_diligence("corporate", "IN", {})
        self.assertEqual(empty["status"], "incomplete")
        self.assertEqual(empty["completeness_pct"], 0.0)
        self.assertEqual(len(empty["mandatory_outstanding"]), empty["mandatory_total"])

        mandatory_done = {item["id"]: "complete" for item in items if item["mandatory"]}
        ready = assess_due_diligence("corporate", "IN", mandatory_done)
        self.assertEqual(ready["status"], "ready")
        # 14 of 18 items are mandatory -> 77.8% complete
        self.assertEqual(ready["mandatory_total"], 14)
        self.assertEqual(ready["completeness_pct"], 77.8)

        blocked = assess_due_diligence("corporate", "IN", dict(mandatory_done, site_visit="issue"))
        self.assertEqual(blocked["status"], "blocked")
        self.assertEqual(blocked["issues"], ["site_visit"])

        waived = assess_due_diligence("corporate", "IN", dict(mandatory_done, ownership="not_applicable"))
        self.assertEqual(waived["status"], "incomplete")
        self.assertEqual(waived["mandatory_outstanding"], ["ownership"])

    def test_rejects_unknown_items_and_states(self):
        with self.assertRaisesRegex(ValueError, "unknown"):
            assess_due_diligence("fund", "KR", {"in_fx": "complete"})
        with self.assertRaisesRegex(ValueError, "state"):
            assess_due_diligence("fund", "KR", {"ownership": "done"})


class MethodologyTests(unittest.TestCase):
    def test_methodology_shape(self):
        doc = methodology()
        self.assertEqual(set(doc["scorecards"]), set(COUNTERPARTY_TYPES))
        self.assertEqual(len(doc["rating_scale"]), 10)
        self.assertEqual(doc["rating_scale"][1]["max_score"], 90.0)
        self.assertIn("not a regulatory calculation", doc["disclaimer"])
        self.assertEqual(len(doc["scorecards"]["fund"]["inputs"]), 8)


if __name__ == "__main__":
    unittest.main()
