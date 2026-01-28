"""Internal credit rating scorecards, credit review drafts and onboarding checklists.

Simplified, for analysis and learning; not a regulatory calculation and not a
calibrated rating model.

Methodology
-----------
* Three scorecards: ``corporate``, ``financial_institution`` and ``fund``.
* Every scorecard has quantitative factors (70 points of weight) computed from
  submitted line items and four qualitative factors (30 points of weight)
  assessed by the analyst on a 1 (weak) to 5 (strong) scale.
* A quantitative factor is scored 0-100 by straight-line interpolation between
  a "weak" anchor (score 0) and a "strong" anchor (score 100), capped at both
  ends. Size factors are interpolated on a log10 scale.
* A qualitative assessment ``a`` is scored ``(a - 1) * 25``.
* Total score = sum(weight * factor score) / 100, so it is also 0-100.
* The total score maps to an internal grade IR1 (strongest) to IR10 (weakest)
  through fixed score bands. Each grade carries an indicative one-year
  probability of default. The PD values are illustrative placeholders and are
  not calibrated to any default history.
* All amounts are expected in USD millions (the reporting currency). Ratios
  such as volatility or drawdown are decimals (0.12 means 12%).
"""

from __future__ import annotations

from math import isfinite, log10
from statistics import median

COUNTERPARTY_TYPES = ("corporate", "financial_institution", "fund")

TYPE_LABELS = {
    "corporate": "Corporate",
    "financial_institution": "Financial institution",
    "fund": "Fund",
}

COUNTRIES = {
    "IN": {"name": "India", "currency": "INR"},
    "CN": {"name": "China", "currency": "CNY"},
    "JP": {"name": "Japan", "currency": "JPY"},
    "KR": {"name": "South Korea", "currency": "KRW"},
}

# (grade, minimum total score, indicative one-year PD, description)
RATING_SCALE = (
    ("IR1", 90.0, 0.0003, "Exceptional"),
    ("IR2", 80.0, 0.0010, "Very strong"),
    ("IR3", 70.0, 0.0025, "Strong"),
    ("IR4", 62.0, 0.0060, "Good"),
    ("IR5", 54.0, 0.0120, "Satisfactory"),
    ("IR6", 46.0, 0.0250, "Adequate"),
    ("IR7", 38.0, 0.0500, "Vulnerable"),
    ("IR8", 30.0, 0.1000, "Weak"),
    ("IR9", 20.0, 0.2000, "Very weak"),
    ("IR10", 0.0, 0.3500, "Distressed"),
)
GRADES = tuple(row[0] for row in RATING_SCALE)

# Indicative limit as a share of the capital base (equity, or NAV for funds).
LIMIT_PCT_BY_GRADE = {
    "IR1": 0.10, "IR2": 0.08, "IR3": 0.06, "IR4": 0.05, "IR5": 0.04,
    "IR6": 0.03, "IR7": 0.02, "IR8": 0.01, "IR9": 0.0, "IR10": 0.0,
}
# Fund capital can be redeemed, so the fund limit uses half the percentage.
LIMIT_BASE_MULTIPLIER = {"corporate": 1.0, "financial_institution": 1.0, "fund": 0.5}

STRENGTH_THRESHOLD = 75.0
CONCERN_THRESHOLD = 35.0

QUALITATIVE_FACTORS = (
    {"key": "business_profile", "label": "Business profile", "weight": 10.0,
     "description": "Market position, diversification and stability of the franchise or strategy."},
    {"key": "management_governance", "label": "Management and governance", "weight": 8.0,
     "description": "Track record, transparency, ownership structure and risk controls."},
    {"key": "sector_outlook", "label": "Sector outlook", "weight": 6.0,
     "description": "Demand, competition, regulation and cyclicality of the sector over the next 12-24 months."},
    {"key": "country", "label": "Country environment", "weight": 6.0,
     "description": "Analyst view of the operating, legal and macro environment of the country of risk."},
)

INPUT_FIELDS = {
    "corporate": (
        ("revenue", "Revenue", "Income statement"),
        ("ebitda", "EBITDA", "Income statement"),
        ("operating_income", "Operating income (EBIT)", "Income statement"),
        ("interest_expense", "Interest expense", "Income statement"),
        ("net_income", "Net income", "Income statement"),
        ("total_assets", "Total assets", "Balance sheet"),
        ("current_assets", "Current assets", "Balance sheet"),
        ("cash", "Cash and equivalents", "Balance sheet"),
        ("current_liabilities", "Current liabilities", "Balance sheet"),
        ("total_debt", "Total debt", "Balance sheet"),
        ("equity", "Shareholders' equity", "Balance sheet"),
        ("operating_cash_flow", "Operating cash flow", "Cash flow"),
        ("capex", "Capital expenditure", "Cash flow"),
    ),
    "financial_institution": (
        ("operating_income", "Total operating income", "Income statement"),
        ("operating_expenses", "Operating expenses", "Income statement"),
        ("net_income", "Net income", "Income statement"),
        ("total_assets", "Total assets", "Balance sheet"),
        ("gross_loans", "Gross loans", "Balance sheet"),
        ("non_performing_loans", "Non-performing loans", "Balance sheet"),
        ("loan_loss_reserves", "Loan loss reserves", "Balance sheet"),
        ("customer_deposits", "Customer deposits", "Balance sheet"),
        ("total_equity", "Total equity", "Balance sheet"),
        ("cet1_capital", "Common equity tier 1 capital", "Capital and liquidity"),
        ("risk_weighted_assets", "Risk-weighted assets", "Capital and liquidity"),
        ("liquid_assets", "High-quality liquid assets", "Capital and liquidity"),
        ("net_cash_outflows_30d", "Net cash outflows over 30 days", "Capital and liquidity"),
    ),
    "fund": (
        ("net_asset_value", "Net asset value (AUM)", "Size and leverage"),
        ("gross_exposure", "Gross exposure", "Size and leverage"),
        ("liquid_assets_7d", "Assets realisable within 7 days", "Liquidity and redemption"),
        ("redemption_notice_days", "Redemption notice (days)", "Liquidity and redemption"),
        ("top5_investor_share", "Share of NAV held by five largest investors (decimal)", "Liquidity and redemption"),
        ("net_flows_12m_pct", "Net investor flows over 12 months / NAV (decimal)", "Liquidity and redemption"),
        ("annualised_volatility", "Annualised return volatility (decimal)", "Performance"),
        ("max_drawdown", "Maximum drawdown over 3 years (decimal)", "Performance"),
    ),
}

