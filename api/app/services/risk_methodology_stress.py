"""Risk methodology: scenario stress testing and simplified economic capital.

Stress P&L is linear: P&L = sensitivity x shock for each risk factor, with no
convexity or cross effects. Scenario shock sizes are illustrative, chosen to
resemble the shape of well-known episodes; they are not exact historical
measurements. Simplified, for analysis and learning; not a regulatory
calculation.
"""

from math import isfinite, log

import numpy as np
from scipy import stats

from app.services.risk_methodology import (
    FACTOR_BY_ID, MARKETS, MODEL_DISCLAIMER, RISK_FACTORS, RISK_TYPES,
    SAMPLE_POSITIONS, sample_portfolio,
)

SCENARIO_DISCLAIMER = (
    "Shock sizes are illustrative and rounded. They are not exact historical measurements."
)


def _shocks(equity, rates, credit, fx) -> dict[str, float]:
    """Build a shock map from per-market tuples ordered India, China, Japan, South Korea."""
    ordered = {"equity": equity, "rates": rates, "credit": credit, "fx": fx}
    shocks = {}
    for factor in RISK_FACTORS:
        value = ordered[factor["risk_type"]][MARKETS.index(factor["market"])]
        if value:
            shocks[factor["id"]] = float(value)
    return shocks


# Equity and FX shocks in %, rates and credit shocks in bp.
# FX is the move of the local currency against USD (negative = depreciation).
SCENARIO_LIBRARY: list[dict] = [
    {
        "id": "global_credit_crisis",
        "name": "Global credit crisis (2008-style)",
        "description": "Sharp equity falls across Asia, spreads widen, carry currencies weaken and the yen rallies.",
        "shocks": _shocks((-25, -22, -28, -27), (-40, -30, -15, -50), (200, 180, 90, 250), (-8, -1, 12, -18)),
    },
    {
        "id": "asian_currency_crisis",
        "name": "Asian currency crisis (1997-style)",
        "description": "Disorderly currency depreciation led by the won, with rate rises to defend currencies.",
        "shocks": _shocks((-15, -8, -12, -35), (150, 20, -10, 400), (150, 80, 40, 400), (-12, -1, 5, -35)),
    },
    {
        "id": "china_equity_deleveraging",
        "name": "China equity deleveraging (2015-style)",
        "description": "A margin-driven fall in mainland equities with a one-off currency adjustment and regional spillover.",
        "shocks": _shocks((-8, -30, -10, -9), (-10, -30, -5, -10), (30, 90, 15, 35), (-2, -3, 3, -4)),
    },
    {
        "id": "pandemic_liquidity_shock",
        "name": "Pandemic liquidity shock (2020-style)",
        "description": "A fast global sell-off with a scramble for USD funding and wider credit spreads.",
        "shocks": _shocks((-23, -10, -20, -22), (-40, -30, 5, -30), (120, 60, 50, 100), (-5, -2, 2, -7)),
    },
    {
        "id": "india_outflow_shock",
        "name": "India capital outflow (2013-style)",
        "description": "Higher US yields trigger outflows from India: the rupee falls and local yields jump.",
        "shocks": _shocks((-10, -3, -4, -5), (120, 15, 10, 30), (80, 15, 5, 20), (-12, -1, -3, -4)),
    },
    {
        "id": "yen_carry_unwind",
        "name": "Yen carry trade unwind",
        "description": "A policy surprise in Japan lifts yen yields and the yen; Japanese equities fall hard.",
        "shocks": _shocks((-4, -2, -18, -9), (5, 0, 35, 10), (15, 10, 30, 25), (-1, 0, 10, -2)),
    },
    {
        "id": "rates_up_100",
        "name": "Parallel rates +100bp",
        "description": "Hypothetical: all four yield curves rise by 100bp with a mild equity fall.",
        "shocks": _shocks((-5, -5, -5, -5), (100, 100, 100, 100), (20, 20, 20, 20), (0, 0, 0, 0)),
    },
    {
        "id": "korea_credit_crunch",
        "name": "South Korea credit crunch",
        "description": "Hypothetical: a local funding squeeze widens Korean credit spreads and weakens the won.",
        "shocks": _shocks((-2, -1, -2, -12), (0, 0, 0, 60), (10, 10, 5, 220), (-1, 0, 1, -8)),
    },
]
SCENARIO_BY_ID = {scenario["id"]: scenario for scenario in SCENARIO_LIBRARY}


def scenario_library() -> list[dict]:
    return [{**scenario, "shocks": dict(scenario["shocks"]), "illustrative": True} for scenario in SCENARIO_LIBRARY]


