"""Initial margin, potential future exposure and market data helpers.

Product coverage: equity, bond, interest rate swap (irs), credit default swap
(cds), equity option and FX.

Everything here is simplified, for analysis and learning; none of it is a
regulatory calculation or a production margin model. Each function states the
shortcuts it takes.

Series conventions used throughout
- equity, equity_option, fx: a price / rate level series; shocks are relative returns.
- bond, irs: a yield / swap rate series quoted in percent (7.10 means 7.10%);
  shocks are absolute changes in percentage points.
- cds: a spread series quoted in basis points; shocks are absolute changes in bp.
"""

from math import ceil, exp, isfinite, log, sqrt

import numpy as np
from scipy.stats import binom, norm

TRADING_DAYS = 252
PRODUCTS = ("equity", "bond", "irs", "cds", "equity_option", "fx")
RELATIVE_PRODUCTS = ("equity", "equity_option", "fx")
# Divisor that turns a quoted absolute shock into a decimal (percent or basis points).
SHOCK_SCALE = {"bond": 100.0, "irs": 100.0, "cds": 10_000.0}
SIDES = {
    "equity": ("long", "short"),
    "fx": ("long", "short"),
    "bond": ("long", "short"),
    "equity_option": ("long", "short"),
    "irs": ("pay_fixed", "receive_fixed"),
    "cds": ("buy_protection", "sell_protection"),
}
MAX_SIMULATION_CELLS = 4_000_000


# ---------------------------------------------------------------------------
# Small building blocks
# ---------------------------------------------------------------------------

def _series(values, minimum: int = 2, positive: bool = False) -> np.ndarray:
    array = np.asarray(list(values), dtype=float)
    if array.ndim != 1 or array.size < minimum:
        raise ValueError(f"series needs at least {minimum} observations")
    if not np.all(np.isfinite(array)):
        raise ValueError("series must contain only finite numbers")
    if positive and np.any(array <= 0):
        raise ValueError("price series must be strictly positive")
    return array


def _check_product(product: str) -> str:
    if product not in PRODUCTS:
        raise ValueError(f"product must be one of {', '.join(PRODUCTS)}")
    return product


def _check_confidence(confidence: float) -> float:
    if not 0.5 < confidence < 1:
        raise ValueError("confidence must be between 0.5 and 1 (exclusive)")
    return float(confidence)


def _check_mpor(mpor_days: int) -> int:
    if int(mpor_days) != mpor_days or mpor_days < 1:
        raise ValueError("mpor_days must be a positive whole number of business days")
    return int(mpor_days)


def horizon_shocks(series, horizon_days: int = 1, relative: bool = True) -> np.ndarray:
    """Overlapping h-day moves: relative returns s[t+h]/s[t]-1 or absolute changes s[t+h]-s[t]."""
    horizon_days = _check_mpor(horizon_days)
    array = _series(series, minimum=horizon_days + 1, positive=relative)
    if relative:
        return array[horizon_days:] / array[:-horizon_days] - 1.0
    return array[horizon_days:] - array[:-horizon_days]


def bs_price(spot, strike: float, time, rate: float, volatility: float, option_type: str = "call"):
    """Black-Scholes price without dividends; returns intrinsic value at or after expiry.

    Vectorised over spot and time.
    """
    spot = np.asarray(spot, dtype=float)
    time = np.broadcast_to(np.asarray(time, dtype=float), spot.shape)
    call = option_type == "call"
    intrinsic = np.maximum(spot - strike, 0.0) if call else np.maximum(strike - spot, 0.0)
    live = (time > 0) & (spot > 0)
    if volatility <= 0:
        # Zero volatility: discounted forward intrinsic value.
        forward = spot * np.exp(rate * np.maximum(time, 0.0))
        payoff = np.maximum(forward - strike, 0.0) if call else np.maximum(strike - forward, 0.0)
        return np.where(live, payoff * np.exp(-rate * np.maximum(time, 0.0)), intrinsic)
    safe_t = np.where(live, time, 1.0)
    safe_s = np.where(live, spot, 1.0)
    d1 = (np.log(safe_s / strike) + (rate + 0.5 * volatility ** 2) * safe_t) / (volatility * np.sqrt(safe_t))
    d2 = d1 - volatility * np.sqrt(safe_t)
    if call:
        price = safe_s * norm.cdf(d1) - strike * np.exp(-rate * safe_t) * norm.cdf(d2)
    else:
        price = strike * np.exp(-rate * safe_t) * norm.cdf(-d2) - safe_s * norm.cdf(-d1)
    return np.where(live, price, intrinsic)


def bs_delta(spot: float, strike: float, time: float, rate: float, volatility: float, option_type: str = "call") -> float:
    """Black-Scholes delta (no dividends)."""
    if time <= 0 or volatility <= 0:
        in_the_money = spot > strike if option_type == "call" else spot < strike
        return (1.0 if option_type == "call" else -1.0) if in_the_money else 0.0
    d1 = (log(spot / strike) + (rate + 0.5 * volatility ** 2) * time) / (volatility * sqrt(time))
    return float(norm.cdf(d1) if option_type == "call" else norm.cdf(d1) - 1.0)


