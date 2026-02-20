"""Risk methodology: model performance monitoring for a VaR model.

Builds a report over a backtest window: coverage tests, exception analysis
(clustering, largest breaches, risk factor drivers), stability metrics, an
overall green / amber / red status and plain-English findings.

Simplified, for analysis and learning; not a regulatory calculation.
"""

import numpy as np

from app.services.risk_methodology import (
    FACTOR_BY_ID, MODEL_DISCLAIMER, backtest_var, sample_portfolio,
)

CLUSTER_WINDOW_DAYS = 10
STABILITY_PERIODS = 4


def clustering_metrics(hits, cluster_window: int = CLUSTER_WINDOW_DAYS) -> dict:
    """How bunched the exceptions are.

    consecutive_pairs counts exceptions that directly follow another one.
    max_in_window is the largest number of exceptions in any run of
    `cluster_window` consecutive days. Gaps are in trading days.
    """
    flags = np.asarray([1 if hit else 0 for hit in hits])
    positions = np.flatnonzero(flags)
    gaps = np.diff(positions)
    width = min(cluster_window, flags.size)
    max_in_window = int(np.convolve(flags, np.ones(width, dtype=int), mode="valid").max()) if flags.size else 0
    return {
        "consecutive_pairs": int(np.sum(gaps == 1)),
        "max_in_window": max_in_window,
        "cluster_window_days": cluster_window,
        "mean_gap_days": float(gaps.mean()) if gaps.size else None,
        "min_gap_days": int(gaps.min()) if gaps.size else None,
    }


def exception_drivers(factor_pnl_row: dict[str, float], top: int = 3) -> list[dict]:
    """The risk factors that lost the most on one day, largest loss first.

    share_of_loss_pct is the factor's loss as a share of the day's net loss.
    """
    total = sum(factor_pnl_row.values())
    losers = sorted((item for item in factor_pnl_row.items() if item[1] < 0), key=lambda item: item[1])
    drivers = []
    for factor_id, pnl in losers[:top]:
        factor = FACTOR_BY_ID.get(factor_id, {})
        drivers.append({
            "factor_id": factor_id,
            "label": factor.get("label", factor_id),
            "risk_type": factor.get("risk_type", "other"),
            "market": factor.get("market", "n/a"),
            "pnl": round(pnl, 2),
            "share_of_loss_pct": round(pnl / total * 100, 2) if total < 0 else None,
        })
    return drivers


def stability_metrics(series: list[dict], periods: int = STABILITY_PERIODS) -> dict:
    """VaR level statistics and the exception rate in consecutive sub-periods."""
    var = np.array([row["var"] for row in series], dtype=float)
    hits = np.array([row["exception"] for row in series], dtype=bool)
    changes = np.abs(np.diff(var)) / var[:-1] * 100 if var.size > 1 and np.all(var[:-1] > 0) else np.array([])
    sub_periods = []
    for chunk in np.array_split(np.arange(var.size), min(periods, var.size)):
        sub_periods.append({
            "start": series[chunk[0]]["date"],
            "end": series[chunk[-1]]["date"],
            "n_obs": int(chunk.size),
            "n_exceptions": int(hits[chunk].sum()),
            "exception_rate": float(hits[chunk].mean()),
            "mean_var": round(float(var[chunk].mean()), 2),
        })
    mean_var = float(var.mean())
    return {
        "mean_var": round(mean_var, 2),
        "min_var": round(float(var.min()), 2),
        "max_var": round(float(var.max()), 2),
        "var_coefficient_of_variation": float(var.std() / mean_var) if mean_var else None,
        "max_daily_var_change_pct": float(changes.max()) if changes.size else None,
        "sub_periods": sub_periods,
    }


def assess_status(backtest: dict) -> tuple[str, list[str]]:
    """Overall status and the reasons for it.

    Red: Basel red zone, or too many exceptions with a Kupiec p-value below 1%.
    Amber: Basel yellow zone, any coverage or independence p-value below 5%.
    Green: otherwise.
    """
    reasons_red, reasons_amber = [], []
    zone = backtest["traffic_light"]["zone"]
    too_many = backtest["n_exceptions"] > backtest["expected_exceptions"]
    kupiec_p = backtest["kupiec"]["p_value"]
    if zone == "red":
        reasons_red.append("Basel traffic light is in the red zone")
    elif zone == "yellow":
        reasons_amber.append("Basel traffic light is in the yellow zone")
    if kupiec_p < 0.01 and too_many:
        reasons_red.append("Kupiec test rejects the exception rate at the 1% level (too many exceptions)")
    elif kupiec_p < 0.05:
        direction = "too many" if too_many else "too few"
        reasons_amber.append(f"Kupiec test rejects the exception rate at the 5% level ({direction} exceptions)")
    if backtest["independence"]["p_value"] < 0.05:
        reasons_amber.append("Christoffersen independence test indicates clustered exceptions")
    if backtest["conditional_coverage"]["p_value"] < 0.05:
        reasons_amber.append("Conditional coverage test is rejected at the 5% level")
    if reasons_red:
        return "red", reasons_red + reasons_amber
    if reasons_amber:
        return "amber", reasons_amber
    return "green", ["Coverage and independence tests are passed and the traffic light is green"]