def _positions(positions: list[dict] | None) -> dict[str, float]:
    book: dict[str, float] = {}
    for position in positions if positions is not None else SAMPLE_POSITIONS:
        factor_id = str(position["factor_id"])
        if factor_id not in FACTOR_BY_ID:
            raise ValueError(f"unknown risk factor: {factor_id}")
        sensitivity = float(position["sensitivity"])
        if not isfinite(sensitivity):
            raise ValueError(f"{factor_id}: sensitivity must be a finite number")
        book[factor_id] = book.get(factor_id, 0.0) + sensitivity
    if not book:
        raise ValueError("at least one position is required")
    return book


def _clean_shocks(shocks: dict) -> dict[str, float]:
    cleaned = {}
    for factor_id, shock in shocks.items():
        if factor_id not in FACTOR_BY_ID:
            raise ValueError(f"unknown risk factor: {factor_id}")
        value = float(shock)
        if not isfinite(value):
            raise ValueError(f"{factor_id}: shock must be a finite number")
        cleaned[factor_id] = value
    return cleaned


def apply_scenario(positions: list[dict] | None, shocks: dict[str, float]) -> dict:
    """Linear P&L of one scenario: sensitivity x shock for every risk factor."""
    book = _positions(positions)
    shocks = _clean_shocks(shocks)
    by_type = {risk_type: 0.0 for risk_type in RISK_TYPES}
    by_market = {market: 0.0 for market in MARKETS}
    by_factor = []
    for factor in RISK_FACTORS:
        factor_id = factor["id"]
        shock = shocks.get(factor_id, 0.0)
        sensitivity = book.get(factor_id, 0.0)
        pnl = sensitivity * shock
        if factor_id not in book and not shock:
            continue
        by_type[factor["risk_type"]] += pnl
        by_market[factor["market"]] += pnl
        by_factor.append({
            "factor_id": factor_id, "label": factor["label"], "risk_type": factor["risk_type"],
            "market": factor["market"], "unit": factor["unit"], "shock": shock,
            "sensitivity": sensitivity, "pnl": round(pnl, 2),
        })
    return {
        "total_pnl": round(sum(by_type.values()), 2),
        "by_risk_type": {key: round(value, 2) for key, value in by_type.items()},
        "by_market": {key: round(value, 2) for key, value in by_market.items()},
        "by_factor": by_factor,
    }


def resolve_scenarios(scenario_ids: list[str] | None, custom_scenarios: list[dict] | None) -> list[dict]:
    """Library scenarios (all when no ids are given) followed by user-defined ones."""
    scenarios = []
    if scenario_ids is None and not custom_scenarios:
        scenario_ids = [scenario["id"] for scenario in SCENARIO_LIBRARY]
    for scenario_id in scenario_ids or []:
        if scenario_id not in SCENARIO_BY_ID:
            raise ValueError(f"unknown scenario: {scenario_id}")
        scenarios.append({**SCENARIO_BY_ID[scenario_id], "source": "library"})
    for index, custom in enumerate(custom_scenarios or []):
        name = str(custom.get("name", "")).strip() or f"Custom scenario {index + 1}"
        scenarios.append({
            "id": f"custom_{index + 1}", "name": name,
            "description": str(custom.get("description", "")).strip() or "User-defined scenario.",
            "shocks": _clean_shocks(custom.get("shocks", {})), "source": "custom",
        })
    if not scenarios:
        raise ValueError("at least one scenario is required")
    return scenarios


def run_stress_test(
    positions: list[dict] | None = None,
    scenario_ids: list[str] | None = None,
    custom_scenarios: list[dict] | None = None,
) -> dict:
    """Apply each scenario and report P&L by risk type, market and factor."""
    results = []
    for scenario in resolve_scenarios(scenario_ids, custom_scenarios):
        outcome = apply_scenario(positions, scenario["shocks"])
        results.append({
            "id": scenario["id"], "name": scenario["name"], "description": scenario["description"],
            "source": scenario["source"], "shocks": dict(scenario["shocks"]), **outcome,
        })
    worst = min(results, key=lambda row: row["total_pnl"])
    return {
        "results": results,
        "worst_scenario": {"id": worst["id"], "name": worst["name"], "total_pnl": worst["total_pnl"]},
        "using_sample_portfolio": positions is None,
        "disclaimer": f"{SCENARIO_DISCLAIMER} Linear sensitivities only. {MODEL_DISCLAIMER}",
    }


