"""Risk methodology: VaR backtesting, coverage tests and expected shortfall.

Everything here is a pure function over plain lists and numbers. The models
are simplified, for analysis and learning; they are not regulatory
calculations. The bundled sample portfolio is synthetic: its risk factor
moves are generated from a fixed random seed and are not market data.

Conventions
- P&L is signed: a loss is negative.
- VaR and expected shortfall are reported as positive loss amounts.
- The VaR for day t uses only the `window` observations before day t.
- An exception is a day whose loss is strictly greater than that day's VaR.
"""

from datetime import date, timedelta
from math import isfinite, log, sqrt

import numpy as np
from numpy.lib.stride_tricks import sliding_window_view
from scipy import stats

METHODS = ("historical", "parametric")

# ---------------------------------------------------------------------------
# Risk factors shared by the backtesting, stress and monitoring services
# ---------------------------------------------------------------------------

MARKETS = ("India", "China", "Japan", "South Korea")
RISK_TYPES = ("equity", "rates", "credit", "fx")

# unit: a sensitivity is the USD P&L for a +1 unit move in the factor.
#   equity: +1% index move            fx: +1% move of the local currency vs USD
#   rates:  +1bp move in the yield    credit: +1bp move in the spread
# daily_vol / beta / liquidity_horizon are illustrative settings used only to
# generate the synthetic sample history and the simplified liquidity scaling.
RISK_FACTORS: list[dict] = [
    {"id": "EQ_NIFTY50", "label": "Nifty 50", "risk_type": "equity", "market": "India", "unit": "%", "daily_vol": 1.0, "beta": 0.70, "liquidity_horizon": 10},
    {"id": "EQ_CSI300", "label": "CSI 300", "risk_type": "equity", "market": "China", "unit": "%", "daily_vol": 1.3, "beta": 0.60, "liquidity_horizon": 10},
    {"id": "EQ_NIKKEI225", "label": "Nikkei 225", "risk_type": "equity", "market": "Japan", "unit": "%", "daily_vol": 1.2, "beta": 0.75, "liquidity_horizon": 10},
    {"id": "EQ_KOSPI", "label": "KOSPI", "risk_type": "equity", "market": "South Korea", "unit": "%", "daily_vol": 1.2, "beta": 0.75, "liquidity_horizon": 10},
    {"id": "IR_INR", "label": "India 10Y yield", "risk_type": "rates", "market": "India", "unit": "bp", "daily_vol": 5.0, "beta": -0.20, "liquidity_horizon": 20},
    {"id": "IR_CNY", "label": "China 10Y yield", "risk_type": "rates", "market": "China", "unit": "bp", "daily_vol": 3.0, "beta": 0.20, "liquidity_horizon": 20},
    {"id": "IR_JPY", "label": "Japan 10Y yield", "risk_type": "rates", "market": "Japan", "unit": "bp", "daily_vol": 2.0, "beta": 0.25, "liquidity_horizon": 20},
    {"id": "IR_KRW", "label": "South Korea 10Y yield", "risk_type": "rates", "market": "South Korea", "unit": "bp", "daily_vol": 4.0, "beta": 0.20, "liquidity_horizon": 20},
    {"id": "CS_IN", "label": "India credit spread", "risk_type": "credit", "market": "India", "unit": "bp", "daily_vol": 3.0, "beta": -0.60, "liquidity_horizon": 40},
    {"id": "CS_CN", "label": "China credit spread", "risk_type": "credit", "market": "China", "unit": "bp", "daily_vol": 4.0, "beta": -0.60, "liquidity_horizon": 40},
    {"id": "CS_JP", "label": "Japan credit spread", "risk_type": "credit", "market": "Japan", "unit": "bp", "daily_vol": 2.0, "beta": -0.50, "liquidity_horizon": 40},
    {"id": "CS_KR", "label": "South Korea credit spread", "risk_type": "credit", "market": "South Korea", "unit": "bp", "daily_vol": 3.5, "beta": -0.60, "liquidity_horizon": 40},
    {"id": "FX_INR", "label": "INR vs USD", "risk_type": "fx", "market": "India", "unit": "%", "daily_vol": 0.30, "beta": 0.50, "liquidity_horizon": 20},
    {"id": "FX_CNY", "label": "CNY vs USD", "risk_type": "fx", "market": "China", "unit": "%", "daily_vol": 0.20, "beta": 0.40, "liquidity_horizon": 20},
    {"id": "FX_JPY", "label": "JPY vs USD", "risk_type": "fx", "market": "Japan", "unit": "%", "daily_vol": 0.60, "beta": -0.35, "liquidity_horizon": 10},
    {"id": "FX_KRW", "label": "KRW vs USD", "risk_type": "fx", "market": "South Korea", "unit": "%", "daily_vol": 0.50, "beta": 0.55, "liquidity_horizon": 20},
]
FACTOR_BY_ID: dict[str, dict] = {factor["id"]: factor for factor in RISK_FACTORS}

