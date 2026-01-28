"""Region-aware sector benchmarking.

Compares a company's ratios with a sector profile (lower quartile, median,
upper quartile) for India, China, Japan or South Korea.

The profiles are ILLUSTRATIVE. They are hand-set, plausible ranges for
analysis and learning. They are not computed from a market data set and must
not be quoted as observed peer statistics. Each regional profile is the base
sector profile scaled by a small, stated regional tilt.
"""

from math import isfinite

DISCLAIMER = (
    "Illustrative benchmark ranges for analysis and learning. They are not derived "
    "from a market data set and are not observed peer statistics."
)

REGIONS = {
    "IN": "India",
    "CN": "China",
    "JP": "Japan",
    "KR": "South Korea",
}

# Ratios stored as fractions (0.12 = 12%); the rest are multiples.
FRACTION_RATIOS = {
    "gross_profit_margin", "operating_margin", "net_profit_margin",
    "return_on_assets", "return_on_equity", "debt_to_assets",
}
LOWER_IS_BETTER = {"debt_to_equity", "debt_to_assets"}

RATIO_LABELS = {
    "gross_profit_margin": "Gross profit margin",
    "operating_margin": "Operating margin",
    "net_profit_margin": "Net profit margin",
    "return_on_assets": "Return on assets",
    "return_on_equity": "Return on equity",
    "current_ratio": "Current ratio",
    "quick_ratio": "Quick ratio",
    "debt_to_equity": "Debt to equity",
    "debt_to_assets": "Debt to assets",
    "interest_coverage": "Interest coverage",
    "asset_turnover": "Asset turnover",
    "inventory_turnover": "Inventory turnover",
    "receivables_turnover": "Receivables turnover",
}


def _q(p25: float, median: float, p75: float) -> dict:
    return {"p25": p25, "median": median, "p75": p75}


