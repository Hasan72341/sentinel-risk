import unittest
from math import exp, sqrt

import numpy as np
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.routers.margin_models import router
from app.services.margin_models import (
    PRODUCTS, analyze_market_data, backtest_im, bond_price, bs_delta, bs_price,
    calculate_im, calibration_comparison, estimate_volatility, historical_im,
    horizon_shocks, linear_sensitivity, parametric_im, risky_annuity,
    sample_series, scenario_pnl, simulate_pfe, stressed_window, swap_annuity,
)

# Daily returns of -10%, +10%, -10%, +10%.
ZIGZAG = [100, 90, 99, 89.1, 98.01]


class BuildingBlockTests(unittest.TestCase):
    def test_horizon_shocks(self):
        np.testing.assert_allclose(horizon_shocks([100, 110, 99], 1), [0.10, -0.10])
        np.testing.assert_allclose(horizon_shocks([100, 110, 99], 2), [-0.01])
        np.testing.assert_allclose(horizon_shocks([7.0, 7.1, 6.8], 1, relative=False), [0.1, -0.3])
        with self.assertRaisesRegex(ValueError, "positive"):
            horizon_shocks([100, 0, 99], 1)

    def test_black_scholes_reference_values(self):
        # Textbook case: S=100, K=100, T=1, r=5%, vol=20% -> call 10.4506, put 5.5735, delta 0.6368.
        self.assertAlmostEqual(float(bs_price(100, 100, 1, 0.05, 0.2, "call")), 10.4506, places=4)
        self.assertAlmostEqual(float(bs_price(100, 100, 1, 0.05, 0.2, "put")), 5.5735, places=4)
        self.assertAlmostEqual(bs_delta(100, 100, 1, 0.05, 0.2, "call"), 0.6368, places=4)
        self.assertAlmostEqual(bs_delta(100, 100, 1, 0.05, 0.2, "put"), -0.3632, places=4)
        # At expiry the price is intrinsic value.
        self.assertEqual(float(bs_price(120, 100, 0, 0.05, 0.2, "call")), 20.0)
        self.assertEqual(float(bs_price(120, 100, 0, 0.05, 0.2, "put")), 0.0)

    def test_bond_price_and_annuities(self):
        # 2-year 5% annual coupon at a 5% continuous yield: 0.05 e^-0.05 + 1.05 e^-0.10.
        self.assertAlmostEqual(float(bond_price(0.05, 0.0, 0.05, 2.0)), 0.05 * exp(-0.05) + 1.05 * exp(-0.10))
        # After the first coupon only the final cash flow is left, one year away.
        self.assertAlmostEqual(float(bond_price(0.05, 1.0, 0.05, 2.0)), 1.05 * exp(-0.05))
        self.assertEqual(float(bond_price(0.05, 2.0, 0.05, 2.0)), 0.0)
        # Annual 2-year annuity at 5%: e^-0.05 + e^-0.10 = 1.856067.
        self.assertAlmostEqual(float(swap_annuity(0.05, 0.0, 2.0, 1)), 1.856067, places=6)
        # Zero rates: two semi-annual payments of 0.5 each.
        self.assertAlmostEqual(float(swap_annuity(0.0, 0.0, 1.0, 2)), 1.0)
        # Spread 120bp, recovery 40% -> hazard 2%; plus r = 3% -> (1 - e^-0.25) / 0.05 = 4.423984.
        self.assertAlmostEqual(float(risky_annuity(0.012, 0.0, 5.0, 0.03, 0.4)), 4.423984, places=6)

    def test_volatility_estimators(self):
        # Sum of squares 4 over (n - 1) = 3.
        self.assertAlmostEqual(estimate_volatility([1, -1, 1, -1]), sqrt(4 / 3))
        # EWMA, lambda 0.5 on [2, 0]: weights 0.5 (older) and 1 (latest) -> sqrt(0.5 * 4 / 1.5).
        self.assertAlmostEqual(estimate_volatility([2, 0], "ewma", 0.5), sqrt(2 / 1.5))
        # A more recent shock carries more weight.
        self.assertGreater(estimate_volatility([0, 2], "ewma", 0.5), estimate_volatility([2, 0], "ewma", 0.5))

    def test_stressed_window_finds_most_volatile_run(self):
        self.assertEqual(stressed_window([0, 0, 0, 5, -5, 0, 0], 2), (3, 5))


