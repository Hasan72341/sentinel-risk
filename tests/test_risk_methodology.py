import math
import unittest

import numpy as np
from scipy import stats

from app.services.risk_methodology import (
    RISK_FACTORS, SAMPLE_POSITIONS, backtest_sample, backtest_var, basel_traffic_light,
    christoffersen_conditional_coverage, christoffersen_independence,
    expected_shortfall_summary, historical_var_es, kupiec_pof, liquidity_horizon_es,
    parametric_var_es, rolling_var, sample_portfolio, transition_counts,
)
from app.services.risk_methodology_monitoring import (
    assess_status, clustering_metrics, exception_drivers, model_performance_report,
    sample_model_performance_report, stability_metrics,
)
from app.services.risk_methodology_stress import (
    SCENARIO_LIBRARY, apply_scenario, diversification_benefit, reverse_stress_test,
    run_stress_test, simulate_economic_capital, unexpected_loss,
)


class VarAndExpectedShortfallTests(unittest.TestCase):
    def test_historical_var_and_es_by_hand(self):
        # 10% quantile of -5..4 sits at position 0.9: -5 + 0.9 = -4.1.
        # Only -5 lies at or beyond it, so ES = 5.
        var, es = historical_var_es([-5, -4, -3, -2, -1, 0, 1, 2, 3, 4], 0.9)
        self.assertAlmostEqual(var, 4.1)
        self.assertAlmostEqual(es, 5.0)

    def test_historical_es_averages_the_tail(self):
        # 101 points -50..50; the 5% quantile is exactly -45.
        # Tail is -50..-45, whose mean is -47.5.
        var, es = historical_var_es(range(-50, 51), 0.95)
        self.assertAlmostEqual(var, 45.0)
        self.assertAlmostEqual(es, 47.5)

    def test_parametric_var_and_es_by_hand(self):
        # mean 0, sample sd = sqrt(10 / 4) = 1.5811388
        # z(1%) = -2.3263479, so VaR = 2.3263479 * 1.5811388 = 3.678279
        # ES = sd * pdf(z) / 0.01 = 1.5811388 * 0.0266521 / 0.01 = 4.214068
        var, es = parametric_var_es([-2, -1, 0, 1, 2], 0.99)
        self.assertAlmostEqual(var, 3.678279, places=5)
        self.assertAlmostEqual(es, 4.214068, places=4)

    def test_parametric_var_includes_the_mean(self):
        var, _ = parametric_var_es([-1, 0, 1, 2, 3], 0.99)  # same sd, mean 1
        self.assertAlmostEqual(var, 3.678279 - 1, places=5)

    def test_rolling_var_uses_only_prior_observations(self):
        pnl = [-5, -4, -3, -2, -1, 0, 1, 2, 3, 4, -100, 7]
        var = rolling_var(pnl, 0.9, 10, "historical")
        self.assertEqual(len(var), 2)
        self.assertAlmostEqual(var[0], 4.1)  # day 10 (-100) is not in its own window
        # Window for day 11 is -4..4 plus -100: sorted -100, -4, ...; 0.9 of the way to -4.
        self.assertAlmostEqual(var[1], 100 - 0.9 * 96)

    def test_rolling_var_rejects_short_series_and_bad_method(self):
        with self.assertRaises(ValueError):
            rolling_var([1, 2, 3], 0.99, 3)
        with self.assertRaises(ValueError):
            rolling_var([1, 2, 3, 4], 0.99, 3, "monte_carlo")
        with self.assertRaises(ValueError):
            rolling_var([1, 2, 3, 4], 1.0, 3)

    def test_liquidity_horizon_cascade_by_hand(self):
        # sqrt(100^2 * 10/10 + 60^2 * (20-10)/10 + 30^2 * (40-20)/10)
        # = sqrt(10000 + 3600 + 1800) = sqrt(15400)
        self.assertAlmostEqual(liquidity_horizon_es({10: 100, 20: 60, 40: 30}), math.sqrt(15400))
        self.assertAlmostEqual(liquidity_horizon_es({10: 100}), 100)
        with self.assertRaises(ValueError):
            liquidity_horizon_es({20: 60})

    def test_expected_shortfall_summary_scales_and_buckets(self):
        equity = list(range(-50, 51))                 # horizon 10
        credit = [value / 2 for value in range(-50, 51)]  # horizon 40
        pnl = [a + b for a, b in zip(equity, credit)]
        summary = expected_shortfall_summary(pnl, {"EQ_NIFTY50": equity, "CS_IN": credit}, 0.95)
        # Total is 1.5x the equity series: ES 71.25; credit alone: ES 23.75.
        self.assertAlmostEqual(summary["es_1d"], 71.25)
        self.assertAlmostEqual(summary["es_base_horizon"], round(71.25 * math.sqrt(10), 2))
        self.assertEqual([bucket["liquidity_horizon_days"] for bucket in summary["buckets"]], [10, 40])
        expected = math.sqrt(10) * math.sqrt(71.25**2 + 23.75**2 * (40 - 10) / 10)
        self.assertAlmostEqual(summary["liquidity_adjusted_es"], expected, places=1)
        self.assertIn("Simplified FRTB-style", summary["note"])

    def test_expected_shortfall_summary_without_factors(self):
        summary = expected_shortfall_summary(list(range(-50, 51)), None, 0.95)
        self.assertIsNone(summary["liquidity_adjusted_es"])
        self.assertEqual(summary["buckets"], [])