# Base sector profiles (illustrative).
SECTOR_BENCHMARKS: dict[str, dict] = {
    "information_technology": {
        "name": "Information technology and services",
        "keywords": ["tech", "software", "infotech", "digital", "it services", "systems", "data"],
        "ratios": {
            "gross_profit_margin": _q(0.28, 0.36, 0.48), "operating_margin": _q(0.10, 0.17, 0.24),
            "net_profit_margin": _q(0.07, 0.13, 0.19), "return_on_assets": _q(0.06, 0.11, 0.17),
            "return_on_equity": _q(0.11, 0.18, 0.27), "current_ratio": _q(1.5, 2.2, 3.2),
            "quick_ratio": _q(1.3, 2.0, 3.0), "debt_to_equity": _q(0.05, 0.20, 0.50),
            "debt_to_assets": _q(0.05, 0.12, 0.25), "interest_coverage": _q(8.0, 20.0, 45.0),
            "asset_turnover": _q(0.6, 0.9, 1.2), "receivables_turnover": _q(4.0, 5.5, 7.5),
        },
    },
    "automobiles": {
        "name": "Automobiles and components",
        "keywords": ["auto", "motor", "vehicle", "mobility", "tyre", "tire"],
        "ratios": {
            "gross_profit_margin": _q(0.13, 0.18, 0.24), "operating_margin": _q(0.03, 0.06, 0.09),
            "net_profit_margin": _q(0.02, 0.04, 0.07), "return_on_assets": _q(0.02, 0.04, 0.07),
            "return_on_equity": _q(0.06, 0.10, 0.15), "current_ratio": _q(1.0, 1.3, 1.7),
            "quick_ratio": _q(0.7, 0.9, 1.2), "debt_to_equity": _q(0.30, 0.70, 1.30),
            "debt_to_assets": _q(0.15, 0.28, 0.42), "interest_coverage": _q(3.0, 7.0, 15.0),
            "asset_turnover": _q(0.7, 1.0, 1.3), "inventory_turnover": _q(6.0, 8.5, 12.0),
            "receivables_turnover": _q(5.0, 7.5, 11.0),
        },
    },
    "pharmaceuticals": {
        "name": "Pharmaceuticals and healthcare",
        "keywords": ["pharma", "drug", "bio", "health", "medic", "life science"],
        "ratios": {
            "gross_profit_margin": _q(0.45, 0.58, 0.70), "operating_margin": _q(0.10, 0.16, 0.23),
            "net_profit_margin": _q(0.07, 0.12, 0.18), "return_on_assets": _q(0.04, 0.08, 0.12),
            "return_on_equity": _q(0.08, 0.13, 0.19), "current_ratio": _q(1.5, 2.2, 3.2),
            "quick_ratio": _q(1.0, 1.6, 2.5), "debt_to_equity": _q(0.10, 0.30, 0.60),
            "debt_to_assets": _q(0.08, 0.18, 0.30), "interest_coverage": _q(6.0, 14.0, 30.0),
            "asset_turnover": _q(0.4, 0.6, 0.8), "inventory_turnover": _q(2.0, 3.0, 4.5),
            "receivables_turnover": _q(3.5, 5.0, 7.0),
        },
    },
    "steel_metals": {
        "name": "Steel, metals and mining",
        "keywords": ["steel", "metal", "alumin", "copper", "mining", "iron", "alloy"],
        "ratios": {
            "gross_profit_margin": _q(0.10, 0.16, 0.24), "operating_margin": _q(0.03, 0.07, 0.12),
            "net_profit_margin": _q(0.01, 0.04, 0.08), "return_on_assets": _q(0.01, 0.04, 0.07),
            "return_on_equity": _q(0.04, 0.09, 0.15), "current_ratio": _q(0.9, 1.3, 1.8),
            "quick_ratio": _q(0.5, 0.8, 1.1), "debt_to_equity": _q(0.40, 0.80, 1.40),
            "debt_to_assets": _q(0.20, 0.32, 0.45), "interest_coverage": _q(2.0, 4.5, 9.0),
            "asset_turnover": _q(0.6, 0.8, 1.1), "inventory_turnover": _q(4.0, 5.5, 7.5),
            "receivables_turnover": _q(6.0, 9.0, 14.0),
        },
    },
    "consumer_goods": {
        "name": "Consumer goods and retail",
        "keywords": ["consumer", "retail", "food", "beverage", "fmcg", "mart", "store", "apparel"],
        "ratios": {
            "gross_profit_margin": _q(0.26, 0.36, 0.48), "operating_margin": _q(0.05, 0.10, 0.16),
            "net_profit_margin": _q(0.03, 0.07, 0.12), "return_on_assets": _q(0.04, 0.08, 0.13),
            "return_on_equity": _q(0.09, 0.15, 0.24), "current_ratio": _q(1.0, 1.4, 2.0),
            "quick_ratio": _q(0.5, 0.8, 1.2), "debt_to_equity": _q(0.15, 0.45, 0.90),
            "debt_to_assets": _q(0.10, 0.22, 0.36), "interest_coverage": _q(5.0, 11.0, 25.0),
            "asset_turnover": _q(0.9, 1.2, 1.7), "inventory_turnover": _q(5.0, 7.5, 11.0),
            "receivables_turnover": _q(8.0, 13.0, 22.0),
        },
    },
    "electronics_semiconductors": {
        "name": "Electronics and semiconductors",
        "keywords": ["electr", "semicon", "chip", "display", "device", "component", "optic"],
        "ratios": {
            "gross_profit_margin": _q(0.20, 0.30, 0.42), "operating_margin": _q(0.05, 0.11, 0.19),
            "net_profit_margin": _q(0.03, 0.08, 0.15), "return_on_assets": _q(0.03, 0.06, 0.11),
            "return_on_equity": _q(0.06, 0.11, 0.18), "current_ratio": _q(1.3, 1.8, 2.6),
            "quick_ratio": _q(0.9, 1.3, 2.0), "debt_to_equity": _q(0.15, 0.40, 0.80),
            "debt_to_assets": _q(0.10, 0.20, 0.32), "interest_coverage": _q(5.0, 12.0, 28.0),
            "asset_turnover": _q(0.6, 0.8, 1.1), "inventory_turnover": _q(4.0, 5.5, 8.0),
            "receivables_turnover": _q(4.5, 6.0, 8.5),
        },
    },
    "energy_utilities": {
        "name": "Energy and utilities",
        "keywords": ["energy", "power", "oil", "gas", "petro", "utility", "electric", "refin"],
        "ratios": {
            "gross_profit_margin": _q(0.14, 0.22, 0.32), "operating_margin": _q(0.05, 0.10, 0.16),
            "net_profit_margin": _q(0.03, 0.06, 0.10), "return_on_assets": _q(0.02, 0.04, 0.06),
            "return_on_equity": _q(0.05, 0.09, 0.14), "current_ratio": _q(0.8, 1.1, 1.5),
            "quick_ratio": _q(0.6, 0.8, 1.1), "debt_to_equity": _q(0.50, 1.00, 1.70),
            "debt_to_assets": _q(0.25, 0.38, 0.50), "interest_coverage": _q(2.0, 4.0, 7.5),
            "asset_turnover": _q(0.3, 0.5, 0.9), "inventory_turnover": _q(8.0, 12.0, 20.0),
            "receivables_turnover": _q(5.0, 7.5, 11.0),
        },
    },
    "chemicals": {
        "name": "Chemicals and materials",
        "keywords": ["chem", "material", "polymer", "fertil", "paint", "coating"],
        "ratios": {
            "gross_profit_margin": _q(0.17, 0.25, 0.34), "operating_margin": _q(0.05, 0.09, 0.14),
            "net_profit_margin": _q(0.03, 0.06, 0.10), "return_on_assets": _q(0.03, 0.05, 0.09),
            "return_on_equity": _q(0.06, 0.10, 0.16), "current_ratio": _q(1.1, 1.5, 2.1),
            "quick_ratio": _q(0.7, 1.0, 1.5), "debt_to_equity": _q(0.25, 0.55, 1.00),
            "debt_to_assets": _q(0.14, 0.25, 0.38), "interest_coverage": _q(4.0, 8.0, 17.0),
            "asset_turnover": _q(0.6, 0.8, 1.1), "inventory_turnover": _q(4.5, 6.0, 8.5),
            "receivables_turnover": _q(4.5, 6.5, 9.5),
        },
    },
    "construction_real_estate": {
        "name": "Construction and real estate",
        "keywords": ["construct", "real estate", "property", "realty", "infra", "housing", "developer"],
        "ratios": {
            "gross_profit_margin": _q(0.14, 0.22, 0.32), "operating_margin": _q(0.05, 0.10, 0.17),
            "net_profit_margin": _q(0.02, 0.06, 0.11), "return_on_assets": _q(0.01, 0.03, 0.05),
            "return_on_equity": _q(0.04, 0.09, 0.15), "current_ratio": _q(1.1, 1.5, 2.1),
            "quick_ratio": _q(0.4, 0.7, 1.1), "debt_to_equity": _q(0.60, 1.20, 2.00),
            "debt_to_assets": _q(0.25, 0.38, 0.52), "interest_coverage": _q(1.8, 3.5, 7.0),
            "asset_turnover": _q(0.2, 0.4, 0.7), "inventory_turnover": _q(0.5, 1.2, 3.0),
            "receivables_turnover": _q(3.0, 5.0, 9.0),
        },
    },
}

