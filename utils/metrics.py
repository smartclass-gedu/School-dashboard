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


def inflation_summary(benchmark_df: pd.DataFrame, threshold: float = 10.0) -> dict:
    """Cohort-level summary of the CAT4-vs-internal gap. "gap (pp)" = internal -
    external; positive means the internal grade runs ahead of what the CAT4
    benchmark predicts -- the KHDA grade-inflation signal."""
    clean = benchmark_df["gap (pp)"].dropna()
    if len(clean) == 0:
        return {"mean_gap": 0.0, "flagged_pct": 0.0, "flagged_n": 0, "n": 0}
    flagged = clean > threshold
    return {
        "mean_gap": float(clean.mean()),
        "flagged_pct": float(flagged.mean() * 100),
        "flagged_n": int(flagged.sum()),
        "n": int(len(clean)),
    }


def gap_by_subject(benchmark_df: pd.DataFrame, threshold: float = 10.0) -> pd.DataFrame:
    """Mean gap, row count, and % flagged, one row per subject -- ranked
    subject-level view for the alignment table, sorted most-inflated first."""
    g = benchmark_df.groupby("subjectName")["gap (pp)"].agg(mean_gap="mean", n="count").reset_index()
    flagged = benchmark_df.assign(flag=benchmark_df["gap (pp)"] > threshold).groupby("subjectName")["flag"].mean()
    g["flagged_pct"] = g["subjectName"].map(flagged) * 100
    return g.sort_values("mean_gap", ascending=False)


def gap_by_teacher(benchmark_df: pd.DataFrame, threshold: float = 10.0) -> pd.DataFrame:
    """Same as gap_by_subject but grouped by (subject, teacher) -- the level KHDA
    audits actually operate at, since grade inflation is a marking-practice signal."""
    g = benchmark_df.groupby(["subjectName", "teacherName"])["gap (pp)"].agg(
        mean_gap="mean", n="count"
    ).reset_index()
    flagged = (
        benchmark_df.assign(flag=benchmark_df["gap (pp)"] > threshold)
        .groupby(["subjectName", "teacherName"])["flag"].mean()
    )
    g = g.set_index(["subjectName", "teacherName"])
    g["flagged_pct"] = flagged * 100
    return g.reset_index().sort_values("mean_gap", ascending=False)


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