SAMPLE_PORTFOLIO_NAME = "Illustrative Asia Multi-Asset Book (sample)"

# Sample sensitivities in USD per unit move (see `unit` above). Illustrative.
SAMPLE_POSITIONS: list[dict] = [
    {"factor_id": "EQ_NIFTY50", "sensitivity": 250_000.0},
    {"factor_id": "EQ_CSI300", "sensitivity": 180_000.0},
    {"factor_id": "EQ_NIKKEI225", "sensitivity": 300_000.0},
    {"factor_id": "EQ_KOSPI", "sensitivity": 150_000.0},
    {"factor_id": "IR_INR", "sensitivity": -45_000.0},
    {"factor_id": "IR_CNY", "sensitivity": -30_000.0},
    {"factor_id": "IR_JPY", "sensitivity": 40_000.0},
    {"factor_id": "IR_KRW", "sensitivity": -25_000.0},
    {"factor_id": "CS_IN", "sensitivity": -20_000.0},
    {"factor_id": "CS_CN", "sensitivity": -35_000.0},
    {"factor_id": "CS_JP", "sensitivity": -10_000.0},
    {"factor_id": "CS_KR", "sensitivity": -15_000.0},
    {"factor_id": "FX_INR", "sensitivity": 200_000.0},
    {"factor_id": "FX_CNY", "sensitivity": 150_000.0},
    {"factor_id": "FX_JPY", "sensitivity": -250_000.0},
    {"factor_id": "FX_KRW", "sensitivity": 120_000.0},
]

SAMPLE_END_DATE = date(2025, 12, 31)
SAMPLE_DISCLAIMER = (
    "Synthetic sample data generated from a fixed random seed. "
    "It is illustrative only and is not market data."
)
MODEL_DISCLAIMER = "Simplified, for analysis and learning; not a regulatory calculation."


def list_risk_factors() -> list[dict]:
    """Risk factor definitions without the internal simulation settings."""
    keys = ("id", "label", "risk_type", "market", "unit", "liquidity_horizon")
    return [{key: factor[key] for key in keys} for factor in RISK_FACTORS]


def _business_days(end: date, count: int) -> list[str]:
    days: list[str] = []
    current = end
    while len(days) < count:
        if current.weekday() < 5:
            days.append(current.isoformat())
        current -= timedelta(days=1)
    return days[::-1]


def sample_factor_moves(seed: int = 42, days: int = 750) -> np.ndarray:
    """Synthetic daily factor moves, shape (days, number of factors).

    One common "Asia risk" driver with fat tails (Student t, 5 degrees of
    freedom) and a GARCH(1,1)-style volatility state, plus independent noise
    per factor. The same seed always gives the same history.
    """
    if days < 2:
        raise ValueError("days must be at least 2")
    rng = np.random.default_rng(seed)
    dof = 5
    common = rng.standard_t(dof, size=days) * sqrt((dof - 2) / dof)
    noise = rng.standard_normal((days, len(RISK_FACTORS)))
    variance = np.empty(days)
    variance[0] = 1.0
    for t in range(1, days):
        shock = common[t - 1] * sqrt(variance[t - 1])
        variance[t] = 0.06 + 0.10 * shock**2 + 0.84 * variance[t - 1]
    scale = np.sqrt(variance)[:, None]
    betas = np.array([factor["beta"] for factor in RISK_FACTORS])
    vols = np.array([factor["daily_vol"] for factor in RISK_FACTORS])
    return vols * scale * (betas * common[:, None] + np.sqrt(1 - betas**2) * noise)