class ScenarioPnlTests(unittest.TestCase):
    def test_linear_products(self):
        cases = [
            ({"product": "equity", "side": "long", "notional": 1000}, 0.10, 100.0),
            ({"product": "equity", "side": "short", "notional": 1000}, 0.10, -100.0),
            ({"product": "fx", "side": "long", "notional": 2000}, -0.05, -100.0),
            # +0.10 percentage points on a 5-year duration: 1,000,000 x 5 x 0.001.
            ({"product": "bond", "side": "long", "notional": 1_000_000, "duration": 5}, 0.10, -5000.0),
            ({"product": "bond", "side": "short", "notional": 1_000_000, "duration": 5}, 0.10, 5000.0),
            ({"product": "irs", "side": "pay_fixed", "notional": 1_000_000, "duration": 5}, 0.10, 5000.0),
            ({"product": "irs", "side": "receive_fixed", "notional": 1_000_000, "duration": 5}, 0.10, -5000.0),
            # +25bp on a risky duration of 4: 1,000,000 x 4 x 0.0025.
            ({"product": "cds", "side": "buy_protection", "notional": 1_000_000, "duration": 4}, 25, 10000.0),
            ({"product": "cds", "side": "sell_protection", "notional": 1_000_000, "duration": 4}, 25, -10000.0),
        ]
        for pos, shock, expected in cases:
            with self.subTest(pos=pos):
                self.assertAlmostEqual(float(scenario_pnl(pos, [shock], 100.0, 10)[0]), expected, places=6)

    def test_option_is_fully_revalued_with_time_decay(self):
        option = {"product": "equity_option", "side": "long", "notional": 10, "strike": 100,
                  "expiry_years": 1.0, "volatility": 0.2, "rate": 0.05, "option_type": "call"}
        pnl = scenario_pnl(option, [0.0, 0.10], 100.0, 126)   # half a year of decay
        today = 10.4506
        self.assertAlmostEqual(float(pnl[0]), 10 * (float(bs_price(100, 100, 0.5, 0.05, 0.2)) - today), places=3)
        self.assertAlmostEqual(float(pnl[1]), 10 * (float(bs_price(110, 100, 0.5, 0.05, 0.2)) - today), places=3)
        self.assertLess(pnl[0], 0)   # unchanged spot still loses time value
        # Delta-normal sensitivity: quantity x delta x spot = 10 x 0.6368 x 100.
        self.assertAlmostEqual(linear_sensitivity(option, 100.0), 636.83, places=2)

    def test_invalid_positions_rejected(self):
        with self.assertRaisesRegex(ValueError, "side"):
            scenario_pnl({"product": "irs", "side": "long", "notional": 1, "duration": 1}, [0.1], 1.0, 1)
        with self.assertRaisesRegex(ValueError, "duration"):
            scenario_pnl({"product": "bond", "notional": 1}, [0.1], 1.0, 1)
        with self.assertRaisesRegex(ValueError, "product"):
            scenario_pnl({"product": "commodity", "notional": 1}, [0.1], 1.0, 1)