# Regional tilt: multiplier applied to p25, median and p75 of the base profile.
# Illustrative assumptions, stated so the user can see how each profile was built.
REGION_TILTS: dict[str, dict] = {
    "IN": {
        "rationale": "Assumes somewhat higher returns on equity and slower receivable collection than the base profile.",
        "multipliers": {"return_on_equity": 1.15, "return_on_assets": 1.10, "net_profit_margin": 1.05,
                        "receivables_turnover": 0.90},
    },
    "CN": {
        "rationale": "Assumes somewhat thinner net margins and higher leverage than the base profile.",
        "multipliers": {"net_profit_margin": 0.90, "debt_to_equity": 1.15, "debt_to_assets": 1.10,
                        "interest_coverage": 0.90},
    },
    "JP": {
        "rationale": "Assumes lower returns on equity, lower leverage and stronger liquidity than the base profile.",
        "multipliers": {"return_on_equity": 0.80, "return_on_assets": 0.85, "net_profit_margin": 0.90,
                        "current_ratio": 1.15, "quick_ratio": 1.15, "debt_to_equity": 0.85,
                        "interest_coverage": 1.25},
    },
    "KR": {
        "rationale": "Assumes slightly lower returns on equity and slightly higher leverage than the base profile.",
        "multipliers": {"return_on_equity": 0.90, "debt_to_equity": 1.10, "debt_to_assets": 1.05},
    },
}