def bond_price(yield_rate, time, coupon_rate: float, maturity_years: float):
    """Price per 1 of face of an annual-coupon bond, continuously compounded flat yield.

    Coupons fall on maturity and each whole year before it. Cash flows at or
    before `time` are excluded. Vectorised over yield_rate and time.
    """
    yield_rate = np.asarray(yield_rate, dtype=float)
    time = np.asarray(time, dtype=float)
    price = np.zeros(np.broadcast(yield_rate, time).shape)
    payment = float(maturity_years)
    first = True
    while payment > 1e-9:
        cash = coupon_rate + (1.0 if first else 0.0)
        tau = payment - time
        price = price + np.where(tau > 1e-9, cash * np.exp(-yield_rate * np.maximum(tau, 0.0)), 0.0)
        payment -= 1.0
        first = False
    return price


def swap_annuity(rate, time, maturity_years: float, payments_per_year: int = 1):
    """Present value of 1 per year paid on the remaining fixed dates, flat curve at `rate`."""
    rate = np.asarray(rate, dtype=float)
    time = np.asarray(time, dtype=float)
    annuity = np.zeros(np.broadcast(rate, time).shape)
    accrual = 1.0 / payments_per_year
    payment = float(maturity_years)
    while payment > 1e-9:
        tau = payment - time
        annuity = annuity + np.where(tau > 1e-9, accrual * np.exp(-rate * np.maximum(tau, 0.0)), 0.0)
        payment -= accrual
    return annuity


def risky_annuity(spread, time, maturity_years: float, rate: float, recovery: float):
    """Continuous-premium risky annuity with flat hazard rate spread / (1 - recovery)."""
    spread = np.asarray(spread, dtype=float)
    tau = np.maximum(maturity_years - np.asarray(time, dtype=float), 0.0)
    intensity = rate + spread / (1.0 - recovery)
    safe = np.where(np.abs(intensity) > 1e-12, intensity, 1.0)
    return np.where(np.abs(intensity) > 1e-12, (1.0 - np.exp(-safe * tau)) / safe, tau)


# ---------------------------------------------------------------------------
# Market data analysis
# ---------------------------------------------------------------------------

def analyze_market_data(series, kind: str = "price", window: int = 20) -> dict:
    """Returns, rolling volatility and worst 1/5/10-day moves of a historical series.

    kind="price" uses relative returns (reported in percent); kind="rate" uses
    absolute changes in the units of the series (percentage points or bp).
    Rolling volatility is the sample standard deviation of daily moves over
    `window` observations, annualised with sqrt(252).
    """
    if kind not in ("price", "rate"):
        raise ValueError("kind must be 'price' or 'rate'")
    relative = kind == "price"
    array = _series(series, minimum=3, positive=relative)
    scale = 100.0 if relative else 1.0
    daily = horizon_shocks(array, 1, relative) * scale
    if window < 2:
        raise ValueError("window must be at least 2")
    window = int(min(window, daily.size))

    rolling: list[float | None] = [None] * daily.size
    for end in range(window, daily.size + 1):
        rolling[end - 1] = round(float(np.std(daily[end - window:end], ddof=1) * sqrt(TRADING_DAYS)), 6)

    worst_moves = []
    for horizon in (1, 5, 10):
        if array.size <= horizon:
            continue
        moves = horizon_shocks(array, horizon, relative) * scale
        low, high = int(np.argmin(moves)), int(np.argmax(moves))
        worst_moves.append({
            "horizon_days": horizon,
            "observations": int(moves.size),
            "worst_down": round(float(moves[low]), 6),
            "worst_down_start_index": low,
            "worst_down_end_index": low + horizon,
            "worst_up": round(float(moves[high]), 6),
            "worst_up_start_index": high,
            "worst_up_end_index": high + horizon,
            "quantile_1pct": round(float(np.quantile(moves, 0.01)), 6),
            "quantile_99pct": round(float(np.quantile(moves, 0.99)), 6),
        })

    daily_vol = float(np.std(daily, ddof=1)) if daily.size > 1 else 0.0
    return {
        "kind": kind,
        "unit": "percent" if relative else "series units",
        "observations": int(array.size),
        "first": float(array[0]),
        "last": float(array[-1]),
        "minimum": float(array.min()),
        "maximum": float(array.max()),
        "mean_daily_move": round(float(daily.mean()), 6),
        "daily_volatility": round(daily_vol, 6),
        "annualised_volatility": round(daily_vol * sqrt(TRADING_DAYS), 6),
        "window": window,
        "returns": [round(float(value), 6) for value in daily],
        "rolling_volatility": rolling,
        "worst_moves": worst_moves,
    }


# ---------------------------------------------------------------------------
# Volatility calibration
# ---------------------------------------------------------------------------

def estimate_volatility(daily_moves, method: str = "equal", ewma_lambda: float = 0.94) -> float:
    """Daily volatility of a series of daily moves.

    equal: sample standard deviation (ddof=1).
    ewma:  zero-mean exponentially weighted volatility, weights proportional to
           lambda**age (most recent move has age 0), normalised to sum to one.
    """
    moves = _series(daily_moves, minimum=2)
    if method == "equal":
        return float(np.std(moves, ddof=1))
    if method == "ewma":
        if not 0 < ewma_lambda < 1:
            raise ValueError("ewma_lambda must be between 0 and 1")
        weights = ewma_lambda ** np.arange(moves.size - 1, -1, -1)
        return float(sqrt(np.sum(weights * moves ** 2) / np.sum(weights)))
    raise ValueError("method must be 'equal' or 'ewma'")