class CoverageTestTests(unittest.TestCase):
    def test_kupiec_by_hand(self):
        # T = 250, x = 5, p = 1%:
        # ln L0 = 245 ln(0.99) + 5 ln(0.01) = -2.462332 - 23.025851 = -25.488183
        # ln L1 = 245 ln(0.98) + 5 ln(0.02) = -4.949663 - 19.560115 = -24.509778
        # LR = -2 (ln L0 - ln L1) = 1.956810
        result = kupiec_pof(250, 5, 0.01)
        self.assertAlmostEqual(result["statistic"], 1.956810, places=5)
        self.assertAlmostEqual(result["p_value"], 0.161855, places=5)
        self.assertAlmostEqual(result["observed_rate"], 0.02)

    def test_kupiec_is_zero_when_rate_matches(self):
        result = kupiec_pof(500, 5, 0.01)
        self.assertAlmostEqual(result["statistic"], 0.0)
        self.assertAlmostEqual(result["p_value"], 1.0)

    def test_kupiec_with_no_exceptions(self):
        # Only the (1-p)^T term remains: LR = -2 * 250 * ln(0.99) = 5.025168
        result = kupiec_pof(250, 0, 0.01)
        self.assertAlmostEqual(result["statistic"], 5.025168, places=5)
        self.assertAlmostEqual(result["p_value"], 0.024983, places=5)

    def test_kupiec_matches_chi_square_tail(self):
        result = kupiec_pof(250, 10, 0.01)
        expected = -2 * (240 * math.log(0.99) + 10 * math.log(0.01)) + 2 * (240 * math.log(0.96) + 10 * math.log(0.04))
        self.assertAlmostEqual(result["statistic"], expected)
        self.assertAlmostEqual(result["p_value"], stats.chi2.sf(expected, 1))

    def test_kupiec_rejects_bad_input(self):
        for args in ((0, 0, 0.01), (10, 11, 0.01), (10, 1, 0.0), (10, 1, 1.0)):
            with self.assertRaises(ValueError):
                kupiec_pof(*args)

    def test_transition_counts(self):
        self.assertEqual(
            transition_counts([0, 0, 1, 1, 0, 0, 0, 1, 0, 0]),
            {"n00": 4, "n01": 2, "n10": 2, "n11": 1},
        )

    def test_independence_is_zero_when_transition_rates_are_equal(self):
        # n00=4, n01=2, n10=2, n11=1: pi01 = 2/6 = pi11 = 1/3 = pi, so LR = 0.
        result = christoffersen_independence([0, 0, 1, 1, 0, 0, 0, 1, 0, 0])
        self.assertAlmostEqual(result["pi01"], 1 / 3)
        self.assertAlmostEqual(result["pi11"], 1 / 3)
        self.assertAlmostEqual(result["statistic"], 0.0)
        self.assertAlmostEqual(result["p_value"], 1.0)

    def test_independence_by_hand_for_clustered_exceptions(self):
        # Hits at positions 2, 3, 4 of 12: n00=7, n01=1, n10=1, n11=2.
        # pi = 3/11, pi01 = 1/8, pi11 = 2/3
        # ln L0 = 8 ln(8/11) + 3 ln(3/11)            = -6.445479
        # ln L1 = 7 ln(7/8) + ln(1/8) + ln(1/3) + 2 ln(2/3) = -4.923704
        # LR = -2 (ln L0 - ln L1) = 3.043550
        hits = [0, 0, 1, 1, 1, 0, 0, 0, 0, 0, 0, 0]
        result = christoffersen_independence(hits)
        self.assertEqual((result["n00"], result["n01"], result["n10"], result["n11"]), (7, 1, 1, 2))
        self.assertAlmostEqual(result["pi01"], 0.125)
        self.assertAlmostEqual(result["pi11"], 2 / 3)
        ln_l0 = 8 * math.log(8 / 11) + 3 * math.log(3 / 11)
        ln_l1 = 7 * math.log(7 / 8) + math.log(1 / 8) + math.log(1 / 3) + 2 * math.log(2 / 3)
        self.assertAlmostEqual(result["statistic"], -2 * (ln_l0 - ln_l1))
        self.assertAlmostEqual(result["statistic"], 3.043550, places=5)
        self.assertAlmostEqual(result["p_value"], 0.081055, places=4)

    def test_independence_with_no_exceptions(self):
        result = christoffersen_independence([0] * 50)
        self.assertEqual(result["statistic"], 0.0)
        self.assertEqual(result["p_value"], 1.0)

    def test_conditional_coverage_is_the_sum_with_two_degrees_of_freedom(self):
        hits = [0, 0, 1, 1, 1, 0, 0, 0, 0, 0, 0, 0]
        pof = kupiec_pof(12, 3, 0.05)
        independence = christoffersen_independence(hits)
        result = christoffersen_conditional_coverage(hits, 0.05)
        self.assertAlmostEqual(result["statistic"], pof["statistic"] + independence["statistic"])
        # For chi-square(2) the tail probability is exp(-LR / 2).
        self.assertAlmostEqual(result["p_value"], math.exp(-result["statistic"] / 2))

    def test_basel_traffic_light_boundaries(self):
        zones = [basel_traffic_light(count)["zone"] for count in range(12)]
        self.assertEqual(zones, ["green"] * 5 + ["yellow"] * 5 + ["red"] * 2)

    def test_basel_plus_factors(self):
        expected = {4: 0.0, 5: 0.40, 6: 0.50, 7: 0.65, 8: 0.75, 9: 0.85, 10: 1.0}
        for count, factor in expected.items():
            self.assertEqual(basel_traffic_light(count)["plus_factor"], factor)

    def test_basel_non_standard_setting_has_no_plus_factor(self):
        result = basel_traffic_light(3, 100, 0.99)
        # P(X <= 3) for Binomial(100, 1%) = 0.98163, which is in the yellow band.
        self.assertAlmostEqual(result["cumulative_probability"], 0.98163, places=4)
        self.assertEqual(result["zone"], "yellow")
        self.assertIsNone(result["plus_factor"])
        self.assertFalse(result["standard_setting"])


