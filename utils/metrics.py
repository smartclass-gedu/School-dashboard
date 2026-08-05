"""Shared metric calculations, kept separate from chart/UI code so all four
dashboards compute things the same way."""

import numpy as np
import pandas as pd
from scipy import stats as sstats


def calibration_bias(predicted: pd.Series, actual: pd.Series) -> float:
    """Mean (actual - predicted). Positive = teacher underestimates students
    (they beat predictions); negative = teacher overestimates."""
    return float((actual - predicted).mean())


def growth(current: pd.Series, prior: pd.Series) -> float:
    """Mean point change from prior year to current."""
    return float((current - prior).mean())


def at_risk_rate(student_master: pd.DataFrame) -> float:
    return float(student_master["at_risk"].mean())


def declining_students(subject_term: pd.DataFrame, term_order: list[str]) -> pd.DataFrame:
    """Students whose average score is trending down T1->T3, not just
    currently low -- per-student slope across terms, averaged across
    subjects."""
    pivot = (
        subject_term.groupby(["UPN", "term"])["sheetPercentage"]
        .mean()
        .unstack("term")
        .reindex(columns=term_order)
    )
    slopes = pivot.apply(
        lambda row: np.polyfit(range(len(term_order)), row.values, 1)[0]
        if row.notna().all()
        else np.nan,
        axis=1,
    )
    out = slopes.reset_index()
    out.columns = ["UPN", "slope"]
    return out.sort_values("slope").query("slope < 0")


def band_of(value: float, series: pd.Series) -> str:
    """Return which tertile of `series` the given value falls into."""
    pct_rank = (series < value).mean()
    if pct_rank >= 0.67:
        return "Top third"
    elif pct_rank >= 0.33:
        return "Middle third"
    return "Bottom third"


def correlation_with_p(x: pd.Series, y: pd.Series) -> tuple[float, float]:
    """Pearson r and p-value for two aligned series, NaN-safe."""
    paired = pd.DataFrame({"x": x, "y": y}).dropna()
    if len(paired) < 3:
        return float("nan"), float("nan")
    r, p = sstats.pearsonr(paired["x"], paired["y"])
    return float(r), float(p)


def r_squared(predicted: pd.Series, actual: pd.Series) -> float:
    """How much of the variance in actual is explained by predicted --
    i.e. how good a predictor `predicted` is, not a model fit."""
    paired = pd.DataFrame({"p": predicted, "a": actual}).dropna()
    if len(paired) < 3:
        return float("nan")
    r, _ = sstats.pearsonr(paired["p"], paired["a"])
    return float(r**2)


def anova_across_groups(df: pd.DataFrame, group_col: str, value_col: str):
    """One-way ANOVA F-stat and p-value across groups (e.g. classes, year
    groups) -- tells you whether observed differences are likely real or
    within noise."""
    groups = [g[value_col].dropna().values for _, g in df.groupby(group_col) if len(g) >= 2]
    if len(groups) < 2:
        return float("nan"), float("nan")
    f_stat, p_val = sstats.f_oneway(*groups)
    return float(f_stat), float(p_val)


def summary_stats(series: pd.Series) -> dict:
    """Common descriptive stats bundle for a KPI panel."""
    clean = series.dropna()
    return {
        "mean": float(clean.mean()),
        "median": float(clean.median()),
        "std": float(clean.std()),
        "min": float(clean.min()),
        "max": float(clean.max()),
        "iqr": float(clean.quantile(0.75) - clean.quantile(0.25)),
    }