def stressed_window(daily_moves, window: int) -> tuple[int, int]:
    """Start and end (exclusive) index of the `window`-long run of daily moves with the highest volatility."""
    moves = _series(daily_moves, minimum=2)
    window = int(min(max(window, 2), moves.size))
    best_start, best_vol = 0, -1.0
    for start in range(0, moves.size - window + 1):
        vol = float(np.std(moves[start:start + window], ddof=1))
        if vol > best_vol:
            best_start, best_vol = start, vol
    return best_start, best_start + window


# ---------------------------------------------------------------------------
# Initial margin
# ---------------------------------------------------------------------------

def _position(position: dict) -> dict:
    product = _check_product(position.get("product", "equity"))
    side = position.get("side") or SIDES[product][0]
    if side not in SIDES[product]:
        raise ValueError(f"{product}: side must be one of {', '.join(SIDES[product])}")
    notional = float(position.get("notional", 0))
    if not isfinite(notional) or notional <= 0:
        raise ValueError(f"{product}: notional must be greater than zero")
    clean = {"product": product, "side": side, "notional": notional,
             "label": str(position.get("label") or product)}
    if product in SHOCK_SCALE:
        duration = float(position.get("duration") or 0)
        if not isfinite(duration) or duration <= 0:
            raise ValueError(f"{product}: duration must be greater than zero")
        clean["duration"] = duration
    if product == "equity_option":
        option_type = position.get("option_type", "call")
        if option_type not in ("call", "put"):
            raise ValueError("option_type must be 'call' or 'put'")
        strike = float(position.get("strike") or 0)
        expiry = float(position.get("expiry_years") or 0)
        volatility = float(position.get("volatility") or 0)
        if strike <= 0 or expiry <= 0 or volatility <= 0:
            raise ValueError("equity_option: strike, expiry_years and volatility must be greater than zero")
        clean.update(option_type=option_type, strike=strike, expiry_years=expiry,
                     volatility=volatility, rate=float(position.get("rate") or 0.0))
    return clean


def _direction(position: dict) -> float:
    """+1 when the position gains from a positive shock to its series (before option delta)."""
    product, side = position["product"], position["side"]
    if product == "bond":
        return -1.0 if side == "long" else 1.0          # long bond loses when yields rise
    if product == "irs":
        return 1.0 if side == "pay_fixed" else -1.0      # fixed payer gains when rates rise
    if product == "cds":
        return 1.0 if side == "buy_protection" else -1.0  # protection buyer gains when spreads widen
    return 1.0 if side == "long" else -1.0


def linear_sensitivity(position: dict, reference_level: float) -> float:
    """P&L per unit of shock (relative return, or one quoted unit for rate/spread series).

    Options use the delta-normal approximation: quantity x delta x spot.
    """
    position = _position(position)
    product = position["product"]
    if product == "equity_option":
        delta = bs_delta(reference_level, position["strike"], position["expiry_years"],
                         position["rate"], position["volatility"], position["option_type"])
        return _direction(position) * position["notional"] * delta * reference_level
    if product in SHOCK_SCALE:
        return _direction(position) * position["notional"] * position["duration"] / SHOCK_SCALE[product]
    return _direction(position) * position["notional"]


def scenario_pnl(position: dict, shocks, reference_level: float, horizon_days: int) -> np.ndarray:
    """P&L of a position under each shock, holding the position constant.

    - equity, fx: notional (market value) x relative return.
    - bond, irs, cds: notional x duration x change in yield / rate / spread
      (first-order; no convexity, carry or default).
    - equity_option: full Black-Scholes revaluation at the shocked spot with
      `horizon_days` of time decay; implied volatility and rates held constant.
      `notional` is the number of underlying units and the spot is `reference_level`.
    """
    position = _position(position)
    shocks = np.asarray(shocks, dtype=float)
    if position["product"] == "equity_option":
        args = (position["strike"],)
        tail = (position["rate"], position["volatility"], position["option_type"])
        today = bs_price(reference_level, *args, position["expiry_years"], *tail)
        shocked = bs_price(reference_level * (1.0 + shocks), *args,
                           max(position["expiry_years"] - horizon_days / TRADING_DAYS, 0.0), *tail)
        return _direction(position) * position["notional"] * (shocked - today)
    return linear_sensitivity(position, reference_level) * shocks


def historical_im(pnl, confidence: float = 0.99) -> float:
    """Historical-simulation margin: the loss at the (1 - confidence) quantile of scenario P&L, floored at zero.

    Uses numpy's default linear interpolation between order statistics.
    """
    confidence = _check_confidence(confidence)
    values = _series(pnl, minimum=1)
    return max(-float(np.quantile(values, 1.0 - confidence)), 0.0)


def parametric_im(daily_pnl_volatility: float, mpor_days: int = 10, confidence: float = 0.99) -> float:
    """Normal, zero-mean margin: z(confidence) x daily P&L volatility x sqrt(MPOR days)."""
    confidence = _check_confidence(confidence)
    return float(norm.ppf(confidence) * daily_pnl_volatility * sqrt(_check_mpor(mpor_days)))


def _prepare(position: dict, series, lookback: int | None, mpor_days: int) -> tuple[dict, np.ndarray, bool]:
    clean = _position(position)
    relative = clean["product"] in RELATIVE_PRODUCTS
    array = _series(series, minimum=mpor_days + 2, positive=relative)
    if lookback is not None:
        if lookback < mpor_days + 1:
            raise ValueError("lookback must be longer than the margin period of risk")
        array = array[-(int(lookback) + 1):]
    return clean, array, relative