def sample_portfolio(seed: int = 42, days: int = 750) -> dict:
    """Deterministic synthetic P&L history for the bundled sample book."""
    moves = sample_factor_moves(seed, days)
    sensitivities = np.array([position["sensitivity"] for position in SAMPLE_POSITIONS])
    factor_pnl = moves * sensitivities
    return {
        "name": SAMPLE_PORTFOLIO_NAME,
        "currency": "USD",
        "seed": seed,
        "disclaimer": SAMPLE_DISCLAIMER,
        "factors": list_risk_factors(),
        "positions": [dict(position) for position in SAMPLE_POSITIONS],
        "dates": _business_days(SAMPLE_END_DATE, days),
        "pnl": [round(float(value), 2) for value in factor_pnl.sum(axis=1)],
        "factor_pnl": {
            factor["id"]: [round(float(value), 2) for value in factor_pnl[:, index]]
            for index, factor in enumerate(RISK_FACTORS)
        },
    }


# ---------------------------------------------------------------------------
# VaR and expected shortfall
# ---------------------------------------------------------------------------

def _check_confidence(confidence: float) -> None:
    if not 0.5 < confidence < 1:
        raise ValueError("confidence must be between 0.5 and 1 (exclusive)")


def historical_var_es(pnl, confidence: float) -> tuple[float, float]:
    """Historical simulation VaR and expected shortfall of a P&L sample.

    VaR is minus the (1 - confidence) empirical quantile, using linear
    interpolation between order statistics. Expected shortfall is the average
    loss over the observations at or beyond that quantile.
    """
    _check_confidence(confidence)
    values = np.asarray(pnl, dtype=float)
    if values.size < 2:
        raise ValueError("at least two observations are required")
    quantile = float(np.quantile(values, 1 - confidence))
    tail = values[values <= quantile]
    return -quantile, -float(tail.mean())


def parametric_var_es(pnl, confidence: float) -> tuple[float, float]:
    """Normal (variance-covariance) VaR and expected shortfall.

    VaR = -(mean + z * sd) with z = N^-1(1 - confidence) and the sample
    standard deviation (n - 1). ES = -mean + sd * pdf(z) / (1 - confidence).
    """
    _check_confidence(confidence)
    values = np.asarray(pnl, dtype=float)
    if values.size < 2:
        raise ValueError("at least two observations are required")
    mean = float(values.mean())
    sd = float(values.std(ddof=1))
    z = float(stats.norm.ppf(1 - confidence))
    return -(mean + z * sd), -mean + sd * float(stats.norm.pdf(z)) / (1 - confidence)


def var_es(pnl, confidence: float, method: str = "historical") -> tuple[float, float]:
    if method == "historical":
        return historical_var_es(pnl, confidence)
    if method == "parametric":
        return parametric_var_es(pnl, confidence)
    raise ValueError(f"method must be one of: {', '.join(METHODS)}")


def rolling_var(pnl, confidence: float = 0.99, window: int = 250, method: str = "historical") -> np.ndarray:
    """One-day VaR for each day from index `window` onwards.

    Element i is the VaR for day window + i, estimated from the `window`
    observations immediately before that day (no look-ahead).
    """
    _check_confidence(confidence)
    values = np.asarray(pnl, dtype=float)
    if window < 2:
        raise ValueError("window must be at least 2")
    if values.size <= window:
        raise ValueError("the series must be longer than the window")
    windows = sliding_window_view(values, window)[:-1]
    if method == "historical":
        return -np.quantile(windows, 1 - confidence, axis=1)
    if method == "parametric":
        z = float(stats.norm.ppf(1 - confidence))
        return -(windows.mean(axis=1) + z * windows.std(axis=1, ddof=1))
    raise ValueError(f"method must be one of: {', '.join(METHODS)}")


# ---------------------------------------------------------------------------
# Coverage tests
# ---------------------------------------------------------------------------

def _xlogy(count: float, probability: float) -> float:
    """count * ln(probability) with the convention 0 * ln(0) = 0."""
    return 0.0 if count == 0 else count * log(probability)