class InitialMarginTests(unittest.TestCase):
    def test_historical_quantile(self):
        pnl = [-10, -5, 0, 5, 10]
        self.assertAlmostEqual(historical_im(pnl, 0.75), 5.0)   # 25th percentile is the second value
        self.assertAlmostEqual(historical_im(pnl, 0.90), 8.0)   # 10th percentile: -10 + 0.4 x 5
        self.assertEqual(historical_im([1, 2, 3], 0.99), 0.0)   # no losses -> floored at zero

    def test_parametric_formula(self):
        # z(97.5%) = 1.959964; 100 daily vol over 4 days -> 1.959964 x 100 x 2.
        self.assertAlmostEqual(parametric_im(100, 4, 0.975), 391.9928, places=3)

    def test_single_position_and_offsetting_portfolio(self):
        long = {"product": "equity", "side": "long", "notional": 1000, "series": ZIGZAG}
        short = {"product": "equity", "side": "short", "notional": 1000, "series": ZIGZAG}
        result = calculate_im([long, short], mpor_days=1, confidence=0.75)
        # Scenario P&L is [-100, 100, -100, 100]; the 25th percentile is -100.
        self.assertAlmostEqual(result["positions"][0]["historical_im"], 100.0)
        self.assertAlmostEqual(result["positions"][1]["historical_im"], 100.0)
        # Daily P&L std = sqrt(40000 / 3) = 115.47; x z(75%) 0.67449 = 77.88.
        self.assertAlmostEqual(result["positions"][0]["parametric_im"], 77.88, places=2)
        self.assertAlmostEqual(result["positions"][0]["worst_scenario_pnl"], -100.0)
        # Long and short the same series net to zero.
        self.assertEqual(result["portfolio"]["historical_im"], 0.0)
        self.assertEqual(result["portfolio"]["parametric_im"], 0.0)
        self.assertAlmostEqual(result["portfolio"]["historical_diversification_benefit"], 200.0)

    def test_lookback_restricts_history(self):
        # Calm history followed by a 2-day window: only the last two returns (-10%, +10%) are used.
        series = [100, 100, 100, 100, 90, 99]
        full = calculate_im([{"product": "equity", "notional": 1000, "series": series}], mpor_days=1, confidence=0.75)
        short = calculate_im([{"product": "equity", "notional": 1000, "series": series}], mpor_days=1, confidence=0.75, lookback=2)
        self.assertEqual(full["positions"][0]["scenarios"], 5)
        self.assertEqual(short["positions"][0]["scenarios"], 2)
        # Full: sorted P&L [-100, 0, 0, 0, 100], 25th percentile = 0 -> IM 0.
        self.assertAlmostEqual(full["positions"][0]["historical_im"], 0.0)
        # Two scenarios [-100, 100]: 25th percentile = -50.
        self.assertAlmostEqual(short["positions"][0]["historical_im"], 50.0)

    def test_longer_mpor_and_higher_confidence_raise_margin(self):
        series = sample_series("equity_index")["series"]
        pos = {"product": "equity", "notional": 1_000_000, "series": series}
        base = calculate_im([pos], 5, 0.95)["positions"][0]
        longer = calculate_im([pos], 10, 0.95)["positions"][0]
        stricter = calculate_im([pos], 5, 0.99)["positions"][0]
        self.assertAlmostEqual(longer["parametric_im"] / base["parametric_im"], sqrt(2), places=4)
        self.assertGreater(stricter["historical_im"], base["historical_im"])


class CalibrationTests(unittest.TestCase):
    def test_rows_and_stressed_period(self):
        # 6 calm daily moves of +/-1bp-equivalent, then 4 stressed moves of +/-5, then 4 calm ones.
        series = [100.0]
        for move in [1, -1, 1, -1, 1, -1, 5, -5, 5, -5, 1, -1, 1, -1]:
            series.append(series[-1] + move)
        position = {"product": "cds", "side": "sell_protection", "notional": 1_000_000, "duration": 4}
        result = calibration_comparison(position, series, mpor_days=1, confidence=0.975, lookbacks=[4], stress_window=4)
        rows = {row["calibration"]: row for row in result["rows"]}
        self.assertEqual(set(rows), {"lookback", "full", "ewma", "stressed"})
        # Sensitivity: -1,000,000 x 4 / 10,000 = -400 per bp.
        self.assertEqual(result["sensitivity"], -400.0)
        # Last 4 moves [1, -1, 1, -1]: vol sqrt(4/3) = 1.154701 bp.
        self.assertAlmostEqual(rows["lookback"]["daily_volatility"], 1.154701, places=6)
        self.assertAlmostEqual(rows["lookback"]["parametric_im"], round(1.959964 * 400 * sqrt(4 / 3), 2), places=1)
        # Stressed window is the +/-5 run (daily moves 6..9): vol sqrt(100/3) = 5.773503 bp.
        self.assertEqual((rows["stressed"]["start_index"], rows["stressed"]["end_index"]), (6, 10))
        self.assertAlmostEqual(rows["stressed"]["daily_volatility"], 5.773503, places=6)
        # Protection seller loses 400 x 5 = 2000 on each widening day in the stressed window.
        self.assertAlmostEqual(rows["stressed"]["historical_im"], 2000.0)
        self.assertAlmostEqual(rows["lookback"]["historical_im"], 400.0)
        self.assertGreater(rows["stressed"]["parametric_im"], rows["full"]["parametric_im"])
        self.assertGreater(rows["full"]["parametric_im"], rows["lookback"]["parametric_im"])
        self.assertIsNone(rows["ewma"]["historical_im"])