def calculate_im(positions: list[dict], mpor_days: int = 10, confidence: float = 0.99,
                 lookback: int | None = None) -> dict:
    """Historical-simulation and parametric IM per position and for the portfolio.

    Each position carries its own `series`. For the portfolio the series are
    aligned on their most recent observations (trimmed to the shortest), the
    scenario P&Ls are added date by date and the same quantile is taken, so
    offsetting positions reduce margin. `lookback` is the number of daily
    moves used (all available history when omitted).
    """
    mpor_days = _check_mpor(mpor_days)
    confidence = _check_confidence(confidence)
    if not positions:
        raise ValueError("at least one position is required")
    prepared = [_prepare(position, position.get("series", []), lookback, mpor_days) for position in positions]
    common = min(array.size for _, array, _ in prepared)

    rows, total_pnl, total_daily = [], 0.0, 0.0
    for clean, array, relative in prepared:
        level = float(array[-1])
        pnl = scenario_pnl(clean, horizon_shocks(array, mpor_days, relative), level, mpor_days)
        sensitivity = linear_sensitivity(clean, level)
        daily = horizon_shocks(array, 1, relative)
        daily_pnl = sensitivity * daily
        trimmed = array[-common:]
        total_pnl = total_pnl + scenario_pnl(clean, horizon_shocks(trimmed, mpor_days, relative), level, mpor_days)
        total_daily = total_daily + sensitivity * horizon_shocks(trimmed, 1, relative)
        rows.append({
            "label": clean["label"], "product": clean["product"], "side": clean["side"],
            "notional": clean["notional"], "reference_level": level,
            "observations": int(array.size), "scenarios": int(pnl.size),
            "daily_volatility": round(float(np.std(daily, ddof=1)) * (100.0 if relative else 1.0), 6),
            "volatility_unit": "percent" if relative else ("bp" if clean["product"] == "cds" else "percentage points"),
            "sensitivity": round(sensitivity, 4),
            "historical_im": round(historical_im(pnl, confidence), 2),
            "parametric_im": round(parametric_im(float(np.std(daily_pnl, ddof=1)), mpor_days, confidence), 2),
            "worst_scenario_pnl": round(float(pnl.min()), 2),
        })

    portfolio_hist = historical_im(total_pnl, confidence)
    portfolio_param = parametric_im(float(np.std(total_daily, ddof=1)), mpor_days, confidence)
    standalone_hist = sum(row["historical_im"] for row in rows)
    standalone_param = sum(row["parametric_im"] for row in rows)
    return {
        "mpor_days": mpor_days, "confidence": confidence, "lookback": lookback,
        "positions": rows,
        "portfolio": {
            "scenarios": int(np.size(total_pnl)),
            "historical_im": round(portfolio_hist, 2),
            "parametric_im": round(portfolio_param, 2),
            "standalone_historical_im": round(standalone_hist, 2),
            "standalone_parametric_im": round(standalone_param, 2),
            "historical_diversification_benefit": round(standalone_hist - portfolio_hist, 2),
            "parametric_diversification_benefit": round(standalone_param - portfolio_param, 2),
            "worst_scenario_pnl": round(float(np.min(total_pnl)), 2),
        },
        "method_note": (
            "Simplified, for analysis and learning; not a regulatory calculation. Historical IM is the loss "
            "quantile of overlapping MPOR-day scenario P&L with the position held constant. Parametric IM "
            "assumes normal, zero-mean daily P&L scaled by the square root of time; options use delta only."
        ),
    }


def calibration_comparison(position: dict, series, mpor_days: int = 10, confidence: float = 0.99,
                           lookbacks: tuple[int, ...] | list[int] = (125, 250, 500),
                           ewma_lambda: float = 0.94, stress_window: int = 250) -> dict:
    """IM for one position under different calibrations of the same history.

    Rows: each look-back window that fits, full history, EWMA volatility
    (parametric only) and the stressed period (the `stress_window`-long run of
    daily moves with the highest volatility in the series).
    """
    mpor_days = _check_mpor(mpor_days)
    confidence = _check_confidence(confidence)
    clean, array, relative = _prepare(position, series, None, mpor_days)
    level = float(array[-1])
    sensitivity = linear_sensitivity(clean, level)
    daily = horizon_shocks(array, 1, relative)
    display = 100.0 if relative else 1.0

    def row(label: str, calibration: str, start: int, end: int) -> dict:
        """Calibrate on daily moves [start, end), i.e. series observations [start, end]."""
        window = array[start:end + 1]
        moves = daily[start:end]
        vol = estimate_volatility(moves)
        pnl = scenario_pnl(clean, horizon_shocks(window, mpor_days, relative), level, mpor_days)
        return {
            "label": label, "calibration": calibration, "start_index": start, "end_index": end,
            "daily_moves": int(moves.size),
            "daily_volatility": round(vol * display, 6),
            "annualised_volatility": round(vol * sqrt(TRADING_DAYS) * display, 6),
            "parametric_im": round(parametric_im(abs(sensitivity) * vol, mpor_days, confidence), 2),
            "historical_im": round(historical_im(pnl, confidence), 2),
        }

    rows = []
    for lookback in sorted({int(value) for value in lookbacks}):
        if mpor_days < lookback < daily.size:
            rows.append(row(f"Last {lookback} days", "lookback", daily.size - lookback, daily.size))
    rows.append(row(f"Full history ({daily.size} days)", "full", 0, daily.size))

    ewma_vol = estimate_volatility(daily, "ewma", ewma_lambda)
    rows.append({
        "label": f"EWMA (lambda {ewma_lambda:g})", "calibration": "ewma", "start_index": 0, "end_index": int(daily.size),
        "daily_moves": int(daily.size),
        "daily_volatility": round(ewma_vol * display, 6),
        "annualised_volatility": round(ewma_vol * sqrt(TRADING_DAYS) * display, 6),
        "parametric_im": round(parametric_im(abs(sensitivity) * ewma_vol, mpor_days, confidence), 2),
        "historical_im": None,
    })

    if daily.size > mpor_days + 1:
        size = int(min(max(stress_window, mpor_days + 1), daily.size))
        start, end = stressed_window(daily, size)
        rows.append(row(f"Stressed period ({size} days from observation {start})", "stressed", start, end))

    return {
        "product": clean["product"], "side": clean["side"], "notional": clean["notional"],
        "mpor_days": mpor_days, "confidence": confidence, "reference_level": level,
        "sensitivity": round(sensitivity, 4),
        "volatility_unit": "percent" if relative else ("bp" if clean["product"] == "cds" else "percentage points"),
        "rows": rows,
        "method_note": (
            "Simplified, for analysis and learning; not a regulatory calculation. Every row margins the same "
            "position at today's level; only the slice of history used for calibration changes."
        ),
    }