def _findings(backtest: dict, clustering: dict, largest: list[dict], drivers: dict, stability: dict, status: str) -> list[str]:
    confidence = backtest["confidence"]
    method = "historical simulation" if backtest["method"] == "historical" else "parametric (normal)"
    light = backtest["traffic_light"]
    findings = [
        f"Over {backtest['n_obs']} backtest days the {confidence:.1%} one-day {method} VaR "
        f"(window {backtest['window']} days) recorded {backtest['n_exceptions']} exceptions against "
        f"{backtest['expected_exceptions']:.1f} expected, an exception rate of {backtest['exception_rate']:.2%}.",
        f"The most recent {light['n_obs']} days contain {light['n_exceptions']} exceptions, which places the model "
        f"in the {light['zone']} zone of the Basel traffic-light approach.",
    ]
    kupiec = backtest["kupiec"]
    verdict = "is not rejected" if kupiec["p_value"] >= 0.05 else "is rejected"
    findings.append(
        f"Unconditional coverage: the Kupiec statistic is {kupiec['statistic']:.2f} (p-value {kupiec['p_value']:.3f}), "
        f"so the hypothesis that the exception rate equals {1 - confidence:.1%} {verdict} at the 5% level."
    )
    independence = backtest["independence"]
    verdict = "no evidence of" if independence["p_value"] >= 0.05 else "evidence of"
    findings.append(
        f"Independence: the Christoffersen statistic is {independence['statistic']:.2f} "
        f"(p-value {independence['p_value']:.3f}), giving {verdict} exception clustering. "
        f"Exceptions on the day after another exception: {clustering['consecutive_pairs']}; most exceptions in "
        f"any {clustering['cluster_window_days']}-day period: {clustering['max_in_window']}."
    )
    if largest:
        worst = largest[0]
        ratio = f" ({worst['loss_to_var']:.2f}x VaR)" if worst["loss_to_var"] is not None else ""
        findings.append(
            f"The largest breach was on {worst['date']}: a loss of {-worst['pnl']:,.0f} against a VaR of "
            f"{worst['var']:,.0f}{ratio}, exceeding VaR by {worst['excess']:,.0f}."
        )
    if drivers["top_risk_type_counts"]:
        lead, count = max(drivers["top_risk_type_counts"].items(), key=lambda item: item[1])
        findings.append(
            f"{lead.capitalize()} was the largest loss driver on {count} of the {backtest['n_exceptions']} exception days."
        )
    rates = [period["exception_rate"] for period in stability["sub_periods"]]
    findings.append(
        f"Stability: VaR ranged from {stability['min_var']:,.0f} to {stability['max_var']:,.0f} "
        f"(mean {stability['mean_var']:,.0f}); the exception rate across {len(rates)} sub-periods ranged from "
        f"{min(rates):.2%} to {max(rates):.2%}."
    )
    action = {
        "green": "No action is required beyond routine monitoring.",
        "amber": "The model should be reviewed: investigate the exceptions above and consider recalibration.",
        "red": "The model is not performing adequately: escalate, investigate root causes and recalibrate or replace it.",
    }[status]
    findings.append(f"Overall status is {status}. {action}")
    return findings


def model_performance_report(
    pnl,
    dates=None,
    confidence: float = 0.99,
    window: int = 250,
    method: str = "historical",
    factor_pnl: dict[str, list[float]] | None = None,
    top_breaches: int = 5,
) -> dict:
    """Model performance report for a rolling VaR model over a backtest window."""
    backtest = backtest_var(pnl, dates, confidence, window, method, factor_pnl=factor_pnl)
    series = backtest["series"]
    hits = [row["exception"] for row in series]
    clustering = clustering_metrics(hits)

    top_counts: dict[str, int] = {}
    exceptions = []
    for exception in backtest["exceptions"]:
        row = dict(exception)
        row["drivers"] = []
        if factor_pnl:
            day = window + exception["index"]
            row["drivers"] = exception_drivers({key: float(values[day]) for key, values in factor_pnl.items()})
            if row["drivers"]:
                lead = row["drivers"][0]["risk_type"]
                top_counts[lead] = top_counts.get(lead, 0) + 1
        exceptions.append(row)
    largest = sorted(exceptions, key=lambda row: row["excess"], reverse=True)[:top_breaches]
    ratios = [row["loss_to_var"] for row in exceptions if row["loss_to_var"] is not None]
    drivers = {"available": bool(factor_pnl), "top_risk_type_counts": top_counts}
    stability = stability_metrics(series)
    status, reasons = assess_status(backtest)

    return {
        "status": status,
        "status_reasons": reasons,
        "findings": _findings(backtest, clustering, largest, drivers, stability, status),
        "summary": {key: backtest[key] for key in (
            "method", "confidence", "window", "n_obs", "n_exceptions", "expected_exceptions",
            "exception_rate", "kupiec", "independence", "conditional_coverage", "traffic_light",
        )},
        "clustering": clustering,
        "largest_breaches": largest,
        "exceptions": exceptions,
        "drivers": drivers,
        "mean_loss_to_var": float(np.mean(ratios)) if ratios else None,
        "stability": stability,
        "series": series,
        "disclaimer": MODEL_DISCLAIMER,
    }


def sample_model_performance_report(
    seed: int = 42, days: int = 750, confidence: float = 0.99, window: int = 250, method: str = "historical",
) -> dict:
    """Model performance report for the bundled synthetic sample book."""
    sample = sample_portfolio(seed, days)
    report = model_performance_report(
        sample["pnl"], sample["dates"], confidence, window, method, sample["factor_pnl"]
    )
    report["portfolio"] = {
        "name": sample["name"], "currency": sample["currency"], "seed": seed,
        "disclaimer": sample["disclaimer"],
    }
    return report