class BacktestTests(unittest.TestCase):
    # Long bond, notional 100, duration 1 -> P&L of -1 per +1 point of yield.
    BOND = {"product": "bond", "side": "long", "notional": 100, "duration": 1}
    # Yield changes +1, +1, +1, +1, +5, +1 -> P&L [-1, -1, -1, -1, -5, -1].
    YIELDS = [10, 11, 12, 13, 14, 19, 20]

    def test_exception_counting(self):
        result = backtest_im(self.BOND, self.YIELDS, mpor_days=1, confidence=0.75, lookback=3)
        # Day 3: IM 1, loss 1 (not an exception). Day 4: IM 1, loss 5 (exception, excess 4).
        # Day 5: window [-1, -1, -5], 25th percentile = -3 -> IM 3, loss 1.
        self.assertEqual(result["observations"], 3)
        self.assertEqual([p["im"] for p in result["points"]], [1.0, 1.0, 3.0])
        self.assertEqual([p["realised_pnl"] for p in result["points"]], [-1.0, -5.0, -1.0])
        self.assertEqual([p["exception"] for p in result["points"]], [False, True, False])
        self.assertEqual(result["exceptions"], 1)
        self.assertAlmostEqual(result["exception_rate"], 1 / 3, places=5)
        self.assertEqual(result["worst_excess_loss"], 4.0)
        self.assertAlmostEqual(result["expected_exceptions"], 0.75)
        self.assertIsNone(result["binomial_p_value"])

    def test_non_overlapping_reports_binomial_probability(self):
        result = backtest_im(self.BOND, self.YIELDS, mpor_days=1, confidence=0.75, lookback=3, non_overlapping=True)
        # P(X >= 1) with n = 3, p = 0.25 is 1 - 0.75^3 = 0.578125.
        self.assertAlmostEqual(result["binomial_p_value"], 0.578125)

    def test_parametric_method_and_short_series(self):
        result = backtest_im(self.BOND, self.YIELDS, mpor_days=1, confidence=0.75, lookback=3, method="parametric")
        # Day 3 and 4 windows have zero volatility -> IM 0 -> every loss is an exception.
        self.assertEqual([p["im"] for p in result["points"]][:2], [0.0, 0.0])
        self.assertEqual([p["exception"] for p in result["points"]][:2], [True, True])
        with self.assertRaisesRegex(ValueError, "too short"):
            backtest_im(self.BOND, self.YIELDS, mpor_days=1, confidence=0.75, lookback=10)

    def test_sample_series_exception_rate_is_plausible(self):
        series = sample_series("fx_usdjpy")["series"]
        result = backtest_im({"product": "fx", "notional": 1_000_000}, series, 10, 0.99, 250)
        self.assertEqual(result["observations"], len(series) - 10 - 250)
        self.assertLess(result["exception_rate"], 0.15)


class MarketDataTests(unittest.TestCase):
    def test_price_series(self):
        result = analyze_market_data([100, 110, 99, 108.9], kind="price", window=2)
        np.testing.assert_allclose(result["returns"], [10.0, -10.0, 10.0], atol=1e-6)
        # Rolling 2-day vol: std([10, -10], ddof=1) = 14.142136; annualised x sqrt(252) = 224.499443.
        self.assertIsNone(result["rolling_volatility"][0])
        self.assertAlmostEqual(result["rolling_volatility"][1], 224.499443, places=4)
        one_day = result["worst_moves"][0]
        self.assertEqual(one_day["horizon_days"], 1)
        self.assertAlmostEqual(one_day["worst_down"], -10.0, places=6)
        self.assertEqual((one_day["worst_down_start_index"], one_day["worst_down_end_index"]), (1, 2))
        self.assertAlmostEqual(one_day["worst_up"], 10.0, places=6)
        self.assertEqual(len(result["worst_moves"]), 1)   # too short for 5- and 10-day moves
        self.assertEqual(result["observations"], 4)

    def test_rate_series_uses_absolute_changes_and_all_horizons(self):
        series = list(range(1, 13))            # rises by 1 every day
        series[6] = 2                          # one sharp drop: 6 -> 2, then back to 8
        result = analyze_market_data(series, kind="rate", window=5)
        self.assertEqual(result["returns"][:3], [1.0, 1.0, 1.0])
        self.assertEqual([m["horizon_days"] for m in result["worst_moves"]], [1, 5, 10])
        self.assertEqual(result["worst_moves"][0]["worst_down"], -4.0)   # 6 -> 2
        self.assertEqual(result["worst_moves"][0]["worst_up"], 6.0)      # 2 -> 8
        self.assertEqual(result["worst_moves"][1]["worst_down"], 0.0)    # 2 -> 2 over five days (index 1 to 6)
        self.assertEqual(result["worst_moves"][2]["worst_down"], 10.0)   # every 10-day move is +10

    def test_validation(self):
        with self.assertRaises(ValueError):
            analyze_market_data([1, 2], kind="price")
        with self.assertRaises(ValueError):
            analyze_market_data([1, 2, 3], kind="yield")