def backtest_im(position: dict, series, mpor_days: int = 10, confidence: float = 0.99, lookback: int = 250,
                method: str = "historical", non_overlapping: bool = False) -> dict:
    """Rolling out-of-sample IM backtest for one constant position.

    On each test day t the margin is calibrated on the `lookback` daily moves
    ending at t, then compared with the P&L realised from t to t + MPOR. An
    exception is a realised loss larger than the margin. Historical
    calibration uses only MPOR-day scenarios that are complete by day t.

    Overlapping test windows (the default) give more observations but serially
    dependent exceptions; with non_overlapping=True test days are MPOR apart
    and a binomial tail probability is reported.
    """
    mpor_days = _check_mpor(mpor_days)
    confidence = _check_confidence(confidence)
    if method not in ("historical", "parametric"):
        raise ValueError("method must be 'historical' or 'parametric'")
    clean, array, relative = _prepare(position, series, None, mpor_days)
    if lookback < mpor_days + 1:
        raise ValueError("lookback must be longer than the margin period of risk")
    level = float(array[-1])
    sensitivity = linear_sensitivity(clean, level)
    daily = horizon_shocks(array, 1, relative)                     # daily[j]: move from j to j+1
    pnl = scenario_pnl(clean, horizon_shocks(array, mpor_days, relative), level, mpor_days)  # pnl[i]: i -> i+h
    first, last = int(lookback), pnl.size - 1
    if first > last:
        raise ValueError(
            f"series too short: need at least {lookback + mpor_days + 1} observations for this look-back and MPOR"
        )

    points, exceptions, margins, worst_excess = [], 0, [], 0.0
    for day in range(first, last + 1, mpor_days if non_overlapping else 1):
        if method == "historical":
            margin = historical_im(pnl[day - lookback:day - mpor_days + 1], confidence)
        else:
            vol = float(np.std(daily[day - lookback:day], ddof=1))
            margin = parametric_im(abs(sensitivity) * vol, mpor_days, confidence)
        realised = float(pnl[day])
        breach = -realised > margin
        exceptions += int(breach)
        worst_excess = max(worst_excess, -realised - margin)
        margins.append(margin)
        points.append({"index": day, "im": round(margin, 2), "realised_pnl": round(realised, 2), "exception": breach})

    observations = len(points)
    expected_rate = 1.0 - confidence
    rate = exceptions / observations
    p_value = float(binom.sf(exceptions - 1, observations, expected_rate)) if non_overlapping else None
    if exceptions <= ceil(observations * expected_rate):
        verdict = "Exceptions are in line with the target confidence level."
    else:
        verdict = "More exceptions than the confidence level implies; the calibration looks too light for this history."
    return {
        "product": clean["product"], "method": method, "mpor_days": mpor_days, "confidence": confidence,
        "lookback": int(lookback), "non_overlapping": non_overlapping,
        "observations": observations, "exceptions": exceptions,
        "exception_rate": round(rate, 6), "expected_rate": round(expected_rate, 6),
        "expected_exceptions": round(observations * expected_rate, 2),
        "average_im": round(float(np.mean(margins)), 2),
        "max_im": round(float(np.max(margins)), 2),
        "worst_excess_loss": round(worst_excess, 2),
        "binomial_p_value": None if p_value is None else round(p_value, 6),
        "verdict": verdict,
        "points": points,
        "method_note": (
            "Simplified, for analysis and learning; not a regulatory backtest. The position is held constant "
            "at today's level. Overlapping MPOR windows make exceptions cluster, so the exception rate is "
            "indicative; the binomial probability is only reported for non-overlapping windows."
        ),
    }


# ---------------------------------------------------------------------------
# Potential future exposure
# ---------------------------------------------------------------------------