# Fields that are denominators and must be strictly positive.
POSITIVE_FIELDS = {
    "corporate": ("revenue", "total_assets", "current_liabilities"),
    "financial_institution": (
        "operating_income", "total_assets", "gross_loans", "customer_deposits",
        "risk_weighted_assets", "net_cash_outflows_30d",
    ),
    "fund": ("net_asset_value",),
}
# Fund inputs entered as decimals (0.18 = 18%): allowed range per field.
DECIMAL_RANGES = {
    "top5_investor_share": (0.0, 1.0),
    "max_drawdown": (0.0, 1.0),
    "annualised_volatility": (0.0, 2.0),
    "net_flows_12m_pct": (-1.0, 10.0),
}
# Fields that may legitimately be negative (losses, cash burn, outflows).
SIGNED_FIELDS = {
    "ebitda", "operating_income", "net_income", "equity", "total_equity",
    "cet1_capital", "operating_cash_flow", "net_flows_12m_pct",
}


def _ratio(numerator: float, denominator: float):
    return numerator / denominator if denominator else None


def _corp_debt_to_ebitda(f):
    if f["total_debt"] == 0:
        return 0.0, None
    if f["ebitda"] <= 0:
        return None, 0.0
    return f["total_debt"] / f["ebitda"], None


def _corp_interest_coverage(f):
    if f["interest_expense"] == 0:
        return None, 100.0
    return f["operating_income"] / f["interest_expense"], None


def _corp_debt_to_capital(f):
    capital = f["total_debt"] + f["equity"]
    if capital <= 0:
        return None, 0.0
    return f["total_debt"] / capital, None


def _corp_fcf_to_debt(f):
    if f["total_debt"] == 0:
        return None, 100.0
    return (f["operating_cash_flow"] - f["capex"]) / f["total_debt"], None


def _fi_npl_coverage(f):
    if f["non_performing_loans"] == 0:
        return None, 100.0
    return f["loan_loss_reserves"] / f["non_performing_loans"], None


def _plain(fn):
    return lambda f: (fn(f), None)


# Each factor: key, label, weight, weak anchor, strong anchor, value format,
# formula text (for the methodology endpoint), calculation, optional log scale.
QUANTITATIVE_FACTORS = {
    "corporate": (
        ("scale", "Scale (revenue)", 5.0, 100.0, 10000.0, "usd_mn", "revenue, scored on a log10 scale",
         _plain(lambda f: f["revenue"]), True),
        ("ebitda_margin", "EBITDA margin", 10.0, 0.05, 0.30, "pct", "ebitda / revenue",
         _plain(lambda f: f["ebitda"] / f["revenue"]), False),
        ("return_on_assets", "Return on assets", 5.0, 0.0, 0.10, "pct", "net_income / total_assets",
         _plain(lambda f: f["net_income"] / f["total_assets"]), False),
        ("debt_to_ebitda", "Debt / EBITDA", 15.0, 6.0, 1.0, "x",
         "total_debt / ebitda (score 0 when EBITDA is not positive and debt is outstanding)",
         _corp_debt_to_ebitda, False),
        ("interest_coverage", "Interest coverage", 12.0, 1.0, 8.0, "x",
         "operating_income / interest_expense (score 100 when there is no interest expense)",
         _corp_interest_coverage, False),
        ("debt_to_capital", "Debt / capital", 8.0, 0.80, 0.20, "pct",
         "total_debt / (total_debt + equity) (score 0 when capital is not positive)",
         _corp_debt_to_capital, False),
        ("current_ratio", "Current ratio", 8.0, 0.8, 2.0, "x", "current_assets / current_liabilities",
         _plain(lambda f: f["current_assets"] / f["current_liabilities"]), False),
        ("fcf_to_debt", "Free cash flow / debt", 7.0, 0.0, 0.30, "pct",
         "(operating_cash_flow - capex) / total_debt (score 100 when there is no debt)",
         _corp_fcf_to_debt, False),
    ),
    "financial_institution": (
        ("cet1_ratio", "CET1 ratio", 15.0, 0.07, 0.16, "pct", "cet1_capital / risk_weighted_assets",
         _plain(lambda f: f["cet1_capital"] / f["risk_weighted_assets"]), False),
        ("equity_to_assets", "Equity / assets", 8.0, 0.03, 0.10, "pct", "total_equity / total_assets",
         _plain(lambda f: f["total_equity"] / f["total_assets"]), False),
        ("npl_ratio", "Non-performing loan ratio", 12.0, 0.08, 0.01, "pct", "non_performing_loans / gross_loans",
         _plain(lambda f: f["non_performing_loans"] / f["gross_loans"]), False),
        ("npl_coverage", "NPL reserve coverage", 6.0, 0.4, 1.5, "pct",
         "loan_loss_reserves / non_performing_loans (score 100 when there are no NPLs)",
         _fi_npl_coverage, False),
        ("loan_to_deposit", "Loans / deposits", 10.0, 1.30, 0.70, "pct", "gross_loans / customer_deposits",
         _plain(lambda f: f["gross_loans"] / f["customer_deposits"]), False),
        ("liquidity_coverage", "Liquidity coverage", 9.0, 0.8, 1.6, "pct",
         "liquid_assets / net_cash_outflows_30d",
         _plain(lambda f: f["liquid_assets"] / f["net_cash_outflows_30d"]), False),
        ("return_on_assets", "Return on assets", 6.0, 0.0, 0.015, "pct", "net_income / total_assets",
         _plain(lambda f: f["net_income"] / f["total_assets"]), False),
        ("cost_to_income", "Cost / income", 4.0, 0.80, 0.40, "pct", "operating_expenses / operating_income",
         _plain(lambda f: f["operating_expenses"] / f["operating_income"]), False),
    ),
    "fund": (
        ("aum", "Assets under management", 10.0, 100.0, 10000.0, "usd_mn",
         "net_asset_value, scored on a log10 scale",
         _plain(lambda f: f["net_asset_value"]), True),
        ("gross_leverage", "Gross leverage", 15.0, 6.0, 1.0, "x", "gross_exposure / net_asset_value",
         _plain(lambda f: f["gross_exposure"] / f["net_asset_value"]), False),
        ("liquid_assets_ratio", "Liquid assets (7 days) / NAV", 12.0, 0.10, 0.80, "pct",
         "liquid_assets_7d / net_asset_value",
         _plain(lambda f: f["liquid_assets_7d"] / f["net_asset_value"]), False),
        ("redemption_notice", "Redemption notice period", 8.0, 1.0, 90.0, "days",
         "redemption_notice_days (longer notice gives more stable capital)",
         _plain(lambda f: f["redemption_notice_days"]), False),
        ("volatility", "Performance volatility", 10.0, 0.30, 0.04, "pct", "annualised_volatility",
         _plain(lambda f: f["annualised_volatility"]), False),
        ("max_drawdown", "Maximum drawdown", 7.0, 0.40, 0.05, "pct", "max_drawdown",
         _plain(lambda f: f["max_drawdown"]), False),
        ("investor_concentration", "Investor concentration", 4.0, 0.80, 0.20, "pct", "top5_investor_share",
         _plain(lambda f: f["top5_investor_share"]), False),
        ("net_flows", "Net investor flows (12 months)", 4.0, -0.30, 0.10, "pct", "net_flows_12m_pct",
         _plain(lambda f: f["net_flows_12m_pct"]), False),
    ),
}