def reverse_stress_test(positions: list[dict] | None, shocks: dict[str, float], loss_threshold: float) -> dict:
    """Scale a scenario until the loss reaches `loss_threshold` (a positive amount).

    With linear sensitivities the answer is exact: multiplier = threshold /
    loss at 1x. A scenario that makes money at 1x can never reach the loss.
    """
    if not isfinite(loss_threshold) or loss_threshold <= 0:
        raise ValueError("loss_threshold must be a positive amount")
    base = apply_scenario(positions, shocks)
    base_loss = -base["total_pnl"]
    if base_loss <= 0:
        return {
            "reachable": False, "loss_threshold": loss_threshold, "base_pnl": base["total_pnl"],
            "multiplier": None, "scaled_shocks": {}, "scaled": None,
            "finding": "The scenario does not lose money on this portfolio, so no scaling of it reaches the loss threshold.",
        }
    multiplier = loss_threshold / base_loss
    scaled_shocks = {factor_id: shock * multiplier for factor_id, shock in _clean_shocks(shocks).items()}
    return {
        "reachable": True,
        "loss_threshold": loss_threshold,
        "base_pnl": base["total_pnl"],
        "multiplier": round(multiplier, 6),
        "scaled_shocks": {factor_id: round(shock, 4) for factor_id, shock in scaled_shocks.items()},
        "scaled": apply_scenario(positions, scaled_shocks),
        "finding": (
            f"The loss reaches {loss_threshold:,.0f} when every shock in the scenario is scaled by "
            f"{multiplier:.2f}x. At 1x the scenario loses {base_loss:,.0f}."
        ),
    }


# ---------------------------------------------------------------------------
# Economic capital (simplified)
# ---------------------------------------------------------------------------

# Clearly fictional counterparties. Illustrative figures, USD.
SAMPLE_CREDIT_EXPOSURES: list[dict] = [
    {"name": "Aravali Infra Holdings (sample)", "market": "India", "ead": 40_000_000.0, "pd": 0.020, "lgd": 0.45},
    {"name": "Deccan Coastal Finance (sample)", "market": "India", "ead": 25_000_000.0, "pd": 0.012, "lgd": 0.50},
    {"name": "Jade River Machinery (sample)", "market": "China", "ead": 35_000_000.0, "pd": 0.025, "lgd": 0.55},
    {"name": "Pearl Delta Property Group (sample)", "market": "China", "ead": 20_000_000.0, "pd": 0.060, "lgd": 0.60},
    {"name": "Hoshizora Trading Co (sample)", "market": "Japan", "ead": 50_000_000.0, "pd": 0.004, "lgd": 0.40},
    {"name": "Kitayama Regional Bank (sample)", "market": "Japan", "ead": 30_000_000.0, "pd": 0.003, "lgd": 0.45},
    {"name": "Hanbit Marine Engineering (sample)", "market": "South Korea", "ead": 30_000_000.0, "pd": 0.015, "lgd": 0.50},
    {"name": "Saebyeok Asset Fund (sample)", "market": "South Korea", "ead": 15_000_000.0, "pd": 0.030, "lgd": 0.60},
]

EC_RISK_TYPES = ("market", "credit", "operational")


def unexpected_loss(losses, confidence: float) -> dict:
    """Expected loss, loss quantile and unexpected loss (quantile minus mean)."""
    if not 0.5 < confidence < 1:
        raise ValueError("confidence must be between 0.5 and 1 (exclusive)")
    values = np.asarray(losses, dtype=float)
    if values.size < 2:
        raise ValueError("at least two simulated losses are required")
    expected = float(values.mean())
    quantile = float(np.quantile(values, confidence))
    return {"expected_loss": expected, "loss_quantile": quantile, "unexpected_loss": quantile - expected}


def diversification_benefit(standalone: dict[str, float], diversified_total: float) -> dict:
    """Sum of standalone capital less the capital of the combined loss."""
    undiversified = sum(standalone.values())
    benefit = undiversified - diversified_total
    return {
        "undiversified": undiversified,
        "diversified": diversified_total,
        "benefit": benefit,
        "benefit_pct": benefit / undiversified * 100 if undiversified else 0.0,
    }


def default_market_annual_vol(seed: int = 42) -> float:
    """Annualised P&L volatility of the synthetic sample book (250 days a year)."""
    return float(np.std(sample_portfolio(seed)["pnl"], ddof=1) * np.sqrt(250))