class BacktestTests(unittest.TestCase):
    def setUp(self):
        # Ten quiet days then a large loss, a gain and a small loss.
        self.pnl = [-5, -4, -3, -2, -1, 0, 1, 2, 3, 4, -100, 7, -6]
        self.dates = [f"2025-01-{day:02d}" for day in range(1, 14)]

    def test_exceptions_are_listed_with_sizes(self):
        result = backtest_var(self.pnl, self.dates, confidence=0.9, window=10)
        self.assertEqual(result["n_obs"], 3)
        self.assertEqual(result["n_exceptions"], 1)
        self.assertAlmostEqual(result["expected_exceptions"], 0.3)
        self.assertEqual([row["exception"] for row in result["series"]], [True, False, False])
        exception = result["exceptions"][0]
        self.assertEqual(exception["date"], "2025-01-11")
        self.assertEqual(exception["pnl"], -100)
        self.assertAlmostEqual(exception["var"], 4.1)
        self.assertAlmostEqual(exception["excess"], 95.9)
        self.assertAlmostEqual(exception["loss_to_var"], round(100 / 4.1, 4))
        self.assertEqual(result["kupiec"]["statistic"], kupiec_pof(3, 1, 1 - 0.9)["statistic"])

    def test_loss_equal_to_var_is_not_an_exception(self):
        pnl = [-5, -4, -3, -2, -1, 0, 1, 2, 3, 4, -4.1]
        result = backtest_var(pnl, confidence=0.9, window=10)
        self.assertEqual(result["n_exceptions"], 0)
        self.assertEqual(result["series"][0]["date"], "Day 11")

    def test_validation(self):
        with self.assertRaises(ValueError):
            backtest_var(self.pnl, self.dates[:-1], window=10)
        with self.assertRaises(ValueError):
            backtest_var([1.0, float("nan"), 2.0, 3.0], window=2)
        with self.assertRaises(ValueError):
            backtest_var(self.pnl, window=10, factor_pnl={"EQ_NIFTY50": [1.0]})

    def test_sample_portfolio_is_deterministic_and_consistent(self):
        first, second = sample_portfolio(42, 300), sample_portfolio(42, 300)
        self.assertEqual(first["pnl"], second["pnl"])
        self.assertNotEqual(first["pnl"], sample_portfolio(43, 300)["pnl"])
        self.assertEqual(len(first["dates"]), 300)
        self.assertEqual(first["dates"][-1], "2025-12-31")
        self.assertEqual(len(first["factor_pnl"]), len(RISK_FACTORS))
        self.assertEqual([p["factor_id"] for p in SAMPLE_POSITIONS], [f["id"] for f in RISK_FACTORS])
        for day in (0, 150, 299):
            total = sum(series[day] for series in first["factor_pnl"].values())
            self.assertAlmostEqual(first["pnl"][day], total, delta=0.1)
        self.assertIn("not market data", first["disclaimer"])

    def test_sample_backtest_is_internally_consistent(self):
        for method in ("historical", "parametric"):
            result = backtest_sample(method=method)
            self.assertEqual(result["n_obs"], 500)
            self.assertEqual(result["n_exceptions"], len(result["exceptions"]))
            self.assertEqual(result["n_exceptions"], sum(row["exception"] for row in result["series"]))
            for row in result["exceptions"]:
                self.assertLess(row["pnl"], -row["var"])
            self.assertEqual(result["traffic_light"]["n_obs"], 250)
            self.assertEqual(
                result["traffic_light"]["n_exceptions"],
                sum(row["exception"] for row in result["series"][-250:]),
            )
            shortfall = result["expected_shortfall"]
            self.assertGreater(shortfall["es_1d"], shortfall["var_1d"])
            self.assertGreaterEqual(shortfall["liquidity_adjusted_es"], shortfall["es_base_horizon"])