def resolve_region(region: str) -> str:
    key = str(region).strip().upper()
    if key not in REGIONS:
        raise ValueError(f"Unknown region '{region}'. Available: {', '.join(REGIONS)}")
    return key


def get_regions() -> list[dict]:
    return [{"id": code, "name": name, "tilt_rationale": REGION_TILTS[code]["rationale"]}
            for code, name in REGIONS.items()]


def get_available_industries() -> list[dict]:
    """Available sector profiles."""
    return [{"id": key, "name": value["name"],
             "ratio_count": len(value["ratios"])}
            for key, value in SECTOR_BENCHMARKS.items()]


def get_profile(sector_id: str, region: str) -> dict:
    """Illustrative benchmark profile for one sector in one region."""
    code = resolve_region(region)
    if sector_id not in SECTOR_BENCHMARKS:
        raise ValueError(f"Unknown sector '{sector_id}'. Available: {', '.join(SECTOR_BENCHMARKS)}")
    sector = SECTOR_BENCHMARKS[sector_id]
    multipliers = REGION_TILTS[code]["multipliers"]
    ratios = {}
    for name, bench in sector["ratios"].items():
        factor = multipliers.get(name, 1.0)
        ratios[name] = {
            "label": RATIO_LABELS[name],
            "unit": "fraction" if name in FRACTION_RATIOS else "x",
            "lower_is_better": name in LOWER_IS_BETTER,
            **{point: round(bench[point] * factor, 4) for point in ("p25", "median", "p75")},
        }
    return {
        "sector_id": sector_id,
        "sector_name": sector["name"],
        "region": code,
        "region_name": REGIONS[code],
        "ratios": ratios,
        "tilt_rationale": REGION_TILTS[code]["rationale"],
        "illustrative": True,
        "disclaimer": DISCLAIMER,
    }


def normalize_ratio_name(name: str) -> str:
    """'Gross Profit Margin', 'grossProfitMargin' and 'gross-profit-margin' -> 'gross_profit_margin'."""
    text = str(name).strip()
    out = []
    for i, char in enumerate(text):
        if char.isupper() and i and text[i - 1].islower():
            out.append("_")
        out.append(char.lower() if char.isalnum() else "_")
    return "_".join(part for part in "".join(out).split("_") if part)


def _to_benchmark_scale(name: str, value: float, unit: str | None) -> float:
    """Benchmarks hold margins and returns as fractions (0.12 = 12%).

    Values are taken as fractions unless the unit is "percent" or "pct", in
    which case they are divided by 100. The unit "%" is treated as a fraction
    because the statement analysis reports its percent ratios that way.
    """
    if name in FRACTION_RATIOS and str(unit or "").strip().lower() in ("percent", "pct"):
        return value / 100
    return value