def kupiec_pof(n_obs: int, n_exceptions: int, coverage: float) -> dict:
    """Kupiec proportion-of-failures (unconditional coverage) test.

    coverage is the expected exception probability p (0.01 for a 99% VaR).
    LR = -2 ln[(1-p)^(T-x) p^x] + 2 ln[(1-x/T)^(T-x) (x/T)^x], chi-square(1).
    """
    if n_obs < 1 or not 0 <= n_exceptions <= n_obs:
        raise ValueError("need n_obs >= 1 and 0 <= n_exceptions <= n_obs")
    if not 0 < coverage < 1:
        raise ValueError("coverage must be between 0 and 1 (exclusive)")
    x, t = n_exceptions, n_obs
    observed = x / t
    null = _xlogy(t - x, 1 - coverage) + _xlogy(x, coverage)
    alternative = _xlogy(t - x, 1 - observed) + _xlogy(x, observed)
    statistic = max(-2 * (null - alternative), 0.0) or 0.0  # also clears -0.0
    return {
        "statistic": statistic,
        "p_value": float(stats.chi2.sf(statistic, 1)),
        "observed_rate": observed,
        "expected_rate": coverage,
    }


def transition_counts(hits) -> dict:
    """Counts of day-to-day transitions in a 0/1 exception sequence."""
    flags = [1 if hit else 0 for hit in hits]
    counts = {"n00": 0, "n01": 0, "n10": 0, "n11": 0}
    for previous, current in zip(flags, flags[1:]):
        counts[f"n{previous}{current}"] += 1
    return counts


def christoffersen_independence(hits) -> dict:
    """Christoffersen test that exceptions are independent from day to day.

    First-order Markov alternative, chi-square(1):
    LR = -2 ln[(1-pi)^(n00+n10) pi^(n01+n11)]
         + 2 ln[(1-pi01)^n00 pi01^n01 (1-pi11)^n10 pi11^n11]
    with pi01 = n01/(n00+n01), pi11 = n11/(n10+n11), pi = (n01+n11)/total.
    """
    counts = transition_counts(hits)
    n00, n01, n10, n11 = counts["n00"], counts["n01"], counts["n10"], counts["n11"]
    total = n00 + n01 + n10 + n11
    if total < 1:  # a single observation has no transitions to test
        return {"statistic": 0.0, "p_value": 1.0, "pi01": 0.0, "pi11": 0.0, **counts}
    pi = (n01 + n11) / total
    pi01 = n01 / (n00 + n01) if n00 + n01 else 0.0
    pi11 = n11 / (n10 + n11) if n10 + n11 else 0.0
    null = _xlogy(n00 + n10, 1 - pi) + _xlogy(n01 + n11, pi)
    alternative = (
        _xlogy(n00, 1 - pi01) + _xlogy(n01, pi01)
        + _xlogy(n10, 1 - pi11) + _xlogy(n11, pi11)
    )
    statistic = max(-2 * (null - alternative), 0.0) or 0.0  # also clears -0.0
    return {
        "statistic": statistic,
        "p_value": float(stats.chi2.sf(statistic, 1)),
        "pi01": pi01,
        "pi11": pi11,
        **counts,
    }


def christoffersen_conditional_coverage(hits, coverage: float) -> dict:
    """Joint test of correct coverage and independence, chi-square(2).

    LR_cc = LR_pof + LR_ind (the usual additive form).
    """
    flags = [1 if hit else 0 for hit in hits]
    pof = kupiec_pof(len(flags), sum(flags), coverage)
    independence = christoffersen_independence(flags)
    statistic = pof["statistic"] + independence["statistic"]
    return {"statistic": statistic, "p_value": float(stats.chi2.sf(statistic, 2))}


_BASEL_PLUS_FACTORS = {5: 0.40, 6: 0.50, 7: 0.65, 8: 0.75, 9: 0.85}