PFE_DEFAULTS = {
    "equity": {"spot": 100.0, "quantity": 10_000.0, "volatility": 0.25, "drift": 0.0, "side": "long"},
    "fx": {"spot": 83.0, "notional_foreign": 1_000_000.0, "strike": None, "domestic_rate": 0.065,
           "foreign_rate": 0.045, "volatility": 0.06, "maturity_years": 1.0, "side": "long"},
    "bond": {"notional": 10_000_000.0, "coupon_rate": 0.07, "yield_rate": 0.07, "maturity_years": 5.0,
             "yield_vol_bp": 90.0, "side": "long"},
    "irs": {"notional": 10_000_000.0, "swap_rate": 0.065, "fixed_rate": None, "maturity_years": 5.0,
            "payments_per_year": 1, "rate_vol_bp": 90.0, "side": "pay_fixed"},
    "cds": {"notional": 10_000_000.0, "spread_bp": 120.0, "contract_spread_bp": None, "spread_volatility": 0.6,
            "recovery": 0.4, "rate": 0.05, "maturity_years": 5.0, "side": "buy_protection"},
    "equity_option": {"spot": 100.0, "strike": 100.0, "quantity": 10_000.0, "volatility": 0.25, "rate": 0.05,
                      "expiry_years": 1.0, "option_type": "call", "side": "long"},
}

PFE_MODEL_NOTES = {
    "equity": (
        "Equity price follows geometric Brownian motion. Exposure is the mark-to-market gain versus the "
        "inception price on a financed position (for example an equity swap or forward): quantity x (S(t) - S(0)).",
        ["Constant volatility and drift; no dividends, jumps or financing cost."],
    ),
    "fx": (
        "FX forward to buy (long) or sell (short) the foreign currency at the strike. Spot follows geometric "
        "Brownian motion with drift equal to the interest rate differential; value is the discounted "
        "difference between the forward rate and the strike.",
        ["Constant volatility and flat, deterministic interest rates in both currencies."],
    ),
    "bond": (
        "Bond position financed at inception (for example a repo or forward purchase). The flat yield follows "
        "a normal random walk; exposure is the price gain versus the unchanged-yield price at the same date.",
        ["Flat continuously compounded yield, annual coupons, normal yield volatility with no mean reversion.",
         "No issuer default or credit spread dynamics."],
    ),
    "irs": (
        "Interest rate swap valued as (swap rate - fixed rate) x annuity x notional for the fixed payer. "
        "The swap rate follows a normal random walk and discounts a flat curve.",
        ["Single-factor flat curve, normal rate volatility with no mean reversion.",
         "Accrued interest and floating-leg reset risk between payment dates are ignored.",
         "The collateralised profile spikes after each payment date: the value jumps when a coupon settles "
         "and collateral only catches up one margin period later."],
    ),
    "cds": (
        "Credit default swap valued as (market spread - contract spread) x risky annuity x notional for the "
        "protection buyer. The spread follows a driftless lognormal process with a flat hazard rate.",
        ["Spread risk only: the reference entity's default (jump-to-default) is not simulated.",
         "Continuous premium approximation, constant recovery and discount rate."],
    ),
    "equity_option": (
        "European equity option revalued with Black-Scholes along geometric Brownian motion paths of the "
        "underlying. A purchased option carries exposure equal to its value; a sold option carries none "
        "once the premium has been received.",
        ["Constant implied volatility equal to the simulation volatility; risk-neutral drift; no dividends."],
    ),
}


# Bounds that keep the per-coupon revaluation loops short.
MAX_TENOR_YEARS = 50
PAYMENT_FREQUENCIES = (1, 2, 4, 12)


def _pfe_params(product: str, params: dict | None) -> dict:
    merged = dict(PFE_DEFAULTS[product])
    for key, value in (params or {}).items():
        if key not in merged:
            raise ValueError(f"{product}: unknown parameter '{key}'")
        if value is not None:
            merged[key] = value
    if merged["side"] not in SIDES[product]:
        raise ValueError(f"{product}: side must be one of {', '.join(SIDES[product])}")
    for key, value in merged.items():
        if key in ("side", "option_type") or value is None:
            continue
        if not isfinite(float(value)):
            raise ValueError(f"{product}: {key} must be a finite number")
        merged[key] = float(value)
    positive = {
        "equity": ("spot", "quantity"), "fx": ("spot", "notional_foreign", "maturity_years"),
        "bond": ("notional", "maturity_years"), "irs": ("notional", "maturity_years", "payments_per_year"),
        "cds": ("notional", "spread_bp", "maturity_years"),
        "equity_option": ("spot", "strike", "quantity", "expiry_years"),
    }[product]
    for key in positive:
        if merged[key] <= 0:
            raise ValueError(f"{product}: {key} must be greater than zero")
    for key in ("volatility", "yield_vol_bp", "rate_vol_bp", "spread_volatility"):
        if key in merged and merged[key] < 0:
            raise ValueError(f"{product}: {key} cannot be negative")
    if product == "cds" and not 0 <= merged["recovery"] < 1:
        raise ValueError("cds: recovery must be in [0, 1)")
    if product == "equity_option" and merged["option_type"] not in ("call", "put"):
        raise ValueError("equity_option: option_type must be 'call' or 'put'")
    for key in ("maturity_years", "expiry_years"):
        if key in merged and merged[key] > MAX_TENOR_YEARS:
            raise ValueError(f"{product}: {key} cannot exceed {MAX_TENOR_YEARS} years")
    if product == "irs":
        if merged["payments_per_year"] not in PAYMENT_FREQUENCIES:
            raise ValueError("irs: payments_per_year must be one of "
                             + ", ".join(str(n) for n in PAYMENT_FREQUENCIES))
        merged["payments_per_year"] = int(merged["payments_per_year"])
    return merged