def interpolate_score(value: float, weak: float, strong: float, log_scale: bool = False) -> float:
    """Score 0-100 by linear interpolation between the weak and strong anchors."""
    if log_scale:
        if value <= 0:
            return 0.0
        value, weak, strong = log10(value), log10(weak), log10(strong)
    position = (value - weak) / (strong - weak)
    return min(max(position, 0.0), 1.0) * 100.0


def qualitative_score(assessment: int) -> float:
    """Map a 1 (weak) to 5 (strong) assessment to 0-100."""
    if assessment not in (1, 2, 3, 4, 5):
        raise ValueError("qualitative assessments must be whole numbers from 1 to 5")
    return (assessment - 1) * 25.0


def grade_for_score(total_score: float) -> dict:
    """Return the internal grade, band and indicative PD for a 0-100 score."""
    for grade, floor, pd_1y, description in RATING_SCALE:
        if total_score >= floor:
            return {"grade": grade, "description": description, "pd_1y": pd_1y}
    grade, _, pd_1y, description = RATING_SCALE[-1]
    return {"grade": grade, "description": description, "pd_1y": pd_1y}


def review_frequency_for_grade(grade: str) -> str:
    """IR1-IR5 are reviewed annually; IR6 and weaker semi-annually."""
    return "annual" if GRADES.index(grade) <= 4 else "semi_annual"


def format_value(value, fmt: str) -> str:
    if value is None:
        return "n/a"
    if fmt == "pct":
        return f"{value * 100:.1f}%"
    if fmt == "x":
        return f"{value:.2f}x"
    if fmt == "days":
        return f"{value:.0f} days"
    return f"USD {value:,.0f} mn"


def _check_type(counterparty_type: str) -> None:
    if counterparty_type not in COUNTERPARTY_TYPES:
        raise ValueError(f"counterparty_type must be one of: {', '.join(COUNTERPARTY_TYPES)}")


def _clean_financials(counterparty_type: str, financials: dict, name: str) -> dict:
    cleaned = {}
    for key, label, _ in INPUT_FIELDS[counterparty_type]:
        if key not in financials or financials[key] is None:
            raise ValueError(f"{name}: missing input '{key}' ({label})")
        value = float(financials[key])
        if not isfinite(value):
            raise ValueError(f"{name}: '{key}' must be a finite number")
        if key in POSITIVE_FIELDS[counterparty_type] and value <= 0:
            raise ValueError(f"{name}: '{key}' must be greater than zero")
        if key not in SIGNED_FIELDS and value < 0:
            raise ValueError(f"{name}: '{key}' cannot be negative")
        if counterparty_type == "fund" and key in DECIMAL_RANGES:
            low, high = DECIMAL_RANGES[key]
            if not low <= value <= high:
                raise ValueError(f"{name}: '{key}' must be between {low:g} and {high:g}; "
                                 "enter ratios as decimals (0.18 for 18%)")
        cleaned[key] = value
    if counterparty_type == "fund":
        ceiling = max(cleaned["gross_exposure"], cleaned["net_asset_value"])
        if cleaned["liquid_assets_7d"] > ceiling:
            raise ValueError(f"{name}: 'liquid_assets_7d' cannot exceed the larger of gross exposure "
                             "and net asset value")
    return cleaned


def _score_factors(counterparty_type: str, financials: dict, qualitative: dict, name: str) -> list[dict]:
    factors = []
    for key, label, weight, weak, strong, fmt, _formula, calc, log_scale in QUANTITATIVE_FACTORS[counterparty_type]:
        value, override = calc(financials)
        score = override if override is not None else interpolate_score(value, weak, strong, log_scale)
        factors.append({
            "key": key, "label": label, "category": "quantitative", "weight": weight,
            "value": None if value is None else round(value, 4),
            "display_value": format_value(value, fmt),
            "higher_is_better": strong > weak,
            "score": round(score, 2),
            "weighted_score": round(score * weight / 100.0, 3),
            "_raw_score": score,
        })
    for spec in QUALITATIVE_FACTORS:
        if spec["key"] not in qualitative:
            raise ValueError(f"{name}: missing qualitative assessment '{spec['key']}'")
        assessment = qualitative[spec["key"]]
        score = qualitative_score(assessment)
        factors.append({
            "key": spec["key"], "label": spec["label"], "category": "qualitative",
            "weight": spec["weight"], "value": assessment,
            "display_value": f"{assessment} / 5", "higher_is_better": True,
            "score": score, "weighted_score": round(score * spec["weight"] / 100.0, 3),
            "_raw_score": score,
        })
    return factors


def _capital_base(counterparty_type: str, financials: dict) -> float:
    key = {"corporate": "equity", "financial_institution": "total_equity", "fund": "net_asset_value"}[counterparty_type]
    return max(financials[key], 0.0)