def _rank(value: float, bench: dict, lower_is_better: bool) -> tuple[int, str]:
    """Quartile band: beyond the good quartile 90, better than median 65,
    inside the weak quartile 35, beyond it 10."""
    if lower_is_better:
        steps = (value <= bench["p25"], value <= bench["median"], value <= bench["p75"])
    else:
        steps = (value >= bench["p75"], value >= bench["median"], value >= bench["p25"])
    if steps[0]:
        return 90, "excellent"
    if steps[1]:
        return 65, "above_average"
    if steps[2]:
        return 35, "below_average"
    return 10, "poor"


def compare_against_industry(company_ratios: list[dict], industry_id: str, region: str = "IN") -> dict:
    """Compare a company's ratios with an illustrative sector profile.

    Args:
        company_ratios: [{ratio_name, value, unit}]. Margins and returns are
            fractions (0.12 = 12%) unless unit is "percent" or "pct".
        industry_id: sector key from SECTOR_BENCHMARKS.
        region: IN, CN, JP or KR.

    The overall score is the mean of the quartile-band scores (90 / 65 / 35 / 10).
    """
    profile = get_profile(industry_id, region)
    comparisons = []
    unmatched = []
    seen = set()

    for ratio in company_ratios:
        name = normalize_ratio_name(ratio["ratio_name"])
        if name not in profile["ratios"] or name in seen:
            unmatched.append(str(ratio["ratio_name"]))
            continue
        raw = float(ratio["value"])
        if not isfinite(raw):
            raise ValueError(f"{ratio['ratio_name']}: value must be finite")
        if name in LOWER_IS_BETTER and raw < 0:
            # Negative leverage means negative equity or assets; it is not a low-leverage strength.
            raise ValueError(f"{ratio['ratio_name']}: a negative value is not meaningful "
                             "(negative equity or assets) and cannot be benchmarked")
        seen.add(name)
        bench = profile["ratios"][name]
        value = _to_benchmark_scale(name, raw, ratio.get("unit"))
        percentile, rank = _rank(value, bench, bench["lower_is_better"])
        deviation = (value - bench["median"]) / abs(bench["median"]) * 100
        comparisons.append({
            "ratio_name": name,
            "label": bench["label"],
            "unit": bench["unit"],
            "lower_is_better": bench["lower_is_better"],
            "company_value": round(value, 6),
            "industry_median": bench["median"],
            "industry_p25": bench["p25"],
            "industry_p75": bench["p75"],
            "percentile": percentile,
            "rank": rank,
            "deviation_pct": round(deviation, 1),
        })

    overall = round(sum(c["percentile"] for c in comparisons) / len(comparisons)) if comparisons else 0
    if not comparisons:
        overall_rank = "not_scored"
    elif overall >= 75:
        overall_rank = "excellent"
    elif overall >= 50:
        overall_rank = "above_average"
    elif overall >= 25:
        overall_rank = "below_average"
    else:
        overall_rank = "poor"

    return {
        "industry_id": industry_id,
        "industry_name": profile["sector_name"],
        "region": profile["region"],
        "region_name": profile["region_name"],
        "overall_score": overall,
        "overall_rank": overall_rank,
        "ratios_compared": len(comparisons),
        "comparisons": comparisons,
        "strengths": [c["label"] for c in comparisons if c["rank"] == "excellent"],
        "weaknesses": [c["label"] for c in comparisons if c["rank"] == "poor"],
        "unmatched_ratios": unmatched,
        "tilt_rationale": profile["tilt_rationale"],
        "illustrative": True,
        "disclaimer": DISCLAIMER,
    }


def auto_detect_industry(company_name: str, ratios: list[dict]) -> str | None:
    """Guess a sector from keywords in the company name. None when nothing matches."""
    lowered = str(company_name).lower()
    for sector_id, sector in SECTOR_BENCHMARKS.items():
        if any(keyword in lowered for keyword in sector["keywords"]):
            return sector_id
    return None