class StressTests(unittest.TestCase):
    positions = [
        {"factor_id": "EQ_NIFTY50", "sensitivity": 100_000},   # per +1%
        {"factor_id": "IR_JPY", "sensitivity": -20_000},       # per +1bp
        {"factor_id": "FX_KRW", "sensitivity": 50_000},        # per +1%
    ]

    def test_scenario_pnl_by_hand(self):
        shocks = {"EQ_NIFTY50": -10, "IR_JPY": 25, "FX_KRW": -4, "CS_CN": 100}
        result = apply_scenario(self.positions, shocks)
        # -1,000,000 equity, -500,000 rates, -200,000 FX; no China credit position.
        self.assertEqual(result["total_pnl"], -1_700_000)
        self.assertEqual(result["by_risk_type"], {"equity": -1_000_000, "rates": -500_000, "credit": 0, "fx": -200_000})
        self.assertEqual(result["by_market"], {"India": -1_000_000, "China": 0, "Japan": -500_000, "South Korea": -200_000})
        self.assertEqual({row["factor_id"]: row["pnl"] for row in result["by_factor"]},
                         {"EQ_NIFTY50": -1_000_000, "IR_JPY": -500_000, "CS_CN": 0, "FX_KRW": -200_000})

    def test_unknown_factor_is_rejected(self):
        with self.assertRaises(ValueError):
            apply_scenario(self.positions, {"EQ_SP500": -10})
        with self.assertRaises(ValueError):
            apply_scenario([{"factor_id": "EQ_SP500", "sensitivity": 1}], {"EQ_NIFTY50": -10})

    def test_worst_scenario_and_custom_scenarios(self):
        custom = [
            {"name": "Mild", "shocks": {"EQ_NIFTY50": -1}},
            {"name": "Severe", "shocks": {"EQ_NIFTY50": -30, "FX_KRW": -10}},
            {"name": "Rally", "shocks": {"EQ_NIFTY50": 5}},
        ]
        result = run_stress_test(self.positions, [], custom)
        self.assertEqual([row["total_pnl"] for row in result["results"]], [-100_000, -3_500_000, 500_000])
        self.assertEqual(result["worst_scenario"], {"id": "custom_2", "name": "Severe", "total_pnl": -3_500_000})
        self.assertFalse(result["using_sample_portfolio"])

    def test_library_runs_on_sample_portfolio(self):
        result = run_stress_test()
        self.assertEqual(len(result["results"]), len(SCENARIO_LIBRARY))
        self.assertTrue(result["using_sample_portfolio"])
        self.assertIn("illustrative", result["disclaimer"])
        for row in result["results"]:
            self.assertAlmostEqual(sum(row["by_risk_type"].values()), row["total_pnl"], places=2)
            self.assertAlmostEqual(sum(row["by_market"].values()), row["total_pnl"], places=2)
        self.assertEqual(result["worst_scenario"]["total_pnl"], min(row["total_pnl"] for row in result["results"]))
        with self.assertRaises(ValueError):
            run_stress_test(None, ["not_a_scenario"])

    def test_reverse_stress_by_hand(self):
        # 1x loss is 1,700,000, so a 5,100,000 loss needs exactly 3x.
        shocks = {"EQ_NIFTY50": -10, "IR_JPY": 25, "FX_KRW": -4}
        result = reverse_stress_test(self.positions, shocks, 5_100_000)
        self.assertTrue(result["reachable"])
        self.assertAlmostEqual(result["multiplier"], 3.0)
        self.assertEqual(result["scaled_shocks"], {"EQ_NIFTY50": -30, "IR_JPY": 75, "FX_KRW": -12})
        self.assertAlmostEqual(result["scaled"]["total_pnl"], -5_100_000)

    def test_reverse_stress_unreachable_for_profitable_scenario(self):
        result = reverse_stress_test(self.positions, {"EQ_NIFTY50": 10}, 1_000_000)
        self.assertFalse(result["reachable"])
        self.assertIsNone(result["multiplier"])
        with self.assertRaises(ValueError):
            reverse_stress_test(self.positions, {"EQ_NIFTY50": -10}, 0)