def propose_limit(counterparty_type: str, grade: str, capital_base: float) -> dict:
    """Indicative limit = capital base x grade percentage x type multiplier.

    Simplified, for analysis and learning; a real limit also reflects product
    mix, tenor, collateral and portfolio concentration.
    """
    pct = LIMIT_PCT_BY_GRADE[grade] * LIMIT_BASE_MULTIPLIER[counterparty_type]
    return {
        "capital_base": round(capital_base, 2),
        "capital_base_label": "Net asset value" if counterparty_type == "fund" else "Equity",
        "limit_pct_of_base": round(pct, 4),
        "proposed_limit": round(capital_base * pct, 2),
        "currency": "USD mn",
    }


def _recommendation(grade: str) -> str:
    index = GRADES.index(grade)
    if index <= 4:
        return "Approve"
    if index <= 6:
        return "Approve with conditions and enhanced monitoring"
    if index == 7:
        return "Watchlist: no increase in exposure; reduce where possible"
    return "Decline new exposure; manage down existing exposure"


def _score_core(counterparty_type: str, name: str, financials: dict, qualitative: dict) -> dict:
    cleaned = _clean_financials(counterparty_type, financials, name)
    factors = _score_factors(counterparty_type, cleaned, qualitative, name)
    total = sum(f["_raw_score"] * f["weight"] for f in factors) / 100.0
    quant = [f for f in factors if f["category"] == "quantitative"]
    qual = [f for f in factors if f["category"] == "qualitative"]
    for factor in factors:
        del factor["_raw_score"]
    return {
        "factors": factors,
        "total_score": round(total, 2),
        "quantitative_score": round(sum(f["score"] * f["weight"] for f in quant) / sum(f["weight"] for f in quant), 2),
        "qualitative_score": round(sum(f["score"] * f["weight"] for f in qual) / sum(f["weight"] for f in qual), 2),
        "_financials": cleaned,
    }


def compare_to_peers(counterparty_type: str, subject: dict, peers: list[dict]) -> dict | None:
    """Compare the subject's factors and total score with a scored peer set.

    For each quantitative factor the result gives the peer median, how many
    peers the subject outperforms (direction-aware) and a position label.
    """
    if not peers:
        return None
    scored = []
    for peer in peers:
        peer_name = str(peer.get("name", "")).strip() or "Peer"
        core = _score_core(counterparty_type, peer_name, peer.get("financials", {}), peer.get("qualitative", {}))
        scored.append({
            "name": peer_name, "country": peer.get("country"), "sector": peer.get("sector"),
            "total_score": core["total_score"], "grade": grade_for_score(core["total_score"])["grade"],
            "_factors": {f["key"]: f for f in core["factors"]},
        })

    metrics = []
    for factor in subject["factors"]:
        if factor["category"] != "quantitative":
            continue
        peer_values = [p["_factors"][factor["key"]]["value"] for p in scored]
        peer_values = [value for value in peer_values if value is not None]
        value = factor["value"]
        fmt = next(spec[5] for spec in QUANTITATIVE_FACTORS[counterparty_type] if spec[0] == factor["key"])
        if value is None or not peer_values:
            metrics.append({
                "key": factor["key"], "label": factor["label"], "value": value,
                "display_value": factor["display_value"], "peer_median": None,
                "display_peer_median": "n/a", "peers_outperformed": None,
                "peer_count": len(peer_values), "position": "not comparable",
            })
            continue
        peer_median = median(peer_values)
        better = (lambda a, b: a > b) if factor["higher_is_better"] else (lambda a, b: a < b)
        position = "stronger" if better(value, peer_median) else "weaker" if better(peer_median, value) else "in line"
        metrics.append({
            "key": factor["key"], "label": factor["label"], "value": value,
            "display_value": factor["display_value"],
            "peer_median": round(peer_median, 4), "display_peer_median": format_value(peer_median, fmt),
            "peers_outperformed": sum(1 for pv in peer_values if better(value, pv)),
            "peer_count": len(peer_values), "position": position,
        })

    peer_scores = [p["total_score"] for p in scored]
    sector = subject.get("sector")
    return {
        "peer_count": len(scored),
        "same_sector_peers": sum(1 for p in scored if sector and p["sector"] == sector),
        "peer_median_score": round(median(peer_scores), 2),
        "rank": 1 + sum(1 for score in peer_scores if score > subject["total_score"]),
        "rank_out_of": len(scored) + 1,
        "metrics": metrics,
        "peers": sorted(
            ({k: v for k, v in p.items() if k != "_factors"} for p in scored),
            key=lambda row: row["total_score"], reverse=True,
        ),
    }


def score_counterparty(
    counterparty_type: str,
    name: str,
    country: str,
    financials: dict,
    qualitative: dict,
    sector: str = "",
    peers: list[dict] | None = None,
) -> dict:
    """Run the scorecard for one counterparty and return the full result.

    Simplified, for analysis and learning; not a regulatory calculation.
    See the module docstring for the methodology.
    """
    _check_type(counterparty_type)
    name = str(name).strip()
    if not name:
        raise ValueError("name is required")
    if country not in COUNTRIES:
        raise ValueError(f"country must be one of: {', '.join(COUNTRIES)}")

    core = _score_core(counterparty_type, name, financials, qualitative)
    cleaned = core.pop("_financials")
    rating = grade_for_score(core["total_score"])
    ranked = sorted(core["factors"], key=lambda f: abs(f["score"] - 50) * f["weight"], reverse=True)
    result = {
        "name": name,
        "counterparty_type": counterparty_type,
        "counterparty_type_label": TYPE_LABELS[counterparty_type],
        "country": country,
        "country_name": COUNTRIES[country]["name"],
        "local_currency": COUNTRIES[country]["currency"],
        "sector": sector,
        **core,
        "grade": rating["grade"],
        "grade_description": rating["description"],
        "pd_1y": rating["pd_1y"],
        "strengths": [f"{f['label']} ({f['display_value']}, score {f['score']:.0f})"
                      for f in ranked if f["score"] >= STRENGTH_THRESHOLD],
        "concerns": [f"{f['label']} ({f['display_value']}, score {f['score']:.0f})"
                     for f in ranked if f["score"] <= CONCERN_THRESHOLD],
        "recommendation": _recommendation(rating["grade"]),
        "review_frequency": review_frequency_for_grade(rating["grade"]),
        "limit": propose_limit(counterparty_type, rating["grade"], _capital_base(counterparty_type, cleaned)),
        "financials": cleaned,
        "disclaimer": "Simplified internal scorecard for analysis and learning. The PD is indicative and "
                      "not calibrated to default data; this is not a regulatory calculation.",
    }
    result["peer_comparison"] = compare_to_peers(counterparty_type, result, peers or [])
    return result