def basel_traffic_light(n_exceptions: int, n_obs: int = 250, confidence: float = 0.99) -> dict:
    """Basel traffic-light zone from the cumulative binomial probability.

    Green below 95%, yellow from 95% up to 99.99%, red at 99.99% or above.
    For 250 observations at 99% this gives green 0-4, yellow 5-9, red 10+.
    The capital multiplier add-on is only reported for that standard setting.
    """
    if n_obs < 1 or not 0 <= n_exceptions <= n_obs:
        raise ValueError("need n_obs >= 1 and 0 <= n_exceptions <= n_obs")
    _check_confidence(confidence)
    cumulative = float(stats.binom.cdf(n_exceptions, n_obs, 1 - confidence))
    zone = "green" if cumulative < 0.95 else "yellow" if cumulative < 0.9999 else "red"
    plus_factor = None
    if n_obs == 250 and abs(confidence - 0.99) < 1e-12:
        plus_factor = 0.0 if zone == "green" else 1.0 if zone == "red" else _BASEL_PLUS_FACTORS[n_exceptions]
    return {
        "zone": zone,
        "n_exceptions": n_exceptions,
        "n_obs": n_obs,
        "confidence": confidence,
        "cumulative_probability": cumulative,
        "plus_factor": plus_factor,
        "standard_setting": plus_factor is not None,
    }


# ---------------------------------------------------------------------------
# Liquidity-horizon scaling (simplified FRTB-style illustration)
# ---------------------------------------------------------------------------

BASE_HORIZON_DAYS = 10


def liquidity_horizon_es(es_by_horizon: dict[int, float], base_horizon: int = BASE_HORIZON_DAYS) -> float:
    """Combine base-horizon ES figures across liquidity horizons.

    es_by_horizon[h] is the base-horizon ES of the P&L from all risk factors
    whose liquidity horizon is at least h. Following the FRTB cascade shape:
        ES = sqrt( sum_j ( ES_j * sqrt((LH_j - LH_{j-1}) / base) )^2 ),
    with LH_0 = 0, so the first bucket (the base horizon, all factors) has
    weight 1. Simplified FRTB-style illustration, not a regulatory number.
    """
    horizons = sorted(es_by_horizon)
    if not horizons or horizons[0] != base_horizon:
        raise ValueError("the shortest liquidity horizon must equal the base horizon")
    total, previous = 0.0, 0
    for horizon in horizons:
        total += es_by_horizon[horizon] ** 2 * (horizon - previous) / base_horizon
        previous = horizon
    return sqrt(total)


def expected_shortfall_summary(
    pnl,
    factor_pnl: dict[str, list[float]] | None = None,
    confidence: float = 0.975,
    method: str = "historical",
) -> dict:
    """Expected shortfall over the supplied P&L sample.

    Returns the one-day ES and VaR at `confidence`, the ES scaled to the
    10-day base horizon with the square root of time, and, when a factor
    breakdown is available, a liquidity-horizon adjusted ES.
    """
    values = np.asarray(pnl, dtype=float)
    var_1d, es_1d = var_es(values, confidence, method)
    scale = sqrt(BASE_HORIZON_DAYS)
    result = {
        "confidence": confidence,
        "method": method,
        "n_obs": int(values.size),
        "var_1d": round(var_1d, 2),
        "es_1d": round(es_1d, 2),
        "es_base_horizon": round(es_1d * scale, 2),
        "base_horizon_days": BASE_HORIZON_DAYS,
        "liquidity_adjusted_es": None,
        "buckets": [],
        "note": (
            "Simplified FRTB-style illustration: one-day ES is scaled to 10 days with the "
            "square root of time, then combined across illustrative liquidity horizons. "
            "It omits stressed-period calibration, the reduced factor set and desk-level "
            "aggregation, so it is not a regulatory capital figure."
        ),
    }
    known = {key: series for key, series in (factor_pnl or {}).items() if key in FACTOR_BY_ID}
    if not known:
        return result
    horizons = sorted({FACTOR_BY_ID[key]["liquidity_horizon"] for key in known} | {BASE_HORIZON_DAYS})
    es_by_horizon: dict[int, float] = {}
    for horizon in horizons:
        members = [key for key in known if FACTOR_BY_ID[key]["liquidity_horizon"] >= horizon]
        if horizon == BASE_HORIZON_DAYS:
            subset = values
        else:
            subset = np.sum([np.asarray(known[key], dtype=float) for key in members], axis=0)
        es_by_horizon[horizon] = var_es(subset, confidence, method)[1] * scale
        result["buckets"].append({
            "liquidity_horizon_days": horizon,
            "factors": [FACTOR_BY_ID[key]["label"] for key in members],
            "es_base_horizon": round(es_by_horizon[horizon], 2),
        })
    result["liquidity_adjusted_es"] = round(liquidity_horizon_es(es_by_horizon), 2)
    return result