class PotentialExposureTests(unittest.TestCase):
    def test_equity_deterministic_profile_and_collateral(self):
        # Zero volatility, 10% drift, grid step 126 days = 0.5y: V(t) = 100 x 100 x (e^(0.1 t) - 1).
        params = {"spot": 100, "quantity": 100, "volatility": 0.0, "drift": 0.10}
        result = simulate_pfe("equity", params, horizon_years=1.0, paths=100, seed=1, mpor_days=126)
        self.assertEqual(result["times"], [0.0, 0.5, 1.0])
        half, full = 10000 * (exp(0.05) - 1), 10000 * (exp(0.10) - 1)   # 512.71 and 1051.71
        np.testing.assert_allclose(result["uncollateralised"]["expected_exposure"], [0, half, full], atol=0.01)
        np.testing.assert_allclose(result["uncollateralised"]["pfe"], [0, half, full], atol=0.01)
        # Collateral held equals the value one step earlier.
        np.testing.assert_allclose(result["collateralised"]["pfe"], [0, half, full - half], atol=0.01)
        self.assertAlmostEqual(result["uncollateralised"]["peak_pfe"], round(full, 2))
        self.assertEqual(result["uncollateralised"]["peak_pfe_time"], 1.0)
        # Trapezoid EPE over [0, 0.5, 1]: 0.25 x half + 0.25 x (half + full).
        self.assertAlmostEqual(result["uncollateralised"]["epe"], 0.5 * half + 0.25 * full, places=1)

    def test_threshold_and_initial_margin(self):
        params = {"spot": 100, "quantity": 100, "volatility": 0.0, "drift": 0.10}
        half, full = 10000 * (exp(0.05) - 1), 10000 * (exp(0.10) - 1)
        # Threshold 600 is above the lagged value (512.71), so no collateral is held at t = 1.
        with_threshold = simulate_pfe("equity", params, 1.0, paths=100, mpor_days=126, threshold=600)
        np.testing.assert_allclose(with_threshold["collateralised"]["pfe"], [0, half, full], atol=0.01)
        # Initial margin of 100 comes straight off the collateralised exposure.
        with_im = simulate_pfe("equity", params, 1.0, paths=100, mpor_days=126, initial_margin=100)
        np.testing.assert_allclose(with_im["collateralised"]["pfe"], [0, half - 100, full - half - 100], atol=0.01)

    def test_short_position_has_no_exposure_when_price_rises(self):
        params = {"spot": 100, "quantity": 100, "volatility": 0.0, "drift": 0.10, "side": "short"}
        result = simulate_pfe("equity", params, 1.0, paths=100, mpor_days=126)
        self.assertEqual(result["uncollateralised"]["pfe"], [0.0, 0.0, 0.0])

    def test_equity_pfe_matches_lognormal_quantile(self):
        # 95% quantile of S(1) under GBM: S0 exp(-vol^2 / 2 + 1.644854 vol).
        result = simulate_pfe("equity", {"spot": 100, "quantity": 1, "volatility": 0.2, "drift": 0.0},
                              horizon_years=1.0, quantile=0.95, paths=40000, seed=7, mpor_days=63)
        analytic = 100 * exp(-0.02 + 1.644854 * 0.2) - 100     # 36.2
        self.assertAlmostEqual(result["uncollateralised"]["pfe"][-1], analytic, delta=1.0)
        # Expected exposure at 1y is the at-the-money call value with zero rates: 100 x (2 N(0.1) - 1) = 7.97.
        self.assertAlmostEqual(result["uncollateralised"]["expected_exposure"][-1], 7.9656, delta=0.25)

    def test_swap_deterministic_values(self):
        # Pay 4% fixed against a 5% flat swap rate, 2 years annual, no volatility, notional 1,000,000.
        params = {"notional": 1_000_000, "swap_rate": 0.05, "fixed_rate": 0.04, "maturity_years": 2.0,
                  "payments_per_year": 1, "rate_vol_bp": 0.0}
        result = simulate_pfe("irs", params, paths=100, mpor_days=126)
        self.assertEqual(result["times"], [0.0, 0.5, 1.0, 1.5, 2.0])
        expected = [
            10000 * (exp(-0.05) + exp(-0.10)),    # 18560.67
            10000 * (exp(-0.025) + exp(-0.075)),  # 19030.53
            10000 * exp(-0.05),                   # 9512.29 (the year-1 coupon has been paid)
            10000 * exp(-0.025),                  # 9753.10
            0.0,
        ]
        np.testing.assert_allclose(result["uncollateralised"]["expected_exposure"], expected, atol=0.01)
        self.assertAlmostEqual(result["initial_value"], 18560.67, places=2)
        np.testing.assert_allclose(result["collateralised"]["expected_exposure"],
                                   [0.0, expected[1] - expected[0], 0.0, expected[3] - expected[2], 0.0], atol=0.01)
        receiver = simulate_pfe("irs", {**params, "side": "receive_fixed"}, paths=100, mpor_days=126)
        self.assertEqual(receiver["uncollateralised"]["peak_pfe"], 0.0)

    def test_fx_forward_deterministic(self):
        # Zero rates and volatility: buy 1,000 foreign at 90 when spot is 100 -> value 10,000 throughout.
        params = {"spot": 100, "notional_foreign": 1000, "strike": 90, "domestic_rate": 0.0, "foreign_rate": 0.0,
                  "volatility": 0.0, "maturity_years": 1.0}
        result = simulate_pfe("fx", params, paths=100, mpor_days=126, threshold=4000)
        self.assertEqual(result["uncollateralised"]["pfe"], [10000.0, 10000.0, 10000.0])
        self.assertEqual(result["collateralised"]["pfe"], [4000.0, 4000.0, 4000.0])   # only the threshold is uncovered
        # Default strike is the forward, so the trade starts at zero value.
        at_market = simulate_pfe("fx", {"volatility": 0.0}, paths=100, mpor_days=126)
        self.assertEqual(at_market["initial_value"], 0.0)
        self.assertEqual(at_market["uncollateralised"]["peak_pfe"], 0.0)

    def test_bond_and_cds_deterministic(self):
        # No yield volatility -> no gain versus the unchanged-yield price.
        bond = simulate_pfe("bond", {"yield_vol_bp": 0.0}, paths=100, mpor_days=126)
        self.assertEqual(bond["uncollateralised"]["peak_pfe"], 0.0)
        # CDS bought at 100bp with the market at 120bp, r = 3%, recovery 40%, no spread volatility:
        # 20bp x 4.423984 x 1,000,000 = 8847.97 at inception.
        cds = simulate_pfe("cds", {"notional": 1_000_000, "spread_bp": 120, "contract_spread_bp": 100, "rate": 0.03,
                                   "recovery": 0.4, "spread_volatility": 0.0, "maturity_years": 5.0},
                           paths=100, mpor_days=126)
        self.assertAlmostEqual(cds["uncollateralised"]["pfe"][0], 8847.97, places=2)
        self.assertEqual(cds["uncollateralised"]["pfe"][-1], 0.0)

    def test_option_exposure(self):
        params = {"spot": 100, "strike": 100, "quantity": 1, "volatility": 0.2, "rate": 0.05, "expiry_years": 1.0}
        long = simulate_pfe("equity_option", params, paths=2000, seed=3)
        self.assertAlmostEqual(long["initial_value"], 10.45, places=2)
        self.assertAlmostEqual(long["uncollateralised"]["expected_exposure"][0], 10.45, places=2)
        short = simulate_pfe("equity_option", {**params, "side": "short"}, paths=2000, seed=3)
        self.assertEqual(short["uncollateralised"]["peak_pfe"], 0.0)

    def test_seed_reproducibility_and_collateral_benefit(self):
        for product in PRODUCTS:
            with self.subTest(product=product):
                first = simulate_pfe(product, paths=1000, seed=42)
                second = simulate_pfe(product, paths=1000, seed=42)
                other = simulate_pfe(product, paths=1000, seed=43)
                self.assertEqual(first["uncollateralised"]["pfe"], second["uncollateralised"]["pfe"])
                self.assertNotEqual(first["uncollateralised"]["pfe"], other["uncollateralised"]["pfe"])
                self.assertLess(first["collateralised"]["epe"], first["uncollateralised"]["epe"])
                self.assertEqual(len(first["times"]), len(first["uncollateralised"]["pfe"]))
                self.assertTrue(any("not a regulatory calculation" in note for note in first["simplifications"]))

    def test_validation(self):
        with self.assertRaisesRegex(ValueError, "unknown parameter"):
            simulate_pfe("equity", {"strike": 100})
        with self.assertRaisesRegex(ValueError, "quantile"):
            simulate_pfe("equity", quantile=1.0)
        with self.assertRaisesRegex(ValueError, "too large"):
            simulate_pfe("irs", {"maturity_years": 30}, paths=50000, mpor_days=1)