class EconomicCapitalTests(unittest.TestCase):
    def test_unexpected_loss_by_hand(self):
        # Losses 0..100: mean 50, 99% quantile 99, unexpected loss 49.
        result = unexpected_loss(range(101), 0.99)
        self.assertAlmostEqual(result["expected_loss"], 50)
        self.assertAlmostEqual(result["loss_quantile"], 99)
        self.assertAlmostEqual(result["unexpected_loss"], 49)

    def test_diversification_benefit_by_hand(self):
        result = diversification_benefit({"market": 60, "credit": 30, "operational": 10}, 80)
        self.assertEqual(result["undiversified"], 100)
        self.assertEqual(result["benefit"], 20)
        self.assertEqual(result["benefit_pct"], 20)

    def test_market_only_capital_matches_normal_quantile(self):
        result = simulate_economic_capital(
            market_annual_vol=1_000_000, credit_exposures=[], operational_expected_loss=0,
            confidence=0.99, simulations=200_000, seed=1,
        )
        # Normal loss: UL = z(99%) * sd = 2.3263 * 1,000,000.
        self.assertAlmostEqual(result["economic_capital"] / 2_326_348, 1.0, delta=0.02)
        self.assertAlmostEqual(result["diversification"]["benefit"], 0.0, delta=1.0)

    def test_credit_expected_loss_matches_pd_times_lgd_times_ead(self):
        exposures = [{"name": f"Name {i}", "ead": 1_000_000, "pd": 0.05, "lgd": 0.4} for i in range(20)]
        result = simulate_economic_capital(
            market_annual_vol=0, credit_exposures=exposures, operational_expected_loss=0,
            simulations=100_000, seed=3,
        )
        credit = next(row for row in result["breakdown"] if row["risk_type"] == "credit")
        self.assertAlmostEqual(credit["expected_loss"] / (20 * 1_000_000 * 0.05 * 0.4), 1.0, delta=0.03)

    def test_sample_run_is_deterministic_with_a_diversification_benefit(self):
        first = simulate_economic_capital(simulations=20_000)
        second = simulate_economic_capital(simulations=20_000)
        self.assertEqual(first["economic_capital"], second["economic_capital"])
        self.assertEqual([row["risk_type"] for row in first["breakdown"]], ["market", "credit", "operational"])
        standalone = sum(row["unexpected_loss"] for row in first["breakdown"])
        self.assertAlmostEqual(first["diversification"]["undiversified"], standalone, delta=0.05)
        self.assertGreater(first["diversification"]["benefit"], 0)
        self.assertAlmostEqual(
            sum(row["allocated_capital"] for row in first["breakdown"]), first["economic_capital"], delta=0.05
        )
        self.assertEqual(sum(bin_["count"] for bin_ in first["histogram"]), 20_000)
        self.assertTrue(first["inputs"]["using_sample_exposures"])

    def test_validation(self):
        with self.assertRaises(ValueError):
            simulate_economic_capital(correlations={"market_credit": 1.5})
        with self.assertRaises(ValueError):
            simulate_economic_capital(asset_correlation=1.0)
        with self.assertRaises(ValueError):
            simulate_economic_capital(simulations=10)