# --------------------------------------------------------------------------
# Credit review draft
# --------------------------------------------------------------------------

def _factor(scorecard: dict, key: str) -> dict:
    return next(f for f in scorecard["factors"] if f["key"] == key)


def _assessment_word(score: float) -> str:
    if score >= STRENGTH_THRESHOLD:
        return "strong"
    if score > CONCERN_THRESHOLD:
        return "adequate"
    return "weak"


def _join(items: list[str]) -> str:
    if not items:
        return ""
    if len(items) == 1:
        return items[0]
    return ", ".join(items[:-1]) + " and " + items[-1]


def _financial_paragraph(scorecard: dict) -> str:
    kind = scorecard["counterparty_type"]
    f = scorecard["financials"]

    def show(key):
        factor = _factor(scorecard, key)
        return f"{factor['display_value']} ({_assessment_word(factor['score'])})"

    if kind == "corporate":
        cash_cover = _ratio(f["cash"], f["total_debt"])
        cash_text = (f" Cash of USD {f['cash']:,.0f} mn covers {cash_cover * 100:.0f}% of total debt."
                     if cash_cover is not None else f" The company holds cash of USD {f['cash']:,.0f} mn and reports no debt.")
        return (
            f"Income statement: revenue of USD {f['revenue']:,.0f} mn with an EBITDA margin of {show('ebitda_margin')} "
            f"and return on assets of {show('return_on_assets')}. "
            f"Balance sheet: debt / EBITDA of {show('debt_to_ebitda')}, debt / capital of {show('debt_to_capital')} "
            f"and a current ratio of {show('current_ratio')}.{cash_text} "
            f"Cash flow: interest coverage of {show('interest_coverage')} and free cash flow / debt of {show('fcf_to_debt')}; "
            f"operating cash flow was USD {f['operating_cash_flow']:,.0f} mn against capital expenditure of USD {f['capex']:,.0f} mn."
        )
    if kind == "financial_institution":
        return (
            f"Capital: CET1 ratio of {show('cet1_ratio')} and equity / assets of {show('equity_to_assets')} "
            f"on total assets of USD {f['total_assets']:,.0f} mn. "
            f"Asset quality: non-performing loan ratio of {show('npl_ratio')} with reserve coverage of {show('npl_coverage')}. "
            f"Funding and liquidity: loans / deposits of {show('loan_to_deposit')} and liquidity coverage of {show('liquidity_coverage')}. "
            f"Earnings: return on assets of {show('return_on_assets')} and cost / income of {show('cost_to_income')}."
        )
    return (
        f"Size and leverage: net asset value of USD {f['net_asset_value']:,.0f} mn with gross leverage of {show('gross_leverage')}. "
        f"Liquidity terms: assets realisable within seven days equal {show('liquid_assets_ratio')} of NAV against a redemption "
        f"notice period of {show('redemption_notice')}. "
        f"Redemption profile: the five largest investors hold {show('investor_concentration')} of NAV and net flows over "
        f"twelve months were {show('net_flows')} of NAV. "
        f"Performance: annualised volatility of {show('volatility')} and a maximum drawdown of {show('max_drawdown')}."
    )


def generate_credit_review(scorecard: dict) -> dict:
    """Build a sectioned written credit review from a scorecard result.

    Deterministic templating from the scorecard numbers; no model calls. The
    output is a draft for an analyst to edit, not a finished credit opinion.
    """
    name = scorecard["name"]
    grade = scorecard["grade"]
    limit = scorecard["limit"]
    frequency = "annual" if scorecard["review_frequency"] == "annual" else "semi-annual"
    type_label = scorecard["counterparty_type_label"].lower()
    sector_text = f" in the {scorecard['sector']} sector" if scorecard.get("sector") else ""
    quals = {spec["key"]: _factor(scorecard, spec["key"]) for spec in QUALITATIVE_FACTORS}

    summary = (
        f"{name} is a {type_label}{sector_text} domiciled in {scorecard['country_name']}. "
        f"The internal scorecard gives a total score of {scorecard['total_score']:.1f} out of 100, which maps to "
        f"internal grade {grade} ({scorecard['grade_description']}) with an indicative one-year probability of default of "
        f"{scorecard['pd_1y'] * 100:.2f}%. Recommendation: {scorecard['recommendation']}."
    )

    business = (
        f"Business profile is assessed at {quals['business_profile']['value']} / 5 and management and governance at "
        f"{quals['management_governance']['value']} / 5. The sector outlook is assessed at "
        f"{quals['sector_outlook']['value']} / 5 and the country environment for {scorecard['country_name']} at "
        f"{quals['country']['value']} / 5. Together the qualitative factors score "
        f"{scorecard['qualitative_score']:.1f} out of 100. Exposure is reported in USD; the counterparty's local "
        f"currency is {scorecard['local_currency']}."
    )

    peer = scorecard.get("peer_comparison")
    if peer:
        stronger = [m["label"] for m in peer["metrics"] if m["position"] == "stronger"]
        weaker = [m["label"] for m in peer["metrics"] if m["position"] == "weaker"]
        peer_text = (
            f"Against a peer set of {peer['peer_count']} ({peer['same_sector_peers']} in the same sector), {name} ranks "
            f"{peer['rank']} of {peer['rank_out_of']} by total score ({scorecard['total_score']:.1f} against a peer median of "
            f"{peer['peer_median_score']:.1f})."
        )
        if stronger:
            peer_text += f" It is stronger than the peer median on {_join(stronger)}."
        if weaker:
            peer_text += f" It is weaker than the peer median on {_join(weaker)}."
    else:
        peer_text = "No peer set was supplied, so no peer or sector comparison has been made."

    concerns, strengths = scorecard["concerns"], scorecard["strengths"]
    risks = ("Key concerns: " + "; ".join(concerns) + "." if concerns
             else "No factor scores at or below the concern threshold of 35.")
    mitigants = (" Mitigants and strengths: " + "; ".join(strengths) + "." if strengths
                 else " No factor scores at or above the strength threshold of 75.")

    rationale = (
        f"Quantitative factors (70% weight) score {scorecard['quantitative_score']:.1f} and qualitative factors "
        f"(30% weight) score {scorecard['qualitative_score']:.1f}, giving a weighted total of "
        f"{scorecard['total_score']:.1f}. This falls in the {grade} band of the internal scale. "
        f"No analyst override has been applied."
    )

    if limit["proposed_limit"] > 0:
        limit_text = (
            f"Proposed limit: USD {limit['proposed_limit']:,.1f} mn, being {limit['limit_pct_of_base'] * 100:.1f}% of "
            f"{limit['capital_base_label'].lower()} of USD {limit['capital_base']:,.1f} mn for grade {grade}. "
        )
    else:
        limit_text = f"No limit is proposed at grade {grade}. "
    limit_text += (
        f"Review frequency: {frequency}. The limit is indicative and should be adjusted for product mix, tenor, "
        f"collateral and portfolio concentration."
    )

    sections = [
        {"title": "Summary and recommendation", "body": summary},
        {"title": "Business profile", "body": business},
        {"title": "Financial analysis", "body": _financial_paragraph(scorecard)},
        {"title": "Peer and sector comparison", "body": peer_text},
        {"title": "Risks and mitigants", "body": risks + mitigants},
        {"title": "Rating rationale", "body": rationale},
        {"title": "Proposed limit and review frequency", "body": limit_text},
    ]
    header = f"CREDIT REVIEW DRAFT: {name}"
    note = "Draft generated from a simplified internal scorecard. Review and edit before use."
    text = "\n\n".join([header, note] + [f"{s['title'].upper()}\n{s['body']}" for s in sections])
    return {"title": header, "note": note, "sections": sections, "text": text}