def simulate_economic_capital(
    market_annual_vol: float | None = None,
    credit_exposures: list[dict] | None = None,
    asset_correlation: float = 0.20,
    operational_expected_loss: float = 2_000_000.0,
    operational_sigma: float = 1.0,
    correlations: dict[str, float] | None = None,
    confidence: float = 0.999,
    simulations: int = 50_000,
    seed: int = 7,
) -> dict:
    """One-year economic capital from a simulated loss distribution.

    Simplified, for analysis and learning; not a regulatory calculation.
    - Market: normal annual loss with standard deviation `market_annual_vol`.
    - Credit: one-factor Gaussian default model; each name defaults when its
      asset return falls below N^-1(pd) and then loses ead x lgd.
    - Operational: lognormal annual loss with the given mean and log-sigma.
    The three systematic drivers are jointly normal with the pairwise
    `correlations` (keys market_credit, market_operational, credit_operational).
    Capital for each risk type is its loss quantile minus its expected loss.
    """
    if market_annual_vol is None:
        market_annual_vol = default_market_annual_vol()
    exposures = SAMPLE_CREDIT_EXPOSURES if credit_exposures is None else credit_exposures
    if market_annual_vol < 0 or not isfinite(market_annual_vol):
        raise ValueError("market_annual_vol cannot be negative")
    if not 0 <= asset_correlation < 1:
        raise ValueError("asset_correlation must be in [0, 1)")
    if operational_expected_loss < 0 or operational_sigma <= 0:
        raise ValueError("operational_expected_loss cannot be negative and operational_sigma must be positive")
    if not 1_000 <= simulations <= 200_000:
        raise ValueError("simulations must be between 1,000 and 200,000")
    for exposure in exposures:
        if exposure["ead"] < 0 or not 0 <= exposure["pd"] <= 1 or not 0 <= exposure["lgd"] <= 1:
            raise ValueError(f"{exposure.get('name', 'exposure')}: need ead >= 0 and pd, lgd in [0, 1]")

    pairs = {"market_credit": 0.5, "market_operational": 0.2, "credit_operational": 0.2, **(correlations or {})}
    matrix = np.array([
        [1.0, pairs["market_credit"], pairs["market_operational"]],
        [pairs["market_credit"], 1.0, pairs["credit_operational"]],
        [pairs["market_operational"], pairs["credit_operational"], 1.0],
    ])
    try:
        cholesky = np.linalg.cholesky(matrix)
    except np.linalg.LinAlgError as exc:
        raise ValueError("correlations do not form a valid correlation matrix") from exc

    rng = np.random.default_rng(seed)
    drivers = rng.standard_normal((simulations, 3)) @ cholesky.T
    market = market_annual_vol * drivers[:, 0]

    credit = np.zeros(simulations)
    for exposure in exposures:
        idiosyncratic = rng.standard_normal(simulations)
        # A high systematic driver is a bad year, matching the sign of the market loss.
        asset = -np.sqrt(asset_correlation) * drivers[:, 1] + np.sqrt(1 - asset_correlation) * idiosyncratic
        credit += (asset < stats.norm.ppf(exposure["pd"])) * exposure["ead"] * exposure["lgd"]

    if operational_expected_loss > 0:
        mu = log(operational_expected_loss) - operational_sigma**2 / 2
        operational = np.exp(mu + operational_sigma * drivers[:, 2])
    else:
        operational = np.zeros(simulations)

    losses = {"market": market, "credit": credit, "operational": operational}
    total = market + credit + operational
    breakdown = []
    standalone = {}
    for risk_type in EC_RISK_TYPES:
        metrics = unexpected_loss(losses[risk_type], confidence)
        standalone[risk_type] = metrics["unexpected_loss"]
        breakdown.append({"risk_type": risk_type, **{key: round(value, 2) for key, value in metrics.items()}})
    total_metrics = unexpected_loss(total, confidence)
    diversification = diversification_benefit(standalone, total_metrics["unexpected_loss"])
    for row in breakdown:
        share = row["unexpected_loss"] / diversification["undiversified"] if diversification["undiversified"] else 0.0
        row["share_of_undiversified_pct"] = round(share * 100, 2)
        row["allocated_capital"] = round(share * diversification["diversified"], 2)

    counts, edges = np.histogram(total, bins=40)
    return {
        "confidence": confidence,
        "simulations": simulations,
        "seed": seed,
        "horizon": "1 year",
        "currency": "USD",
        "inputs": {
            "market_annual_vol": round(market_annual_vol, 2),
            "asset_correlation": asset_correlation,
            "operational_expected_loss": operational_expected_loss,
            "operational_sigma": operational_sigma,
            "correlations": pairs,
            "credit_exposures": [dict(exposure) for exposure in exposures],
            "using_sample_exposures": credit_exposures is None,
        },
        "breakdown": breakdown,
        "total": {key: round(value, 2) for key, value in total_metrics.items()},
        "economic_capital": round(diversification["diversified"], 2),
        "diversification": {key: round(value, 2) for key, value in diversification.items()},
        "histogram": [
            {"loss": round(float((edges[index] + edges[index + 1]) / 2), 0), "count": int(count)}
            for index, count in enumerate(counts)
        ],
        "disclaimer": (
            "Simplified economic capital: stylised loss models and illustrative inputs. "
            "Allocated capital spreads the diversified total in proportion to standalone capital. "
            + MODEL_DISCLAIMER
        ),
    }