class SampleSeriesTests(unittest.TestCase):
    def test_deterministic_and_labelled_synthetic(self):
        first, second = sample_series("swap_rate"), sample_series("swap_rate")
        self.assertEqual(first["series"], second["series"])
        self.assertEqual(len(first["series"]), 750)
        self.assertTrue(all(value > 0 for value in first["series"]))
        self.assertIn("not market data", first["disclaimer"])
        with self.assertRaises(ValueError):
            sample_series("unknown")

    def test_stressed_episode_is_detected_by_calibration(self):
        sample = sample_series("equity_index")
        moves = horizon_shocks(sample["series"], 1)
        start, end = stressed_window(moves, 100)
        episode = sample["stressed_episode"]
        self.assertGreaterEqual(start, episode["start_index"] - 20)
        self.assertLessEqual(end, episode["end_index"] + 20)


class MarginModelsApiTests(unittest.TestCase):
    def setUp(self):
        app = FastAPI()
        app.include_router(router, prefix="/margin-models")
        self.client = TestClient(app)

    def test_endpoints(self):
        names = [item["name"] for item in self.client.get("/margin-models/sample-series").json()["series"]]
        self.assertIn("cds_spread", names)
        self.assertEqual(self.client.get("/margin-models/sample-series/nope").status_code, 404)
        series = self.client.get("/margin-models/sample-series/equity_index").json()["series"]

        analysis = self.client.post("/margin-models/market-data/analyze", json={"series": series})
        self.assertEqual(analysis.status_code, 200)
        self.assertEqual(len(analysis.json()["worst_moves"]), 3)

        position = {"product": "equity", "notional": 1_000_000}
        margin = self.client.post("/margin-models/initial-margin", json={"positions": [{**position, "series": series}]})
        self.assertEqual(margin.status_code, 200)
        self.assertGreater(margin.json()["portfolio"]["historical_im"], 0)

        calibration = self.client.post("/margin-models/initial-margin/calibration", json={"position": position, "series": series})
        self.assertEqual(calibration.status_code, 200)
        self.assertEqual(calibration.json()["rows"][-1]["calibration"], "stressed")

        backtest = self.client.post("/margin-models/initial-margin/backtest", json={"position": position, "series": series})
        self.assertEqual(backtest.status_code, 200)
        self.assertEqual(backtest.json()["observations"], 490)

        pfe = self.client.post("/margin-models/pfe", json={"product": "irs", "params": {"side": "receive_fixed"}, "paths": 500, "seed": 5})
        self.assertEqual(pfe.status_code, 200)
        self.assertEqual(pfe.json()["parameters"]["side"], "receive_fixed")

    def test_validation_errors_are_422(self):
        bad_side = self.client.post("/margin-models/initial-margin", json={"positions": [
            {"product": "irs", "side": "long", "notional": 1, "duration": 1, "series": [1, 2, 3, 4]}]})
        self.assertEqual(bad_side.status_code, 422)
        bad_param = self.client.post("/margin-models/pfe", json={"product": "equity", "params": {"strike": 1}})
        self.assertEqual(bad_param.status_code, 422)
        short = self.client.post("/margin-models/initial-margin/backtest", json={
            "position": {"product": "equity", "notional": 1}, "series": [1, 2, 3, 4, 5]})
        self.assertEqual(short.status_code, 422)


if __name__ == "__main__":
    unittest.main()