# --------------------------------------------------------------------------
# Onboarding due diligence
# --------------------------------------------------------------------------

ITEM_STATES = ("pending", "complete", "not_applicable", "issue")

_COMMON_ITEMS = (
    ("identity_documents", "Identity and legal status",
     "Obtain constitutional documents and proof of registration with the national company registry.", True),
    ("ownership", "Identity and legal status",
     "Map the ownership structure and identify ultimate beneficial owners and controllers.", True),
    ("authorised_signatories", "Identity and legal status",
     "Verify authorised signatories and the authority to enter into the proposed transactions.", True),
    ("sanctions_screening", "Screening",
     "Screen the entity, owners and directors against sanctions lists.", True),
    ("pep_adverse_media", "Screening",
     "Screen for politically exposed persons and adverse media.", True),
    ("source_of_funds", "Screening",
     "Understand the source of funds and the purpose of the relationship.", True),
    ("audited_financials", "Financial information",
     "Obtain audited financial statements for the last three years and the latest interim figures.", True),
    ("internal_rating", "Financial information",
     "Complete the internal rating scorecard and written credit review.", True),
    ("legal_agreements", "Legal and documentation",
     "Agree trading and collateral documentation appropriate to the products.", True),
    ("netting_opinion", "Legal and documentation",
     "Confirm enforceability of close-out netting and collateral arrangements in the jurisdiction with legal counsel.", True),
    ("tax_status", "Legal and documentation",
     "Collect tax residency and withholding documentation.", False),
    ("site_visit", "Other",
     "Hold a management meeting or site visit and record the notes.", False),
)

_TYPE_ITEMS = {
    "corporate": (
        ("group_structure", "Counterparty specific",
         "Review the group structure, the position of the contracting entity and any parent support or guarantees.", True),
        ("debt_profile", "Counterparty specific",
         "Review the debt maturity profile, covenants and committed banking facilities.", True),
        ("hedging_rationale", "Counterparty specific",
         "Confirm the commercial or hedging rationale for the proposed products.", False),
    ),
    "financial_institution": (
        ("licence", "Counterparty specific",
         "Confirm the licence status with the primary financial regulator.", True),
        ("regulatory_ratios", "Counterparty specific",
         "Obtain the latest regulatory capital and liquidity disclosures.", True),
        ("aml_programme", "Counterparty specific",
         "Review the institution's own anti-money-laundering and sanctions control framework.", True),
        ("regulatory_actions", "Counterparty specific",
         "Check for recent regulatory enforcement actions or material litigation.", False),
    ),
    "fund": (
        ("offering_documents", "Counterparty specific",
         "Obtain the offering documents, including investment mandate, leverage limits and redemption terms.", True),
        ("manager_authorisation", "Counterparty specific",
         "Confirm the investment manager's regulatory authorisation and its authority to bind the fund.", True),
        ("service_providers", "Counterparty specific",
         "Identify the administrator, custodian, auditor and prime brokers.", True),
        ("nav_reporting", "Counterparty specific",
         "Agree the frequency and content of NAV, performance and liquidity reporting.", True),
        ("investor_base", "Counterparty specific",
         "Review investor concentration and any gates, lock-ups or side letters.", False),
    ),
}

_COUNTRY_ITEMS = {
    "IN": (
        ("in_accounting", "Country: India",
         "Confirm the accounting framework used (Indian Accounting Standards or other) and the fiscal year end, commonly 31 March.", True),
        ("in_fx", "Country: India",
         "Assess foreign exchange regulations affecting cross-border payments and collateral, as INR is not freely convertible.", True),
        ("in_regulator", "Country: India",
         "Identify the relevant Indian regulator for the entity and its activities and confirm good standing.", False),
    ),
    "CN": (
        ("cn_accounting", "Country: China",
         "Confirm the accounting framework used (Chinese accounting standards or IFRS) and the reporting entity.", True),
        ("cn_fx", "Country: China",
         "Assess capital account and foreign exchange controls and whether settlement is in onshore CNY or offshore CNH.", True),
        ("cn_structure", "Country: China",
         "Clarify whether the contracting entity is onshore or offshore and the level of any state ownership.", True),
    ),
    "JP": (
        ("jp_accounting", "Country: Japan",
         "Confirm the accounting framework used (Japanese GAAP or IFRS) and the fiscal year end, commonly 31 March.", True),
        ("jp_group", "Country: Japan",
         "Review cross-shareholdings and group or main-bank relationships relevant to support.", False),
        ("jp_regulator", "Country: Japan",
         "Identify the relevant Japanese regulator for the entity and its activities and confirm good standing.", False),
    ),
    "KR": (
        ("kr_accounting", "Country: South Korea",
         "Confirm the accounting framework used (Korean IFRS or other) and whether statements are consolidated.", True),
        ("kr_fx", "Country: South Korea",
         "Assess foreign exchange reporting requirements and settlement arrangements, as KRW is not deliverable offshore.", True),
        ("kr_group", "Country: South Korea",
         "Review affiliation with a business group, including intra-group guarantees and cross-holdings.", False),
    ),
}