# ---------------------------------------------------------------------------
# Backtest
# ---------------------------------------------------------------------------

def _clean_series(pnl, dates, factor_pnl) -> tuple[np.ndarray, list[str], dict[str, np.ndarray]]:
    values = np.asarray(pnl, dtype=float)
    if values.ndim != 1 or values.size < 3:
        raise ValueError("pnl must be a list of at least three numbers")
    if not all(isfinite(value) for value in values):
        raise ValueError("pnl values must be finite numbers")
    if dates is None:
        labels = [f"Day {index + 1}" for index in range(values.size)]
    else:
        labels = [str(label) for label in dates]
        if len(labels) != values.size:
            raise ValueError("dates must have the same length as pnl")
    factors: dict[str, np.ndarray] = {}
    for key, series in (factor_pnl or {}).items():
        column = np.asarray(series, dtype=float)
        if column.shape != values.shape:
            raise ValueError(f"factor_pnl[{key}] must have the same length as pnl")
        factors[key] = column
    return values, labels, factors


def backtest_var(
    pnl,
    dates=None,
    confidence: float = 0.99,
    window: int = 250,
    method: str = "historical",
    es_confidence: float = 0.975,
    factor_pnl: dict[str, list[float]] | None = None,
) -> dict:
    """Backtest a rolling one-day VaR against realised P&L.

    Simplified, for analysis and learning; not a regulatory calculation.
    The traffic-light zone is assessed on the most recent 250 backtest days
    (or all of them when fewer are available).
    """
    values, labels, factors = _clean_series(pnl, dates, factor_pnl)
    var_series = rolling_var(values, confidence, window, method)
    realised = values[window:]
    hits = realised < -var_series
    n_obs = int(realised.size)
    n_exceptions = int(hits.sum())
    coverage = 1 - confidence

    windows = sliding_window_view(values, window)[:-1]
    es_series = [var_es(row, es_confidence, method)[1] for row in windows]

    series = [
        {
            "date": labels[window + index],
            "pnl": round(float(realised[index]), 2),
            "var": round(float(var_series[index]), 2),
            "es": round(float(es_series[index]), 2),
            "exception": bool(hits[index]),
        }
        for index in range(n_obs)
    ]
    exceptions = [
        {
            "date": row["date"],
            "index": index,
            "pnl": row["pnl"],
            "var": row["var"],
            "excess": round(-row["pnl"] - row["var"], 2),
            "loss_to_var": round(-row["pnl"] / row["var"], 4) if row["var"] > 0 else None,
        }
        for index, row in enumerate(series) if row["exception"]
    ]

    recent = hits[-250:]
    pof = kupiec_pof(n_obs, n_exceptions, coverage)
    independence = christoffersen_independence(hits)
    conditional = christoffersen_conditional_coverage(hits, coverage)
    latest_factor_pnl = {key: column[-window:].tolist() for key, column in factors.items()}

    return {
        "method": method,
        "confidence": confidence,
        "window": window,
        "n_obs": n_obs,
        "n_exceptions": n_exceptions,
        "expected_exceptions": round(n_obs * coverage, 4),
        "exception_rate": n_exceptions / n_obs,
        "kupiec": pof,
        "independence": independence,
        "conditional_coverage": conditional,
        "traffic_light": basel_traffic_light(int(recent.sum()), int(recent.size), confidence),
        "expected_shortfall": expected_shortfall_summary(
            values[-window:], latest_factor_pnl, es_confidence, method
        ),
        "series": series,
        "exceptions": exceptions,
        "disclaimer": MODEL_DISCLAIMER,
    }


def backtest_sample(
    seed: int = 42,
    days: int = 750,
    confidence: float = 0.99,
    window: int = 250,
    method: str = "historical",
    es_confidence: float = 0.975,
) -> dict:
    """Backtest the bundled synthetic sample book."""
    sample = sample_portfolio(seed, days)
    result = backtest_var(
        sample["pnl"], sample["dates"], confidence, window, method, es_confidence, sample["factor_pnl"]
    )
    result["portfolio"] = {
        "name": sample["name"], "currency": sample["currency"], "seed": seed,
        "disclaimer": sample["disclaimer"],
    }
    return result