def _gbm_paths(start: float, drift: float, volatility: float, steps: np.ndarray, normals: np.ndarray) -> np.ndarray:
    increments = (drift - 0.5 * volatility ** 2) * steps + volatility * np.sqrt(steps) * normals
    log_paths = np.concatenate([np.zeros((normals.shape[0], 1)), np.cumsum(increments, axis=1)], axis=1)
    return start * np.exp(log_paths)


def _normal_paths(start: float, volatility: float, steps: np.ndarray, normals: np.ndarray) -> np.ndarray:
    increments = volatility * np.sqrt(steps) * normals
    return start + np.concatenate([np.zeros((normals.shape[0], 1)), np.cumsum(increments, axis=1)], axis=1)


def _mtm_paths(product: str, p: dict, times: np.ndarray, normals: np.ndarray) -> np.ndarray:
    """Mark-to-market of the trade to us on every path and grid date (paths x dates)."""
    steps = np.diff(times)
    first_side = p["side"] == SIDES[product][0]   # long / pay_fixed / buy_protection
    sign = 1.0 if first_side else -1.0
    if product == "equity":
        spot = _gbm_paths(p["spot"], p["drift"], p["volatility"], steps, normals)
        return sign * p["quantity"] * (spot - p["spot"])
    if product == "fx":
        carry = p["domestic_rate"] - p["foreign_rate"]
        strike = p["strike"] if p["strike"] is not None else p["spot"] * exp(carry * p["maturity_years"])
        spot = _gbm_paths(p["spot"], carry, p["volatility"], steps, normals)
        remaining = np.maximum(p["maturity_years"] - times, 0.0)
        forward = spot * np.exp(carry * remaining)
        return sign * p["notional_foreign"] * (forward - strike) * np.exp(-p["domestic_rate"] * remaining)
    if product == "bond":
        yields = _normal_paths(p["yield_rate"], p["yield_vol_bp"] / 1e4, steps, normals)
        shocked = bond_price(yields, times, p["coupon_rate"], p["maturity_years"])
        unchanged = bond_price(p["yield_rate"], times, p["coupon_rate"], p["maturity_years"])
        return sign * p["notional"] * (shocked - unchanged)
    if product == "irs":
        fixed = p["fixed_rate"] if p["fixed_rate"] is not None else p["swap_rate"]
        rates = _normal_paths(p["swap_rate"], p["rate_vol_bp"] / 1e4, steps, normals)
        annuity = swap_annuity(rates, times, p["maturity_years"], p["payments_per_year"])
        return sign * p["notional"] * (rates - fixed) * annuity
    if product == "cds":
        contract = (p["contract_spread_bp"] if p["contract_spread_bp"] is not None else p["spread_bp"]) / 1e4
        spreads = _gbm_paths(p["spread_bp"] / 1e4, 0.0, p["spread_volatility"], steps, normals)
        annuity = risky_annuity(spreads, times, p["maturity_years"], p["rate"], p["recovery"])
        return sign * p["notional"] * (spreads - contract) * annuity
    spot = _gbm_paths(p["spot"], p["rate"], p["volatility"], steps, normals)
    remaining = np.broadcast_to(p["expiry_years"] - times, spot.shape)
    value = bs_price(spot, p["strike"], remaining, p["rate"], p["volatility"], p["option_type"])
    return sign * p["quantity"] * value