def due_diligence_checklist(counterparty_type: str, country: str) -> dict:
    """Return generic onboarding due-diligence items for a type and country.

    Items are generic prompts for an analyst. They are not legal advice and do
    not replace the firm's own onboarding policy.
    """
    _check_type(counterparty_type)
    if country not in COUNTRIES:
        raise ValueError(f"country must be one of: {', '.join(COUNTRIES)}")
    rows = _COMMON_ITEMS + _TYPE_ITEMS[counterparty_type] + _COUNTRY_ITEMS[country]
    return {
        "counterparty_type": counterparty_type,
        "country": country,
        "country_name": COUNTRIES[country]["name"],
        "states": list(ITEM_STATES),
        "items": [{"id": i, "category": c, "text": t, "mandatory": m} for i, c, t, m in rows],
        "note": "Generic checklist for illustration; not legal advice. Follow your own onboarding policy.",
    }


def assess_due_diligence(counterparty_type: str, country: str, states: dict[str, str]) -> dict:
    """Assess checklist completeness and approval readiness.

    * completeness = (complete + not applicable) / all items
    * ``blocked`` if any item is marked ``issue``
    * ``ready`` if every mandatory item is ``complete`` and nothing is blocked
      (a mandatory item cannot be waived as not applicable)
    * otherwise ``incomplete``
    """
    checklist = due_diligence_checklist(counterparty_type, country)
    items = checklist["items"]
    known = {item["id"] for item in items}
    unknown = sorted(set(states) - known)
    if unknown:
        raise ValueError(f"unknown checklist item(s): {', '.join(unknown)}")
    bad = sorted({state for state in states.values() if state not in ITEM_STATES})
    if bad:
        raise ValueError(f"item state must be one of: {', '.join(ITEM_STATES)}")

    resolved = [{**item, "state": states.get(item["id"], "pending")} for item in items]
    done = sum(1 for item in resolved if item["state"] in ("complete", "not_applicable"))
    issues = [item for item in resolved if item["state"] == "issue"]
    outstanding = [item for item in resolved if item["mandatory"] and item["state"] != "complete"]
    if issues:
        status, label = "blocked", "Blocked: resolve open issues before approval"
    elif outstanding:
        status, label = "incomplete", "Incomplete: mandatory items outstanding"
    else:
        status, label = "ready", "Ready for approval"
    return {
        "total_items": len(resolved),
        "completed_items": done,
        "completeness_pct": round(done / len(resolved) * 100, 1),
        "mandatory_total": sum(1 for item in resolved if item["mandatory"]),
        "mandatory_outstanding": [item["id"] for item in outstanding],
        "issues": [item["id"] for item in issues],
        "status": status,
        "status_label": label,
        "items": resolved,
    }


# --------------------------------------------------------------------------
# Methodology and illustrative sample data
# --------------------------------------------------------------------------

def methodology() -> dict:
    """Describe the scorecards, scale and limit rule for display in the UI."""
    scorecards = {}
    for kind in COUNTERPARTY_TYPES:
        scorecards[kind] = {
            "label": TYPE_LABELS[kind],
            "inputs": [{"key": k, "label": label, "group": group} for k, label, group in INPUT_FIELDS[kind]],
            "quantitative_factors": [
                {"key": key, "label": label, "weight": weight, "weak_anchor": weak, "strong_anchor": strong,
                 "format": fmt, "formula": formula, "log_scale": log_scale}
                for key, label, weight, weak, strong, fmt, formula, _calc, log_scale in QUANTITATIVE_FACTORS[kind]
            ],
            "qualitative_factors": [dict(spec) for spec in QUALITATIVE_FACTORS],
        }
    floors = [row[1] for row in RATING_SCALE]
    return {
        "summary": (
            "Quantitative factors (70% weight) are scored 0-100 by linear interpolation between a weak and a strong "
            "anchor. Qualitative factors (30% weight) are analyst assessments from 1 to 5, scored (a - 1) x 25. "
            "The weighted total maps to an internal grade from IR1 to IR10."
        ),
        "disclaimer": (
            "Simplified, for analysis and learning; not a regulatory calculation. Anchors, weights and PD values "
            "are illustrative and not calibrated to default data."
        ),
        "units": "Amounts in USD millions; ratios entered directly are decimals (0.12 = 12%).",
        "rating_scale": [
            {"grade": grade, "min_score": floor, "max_score": 100.0 if i == 0 else floors[i - 1],
             "pd_1y": pd_1y, "description": description,
             "review_frequency": review_frequency_for_grade(grade),
             "limit_pct_of_base": LIMIT_PCT_BY_GRADE[grade]}
            for i, (grade, floor, pd_1y, description) in enumerate(RATING_SCALE)
        ],
        "limit_rule": (
            "Indicative limit = capital base x grade percentage. The capital base is equity for corporates and "
            "financial institutions and net asset value for funds; funds use half the grade percentage."
        ),
        "strength_threshold": STRENGTH_THRESHOLD,
        "concern_threshold": CONCERN_THRESHOLD,
        "countries": [{"code": code, **info} for code, info in COUNTRIES.items()],
        "scorecards": scorecards,
    }


def _q(business: int, management: int, sector: int, country: int) -> dict:
    return {"business_profile": business, "management_governance": management,
            "sector_outlook": sector, "country": country}


def _corp(revenue, ebitda, ebit, interest, net, assets, cur_assets, cash, cur_liabs, debt, equity, ocf, capex):
    return {"revenue": revenue, "ebitda": ebitda, "operating_income": ebit, "interest_expense": interest,
            "net_income": net, "total_assets": assets, "current_assets": cur_assets, "cash": cash,
            "current_liabilities": cur_liabs, "total_debt": debt, "equity": equity,
            "operating_cash_flow": ocf, "capex": capex}