class MonitoringTests(unittest.TestCase):
    def test_clustering_metrics_by_hand(self):
        hits = [0, 1, 1, 0, 0, 0, 1, 0, 0, 0, 0, 0, 0, 0, 0, 0, 1]
        result = clustering_metrics(hits, cluster_window=10)
        # Exceptions at 1, 2, 6, 16: gaps 1, 4, 10.
        self.assertEqual(result["consecutive_pairs"], 1)
        self.assertEqual(result["max_in_window"], 3)
        self.assertAlmostEqual(result["mean_gap_days"], 5.0)
        self.assertEqual(result["min_gap_days"], 1)

    def test_clustering_metrics_without_exceptions(self):
        result = clustering_metrics([0] * 20)
        self.assertEqual(result["max_in_window"], 0)
        self.assertIsNone(result["mean_gap_days"])

    def test_exception_drivers_rank_losses(self):
        drivers = exception_drivers({"EQ_NIFTY50": -60, "FX_JPY": -30, "IR_INR": 10, "CS_KR": -20}, top=2)
        self.assertEqual([row["factor_id"] for row in drivers], ["EQ_NIFTY50", "FX_JPY"])
        self.assertEqual(drivers[0]["risk_type"], "equity")
        self.assertEqual(drivers[0]["market"], "India")
        self.assertEqual(drivers[0]["share_of_loss_pct"], 60.0)  # -60 of a net -100
        self.assertEqual(drivers[1]["share_of_loss_pct"], 30.0)

    def test_stability_metrics_by_hand(self):
        series = [
            {"date": f"D{i}", "var": var, "exception": hit}
            for i, (var, hit) in enumerate([(10, False), (10, True), (20, False), (20, False)])
        ]
        result = stability_metrics(series, periods=2)
        self.assertEqual((result["mean_var"], result["min_var"], result["max_var"]), (15, 10, 20))
        self.assertAlmostEqual(result["var_coefficient_of_variation"], 5 / 15)
        self.assertAlmostEqual(result["max_daily_var_change_pct"], 100.0)
        self.assertEqual([p["n_exceptions"] for p in result["sub_periods"]], [1, 0])
        self.assertEqual([p["exception_rate"] for p in result["sub_periods"]], [0.5, 0.0])
        self.assertEqual((result["sub_periods"][1]["start"], result["sub_periods"][1]["end"]), ("D2", "D3"))

    @staticmethod
    def _backtest(n_exceptions, zone, kupiec_p, independence_p=0.5, conditional_p=0.5, expected=2.5):
        return {
            "n_exceptions": n_exceptions, "expected_exceptions": expected,
            "traffic_light": {"zone": zone}, "kupiec": {"p_value": kupiec_p},
            "independence": {"p_value": independence_p}, "conditional_coverage": {"p_value": conditional_p},
        }

    def test_status_rules(self):
        self.assertEqual(assess_status(self._backtest(2, "green", 0.7))[0], "green")
        self.assertEqual(assess_status(self._backtest(6, "yellow", 0.06))[0], "amber")
        self.assertEqual(assess_status(self._backtest(3, "green", 0.7, independence_p=0.01))[0], "amber")
        self.assertEqual(assess_status(self._backtest(3, "green", 0.7, conditional_p=0.03))[0], "amber")
        self.assertEqual(assess_status(self._backtest(12, "red", 0.0001))[0], "red")
        self.assertEqual(assess_status(self._backtest(9, "yellow", 0.005))[0], "red")
        # Too few exceptions is a conservative model: review it, do not fail it.
        status, reasons = assess_status(self._backtest(0, "green", 0.005, expected=5))
        self.assertEqual(status, "amber")
        self.assertIn("too few", reasons[0])

    def test_report_on_constructed_series(self):
        quiet = [1.0, -1.0] * 130          # 260 days of +/-1
        pnl = quiet[:]
        factor = {"EQ_KOSPI": [0.0] * 260, "FX_KRW": quiet[:]}
        for day in (100, 101, 102, 180):   # four large losses, three in a row
            pnl[day] = -50.0
            factor["EQ_KOSPI"][day] = -45.0
            factor["FX_KRW"][day] = -5.0
        report = model_performance_report(pnl, None, 0.99, 50, "historical", factor)
        summary = report["summary"]
        self.assertEqual(summary["n_obs"], 210)
        # Index 100 breaches a VaR of 1. Index 101 breaches too: one -50 in the window
        # puts the 1% quantile at -50 + 0.49 * 49 = -25.99. By index 102 the window
        # holds two -50 values, the quantile is -50 and a loss of 50 is not a breach.
        self.assertEqual([row["date"] for row in report["exceptions"]], ["Day 101", "Day 102", "Day 181"])
        self.assertAlmostEqual(report["exceptions"][1]["var"], 25.99)
        self.assertEqual(report["clustering"]["consecutive_pairs"], 1)
        self.assertEqual(report["clustering"]["max_in_window"], 2)
        self.assertEqual(report["largest_breaches"][0]["date"], "Day 101")
        self.assertAlmostEqual(report["largest_breaches"][0]["excess"], 49.0)
        first = report["exceptions"][0]["drivers"]
        self.assertEqual(first[0]["factor_id"], "EQ_KOSPI")
        self.assertEqual(first[0]["share_of_loss_pct"], 90.0)
        self.assertEqual(report["drivers"]["top_risk_type_counts"], {"equity": 3})
        self.assertLess(summary["independence"]["p_value"], 0.05)
        self.assertIn(report["status"], ("amber", "red"))
        self.assertTrue(any("clustered" in reason for reason in report["status_reasons"]))
        self.assertTrue(report["findings"][-1].startswith(f"Overall status is {report['status']}."))

    def test_sample_report(self):
        report = sample_model_performance_report()
        self.assertIn(report["status"], ("green", "amber", "red"))
        self.assertGreaterEqual(len(report["findings"]), 6)
        self.assertEqual(len(report["exceptions"]), report["summary"]["n_exceptions"])
        self.assertEqual(len(report["stability"]["sub_periods"]), 4)
        self.assertEqual(sum(p["n_exceptions"] for p in report["stability"]["sub_periods"]), report["summary"]["n_exceptions"])
        for exception in report["exceptions"]:
            self.assertTrue(exception["drivers"])
        self.assertIn("not market data", report["portfolio"]["disclaimer"])
        for text in report["findings"]:
            self.assertTrue(text.isascii())


class RouterTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from fastapi import FastAPI
        from fastapi.testclient import TestClient

        from app.routers import risk_methodology

        app = FastAPI()
        app.include_router(risk_methodology.router, prefix="/api/v1/risk-methodology")
        cls.client = TestClient(app)
        cls.base = "/api/v1/risk-methodology"

    def test_backtest_defaults_to_sample(self):
        response = self.client.post(f"{self.base}/var-backtest", json={"method": "parametric"})
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["method"], "parametric")
        self.assertIn("portfolio", body)

    def test_backtest_with_own_series_and_errors(self):
        pnl = [-5, -4, -3, -2, -1, 0, 1, 2, 3, 4, -100, 7, -6]
        response = self.client.post(f"{self.base}/var-backtest", json={"pnl": pnl, "confidence": 0.9, "window": 10})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["n_exceptions"], 1)
        response = self.client.post(f"{self.base}/var-backtest", json={"pnl": pnl, "window": 50})
        self.assertEqual(response.status_code, 422)
        response = self.client.post(f"{self.base}/var-backtest", json={"method": "monte_carlo"})
        self.assertEqual(response.status_code, 422)

    def test_monitoring_stress_and_capital_endpoints(self):
        self.assertEqual(self.client.post(f"{self.base}/model-monitoring", json={}).status_code, 200)
        self.assertEqual(self.client.get(f"{self.base}/sample-portfolio", params={"days": 100}).status_code, 200)
        library = self.client.get(f"{self.base}/stress/scenarios").json()
        self.assertEqual(len(library["factors"]), 16)
        self.assertTrue(all(scenario["illustrative"] for scenario in library["scenarios"]))
        run = self.client.post(f"{self.base}/stress/run", json={
            "scenario_ids": ["rates_up_100"],
            "custom_scenarios": [{"name": "Nikkei -10%", "shocks": {"EQ_NIKKEI225": -10}}],
        }).json()
        self.assertEqual([row["id"] for row in run["results"]], ["rates_up_100", "custom_1"])
        self.assertEqual(run["results"][1]["total_pnl"], -3_000_000)  # 300,000 per 1% x -10%
        reverse = self.client.post(f"{self.base}/stress/reverse", json={
            "shocks": {"EQ_NIKKEI225": -10}, "loss_threshold": 6_000_000,
        }).json()
        self.assertEqual(reverse["multiplier"], 2.0)
        self.assertEqual(self.client.post(f"{self.base}/stress/reverse", json={"loss_threshold": 1}).status_code, 422)
        self.assertEqual(self.client.post(f"{self.base}/stress/run", json={"scenario_ids": ["nope"]}).status_code, 422)
        capital = self.client.post(f"{self.base}/economic-capital", json={"simulations": 5000})
        self.assertEqual(capital.status_code, 200)
        self.assertEqual(len(capital.json()["breakdown"]), 3)


class EnglishOnlyTests(unittest.TestCase):
    def test_source_files_are_ascii(self):
        from pathlib import Path

        root = Path(__file__).resolve().parents[1] / "api" / "app"
        for path in [root / "routers" / "risk_methodology.py", *sorted((root / "services").glob("risk_methodology*.py"))]:
            self.assertTrue(path.read_text(encoding="utf-8").isascii(), path.name)


if __name__ == "__main__":
    unittest.main()