def simulate_pfe(product: str, params: dict | None = None, horizon_years: float | None = None,
                 quantile: float = 0.95, paths: int = 5000, seed: int | None = None,
                 mpor_days: int = 10, threshold: float = 0.0, initial_margin: float = 0.0) -> dict:
    """Monte Carlo expected exposure and PFE profile for one trade, with and without collateral.

    The time grid steps in units of the margin period of risk (MPOR business
    days / 252 years), so the collateral lag is exactly one grid step.

    Uncollateralised exposure: E(t) = max(V(t), 0).
    Collateralised exposure:   E(t) = max(V(t) - C(t) - initial_margin, 0), where
    the variation margin held is based on the value one MPOR earlier,
    C(t) = max(V(t - MPOR) - threshold, 0) - max(-V(t - MPOR) - threshold, 0).

    Expected exposure is the mean and PFE the `quantile` of E(t) across paths.
    Passing `seed` makes the run reproducible. Simplified, for analysis and
    learning; not a regulatory calculation.
    """
    _check_product(product)
    p = _pfe_params(product, params)
    mpor_days = _check_mpor(mpor_days)
    if not 0.5 <= quantile < 1:
        raise ValueError("quantile must be in [0.5, 1)")
    if int(paths) != paths or not 100 <= paths <= 50_000:
        raise ValueError("paths must be a whole number between 100 and 50000")
    if threshold < 0 or initial_margin < 0:
        raise ValueError("threshold and initial_margin cannot be negative")

    maturity = p.get("maturity_years") or p.get("expiry_years")
    horizon = float(horizon_years) if horizon_years else float(maturity or 1.0)
    if horizon <= 0:
        raise ValueError("horizon_years must be greater than zero")
    if maturity:
        horizon = min(horizon, float(maturity))

    step = mpor_days / TRADING_DAYS
    count = max(int(ceil(horizon / step - 1e-9)), 1)
    if count * paths > MAX_SIMULATION_CELLS:
        raise ValueError("simulation too large: reduce paths, shorten the horizon or lengthen the margin period of risk")
    times = np.minimum(np.arange(count + 1) * step, horizon)

    normals = np.random.default_rng(seed).standard_normal((int(paths), count))
    value = _mtm_paths(product, p, times, normals)

    lagged = np.concatenate([value[:, :1], value[:, :-1]], axis=1)
    collateral = np.maximum(lagged - threshold, 0.0) - np.maximum(-lagged - threshold, 0.0)
    exposure = np.maximum(value, 0.0)
    collateralised = np.maximum(value - collateral - initial_margin, 0.0)

    def profile(matrix: np.ndarray) -> dict:
        expected = matrix.mean(axis=0)
        pfe = np.quantile(matrix, quantile, axis=0)
        peak = int(np.argmax(pfe))
        return {
            "expected_exposure": [round(float(v), 2) for v in expected],
            "pfe": [round(float(v), 2) for v in pfe],
            "peak_pfe": round(float(pfe[peak]), 2),
            "peak_pfe_time": round(float(times[peak]), 6),
            "epe": round(float(np.trapezoid(expected, times) / horizon), 2),
            "max_expected_exposure": round(float(expected.max()), 2),
        }

    description, simplifications = PFE_MODEL_NOTES[product]
    return {
        "product": product, "parameters": p, "quantile": quantile, "paths": int(paths), "seed": seed,
        "mpor_days": mpor_days, "threshold": threshold, "initial_margin": initial_margin,
        "horizon_years": horizon, "grid_step_years": round(step, 6),
        "times": [round(float(t), 6) for t in times],
        "initial_value": round(float(value[0, 0]), 2),
        "expected_mtm": [round(float(v), 2) for v in value.mean(axis=0)],
        "uncollateralised": profile(exposure),
        "collateralised": profile(collateralised),
        "model": description,
        "simplifications": simplifications + [
            "Variation margin is exchanged in full with a lag of one margin period of risk; no minimum "
            "transfer amount, rounding, disputes or collateral haircuts.",
            "Simplified, for analysis and learning; not a regulatory calculation.",
        ],
    }


# ---------------------------------------------------------------------------
# Synthetic sample series
# ---------------------------------------------------------------------------

SAMPLE_SERIES = {
    "equity_index": {"label": "Sample equity index level", "product": "equity", "kind": "price", "start": 1000.0, "vol": 0.011, "seed": 11},
    "fx_usdinr": {"label": "Sample USD/INR rate", "product": "fx", "kind": "price", "start": 83.0, "vol": 0.0025, "seed": 12},
    "fx_usdcny": {"label": "Sample USD/CNY rate", "product": "fx", "kind": "price", "start": 7.2, "vol": 0.0022, "seed": 13},
    "fx_usdjpy": {"label": "Sample USD/JPY rate", "product": "fx", "kind": "price", "start": 150.0, "vol": 0.006, "seed": 14},
    "fx_usdkrw": {"label": "Sample USD/KRW rate", "product": "fx", "kind": "price", "start": 1350.0, "vol": 0.005, "seed": 15},
    "bond_yield": {"label": "Sample 10-year government bond yield (%)", "product": "bond", "kind": "rate", "start": 7.0, "vol": 0.045, "seed": 16},
    "swap_rate": {"label": "Sample 5-year swap rate (%)", "product": "irs", "kind": "rate", "start": 6.5, "vol": 0.05, "seed": 17},
    "cds_spread": {"label": "Sample 5-year CDS spread (bp)", "product": "cds", "kind": "rate", "start": 120.0, "vol": 3.0, "seed": 18},
}


def sample_series(name: str = "equity_index", observations: int = 750) -> dict:
    """Deterministic synthetic series with a high-volatility episode in the middle.

    Generated from a fixed random seed purely for demonstration: it is not
    market data and does not describe any real instrument.
    """
    if name not in SAMPLE_SERIES:
        raise ValueError(f"unknown sample series; choose one of {', '.join(SAMPLE_SERIES)}")
    if not 60 <= observations <= 2500:
        raise ValueError("observations must be between 60 and 2500")
    spec = SAMPLE_SERIES[name]
    rng = np.random.default_rng(spec["seed"])
    moves = rng.standard_normal(observations - 1) * spec["vol"]
    start, end = int(observations * 0.40), int(observations * 0.55)
    moves[start:end] *= 3.0                                   # stressed episode
    if spec["kind"] == "price":
        values = spec["start"] * np.exp(np.concatenate([[0.0], np.cumsum(moves)]))
    else:
        values = np.maximum(spec["start"] + np.concatenate([[0.0], np.cumsum(moves)]), spec["start"] * 0.1)
    return {
        "name": name, "label": spec["label"], "product": spec["product"], "kind": spec["kind"],
        "series": [round(float(value), 4) for value in values],
        "stressed_episode": {"start_index": start, "end_index": end},
        "disclaimer": "Synthetic series generated from a fixed random seed for illustration; not market data.",
    }


def list_sample_series() -> list[dict]:
    return [{"name": name, "label": spec["label"], "product": spec["product"], "kind": spec["kind"]}
            for name, spec in SAMPLE_SERIES.items()]