def _fi(income, expenses, net, assets, loans, npl, reserves, deposits, equity, cet1, rwa, hqla, outflows):
    return {"operating_income": income, "operating_expenses": expenses, "net_income": net,
            "total_assets": assets, "gross_loans": loans, "non_performing_loans": npl,
            "loan_loss_reserves": reserves, "customer_deposits": deposits, "total_equity": equity,
            "cet1_capital": cet1, "risk_weighted_assets": rwa, "liquid_assets": hqla,
            "net_cash_outflows_30d": outflows}


def _fund(nav, gross, liquid, notice, top5, flows, vol, drawdown):
    return {"net_asset_value": nav, "gross_exposure": gross, "liquid_assets_7d": liquid,
            "redemption_notice_days": notice, "top5_investor_share": top5, "net_flows_12m_pct": flows,
            "annualised_volatility": vol, "max_drawdown": drawdown}


# Fictional counterparties with invented figures. Illustrative sample data
# only; none of these are real companies or real market data.
SAMPLE_COUNTERPARTIES = {
    "corporate": (
        {"name": "Saffron Ridge Industries (sample)", "country": "IN", "sector": "Industrials",
         "financials": _corp(4200, 780, 560, 95, 310, 6100, 2100, 420, 1350, 1900, 2600, 640, 330),
         "qualitative": _q(4, 3, 4, 3)},
        {"name": "Jade Harbour Components (sample)", "country": "CN", "sector": "Technology hardware",
         "financials": _corp(7800, 1010, 620, 210, 290, 11500, 4300, 900, 3900, 4600, 3700, 820, 700),
         "qualitative": _q(3, 3, 3, 3)},
        {"name": "Kitsune Precision Works (sample)", "country": "JP", "sector": "Industrials",
         "financials": _corp(9600, 1820, 1340, 60, 880, 13800, 5600, 2100, 2700, 2200, 8300, 1500, 620),
         "qualitative": _q(5, 4, 3, 4)},
        {"name": "Baram Marine Engineering (sample)", "country": "KR", "sector": "Industrials",
         "financials": _corp(3100, 250, 110, 120, -40, 5200, 1700, 260, 1900, 2300, 1300, 150, 210),
         "qualitative": _q(2, 3, 2, 4)},
        {"name": "Lotus Grid Utilities (sample)", "country": "IN", "sector": "Utilities",
         "financials": _corp(1500, 520, 360, 140, 130, 5400, 700, 180, 620, 2500, 1900, 430, 380),
         "qualitative": _q(4, 3, 3, 3)},
    ),
    "financial_institution": (
        {"name": "Monsoon Coast Bank (sample)", "country": "IN", "sector": "Commercial banking",
         "financials": _fi(3900, 1900, 980, 92000, 58000, 1750, 1300, 70000, 8200, 7400, 56000, 15500, 11800),
         "qualitative": _q(3, 3, 4, 3)},
        {"name": "Pearl Delta Commercial Bank (sample)", "country": "CN", "sector": "Commercial banking",
         "financials": _fi(8200, 2900, 2600, 310000, 176000, 2900, 4800, 221000, 23500, 21000, 198000, 52000, 39000),
         "qualitative": _q(4, 3, 3, 3)},
        {"name": "Hinoki Bridge Trust Bank (sample)", "country": "JP", "sector": "Trust banking",
         "financials": _fi(5100, 3300, 1100, 420000, 150000, 1500, 1400, 260000, 24000, 21500, 152000, 98000, 62000),
         "qualitative": _q(4, 4, 3, 4)},
        {"name": "Dolsan Harbour Securities (sample)", "country": "KR", "sector": "Broker-dealer",
         "financials": _fi(1400, 1050, 190, 38000, 9000, 420, 210, 7400, 3100, 2600, 24000, 6100, 6400),
         "qualitative": _q(3, 3, 2, 4)},
        {"name": "Banyan Rural Finance (sample)", "country": "IN", "sector": "Non-bank lending",
         "financials": _fi(900, 610, 60, 11000, 8600, 640, 300, 6700, 720, 650, 8100, 700, 820),
         "qualitative": _q(2, 2, 3, 3)},
    ),
    "fund": (
        {"name": "Indus Valley Equity Mutual Fund (sample)", "country": "IN", "sector": "Mutual fund",
         "financials": _fund(2600, 2650, 2200, 3, 0.18, 0.06, 0.16, 0.24),
         "qualitative": _q(4, 4, 4, 3)},
        {"name": "Yellow River Macro Fund (sample)", "country": "CN", "sector": "Hedge fund",
         "financials": _fund(850, 3900, 420, 45, 0.55, -0.12, 0.19, 0.27),
         "qualitative": _q(3, 3, 3, 3)},
        {"name": "Momiji Lifetime Pension Fund (sample)", "country": "JP", "sector": "Pension fund",
         "financials": _fund(18500, 20300, 9800, 90, 0.10, 0.02, 0.07, 0.11),
         "qualitative": _q(5, 4, 3, 4)},
        {"name": "Han River Relative Value Fund (sample)", "country": "KR", "sector": "Hedge fund",
         "financials": _fund(320, 2400, 90, 30, 0.72, -0.25, 0.14, 0.31),
         "qualitative": _q(2, 3, 2, 4)},
        {"name": "Fuji Crest Bond Mutual Fund (sample)", "country": "JP", "sector": "Mutual fund",
         "financials": _fund(5400, 5600, 4300, 2, 0.22, 0.04, 0.05, 0.08),
         "qualitative": _q(4, 4, 3, 4)},
    ),
}


def sample_counterparties() -> dict:
    """Return the bundled fictional counterparties grouped by type."""
    return {
        "note": "Illustrative sample data. All counterparties are fictional and all figures are invented.",
        "samples": {kind: [dict(row, counterparty_type=kind) for row in rows]
                    for kind, rows in SAMPLE_COUNTERPARTIES.items()},
    }


def sample_peers(counterparty_type: str, exclude_name: str = "") -> list[dict]:
    """Bundled fictional peer set for a type, excluding the named counterparty."""
    _check_type(counterparty_type)
    return [dict(row) for row in SAMPLE_COUNTERPARTIES[counterparty_type] if row["name"] != exclude_name]
