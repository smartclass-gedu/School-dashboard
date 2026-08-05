"""
Data loading layer for the school dashboard.

Real mode: reads the two source files, using the same cleaning logic
established in the EDA notebooks (dead-column drop, percent parsing,
UPN-based joins).

Demo mode: if the real files aren't found, generates a synthetic dataset
with the identical schema so the dashboard can be reviewed and designed
before real data is wired in.
"""

import numpy as np
import pandas as pd
import re
import streamlit as st
from pathlib import Path
from sqlalchemy import create_engine

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
F1_PATH = DATA_DIR / "MSB_Private_School_2024-25_MASTER_ANON.csv"
F2_PATH = DATA_DIR / "ReportExplorer_MASTER_ANON.csv"

TERMS = ["T1", "T2", "T3"]
SUBJECTS = ["Maths", "English", "Science", "Humanities", "Art", "PE"]
YEAR_GROUPS = list(range(1, 12))  # Grade/Year 1 through 11


# ---------------------------------------------------------------------------
# Synthetic demo data (same schema as the real files, so swapping in real
# data later is just pointing DATA_DIR at the real CSVs)
# ---------------------------------------------------------------------------
@st.cache_data
def _generate_demo_data(n_students: int = 300, seed: int = 42):
    rng = np.random.default_rng(seed)

    upns = [f"DEMO{1000 + i}" for i in range(n_students)]
    year_group = rng.choice(YEAR_GROUPS, size=n_students)
    house = rng.choice(["Red", "Blue", "Green", "Yellow"], size=n_students)
    sex = rng.choice(["M", "F"], size=n_students)
    reg_group = [f"{yg}{h[0]}" for yg, h in zip(year_group, house)]

    # base academic ability per student drives everything downstream,
    # so predicted/current/prior are correlated the way real data is
    ability = rng.normal(70, 12, size=n_students).clip(30, 99)
    attendance = rng.normal(92, 6, size=n_students).clip(55, 100)

    teachers_per_subject = {
        s: [f"{s[:3]}-Teacher-{i}" for i in range(1, 4)] for s in SUBJECTS
    }

    student_master_rows = []
    subject_term_rows = []

    for i, upn in enumerate(upns):
        prior_year = (ability[i] + rng.normal(0, 4)).clip(30, 99)
        student_ability = ability[i]

        subj_currents, subj_predicted, subj_targets = [], [], []

        for subj in SUBJECTS:
            teacher = rng.choice(teachers_per_subject[subj])
            # teacher effect: some teachers systematically over/under predict
            teacher_bias = (hash(teacher) % 7) - 3  # -3..+3, deterministic per teacher
            subj_ability = (student_ability + rng.normal(0, 6)).clip(20, 100)

            target = (subj_ability + rng.normal(2, 3)).clip(20, 100)
            predicted = (subj_ability + teacher_bias + rng.normal(0, 3)).clip(20, 100)

            term_scores = []
            trend = rng.normal(0, 1.5)  # some students trend up, some down
            for t_idx, term in enumerate(TERMS):
                score = (subj_ability + trend * t_idx + rng.normal(0, 4)).clip(0, 100)
                term_scores.append(score)
                subject_term_rows.append(
                    {
                        "UPN": upn,
                        "subjectName": subj,
                        "teacherName": teacher,
                        "term": term,
                        "sheetPercentage": round(score, 1),
                        "predicted (%)": round(predicted, 1),
                        "teacherTarget (%)": round(target, 1),
                    }
                )

            current = term_scores[-1]
            subj_currents.append(current)
            subj_predicted.append(predicted)
            subj_targets.append(target)

        current_pct = float(np.mean(subj_currents))
        predicted_pct = float(np.mean(subj_predicted))
        target_pct = float(np.mean(subj_targets))

        student_master_rows.append(
            {
                "UPN": upn,
                "yearGroup": int(year_group[i]),
                "regGroup": reg_group[i],
                "House": house[i],
                "Sex": sex[i],
                "Attendance (%)": round(attendance[i], 1),
                "Previous year attainment (%)": round(prior_year, 1),
                "current (%)": round(current_pct, 1),
                "predicted (%)": round(predicted_pct, 1),
                "teacherTarget (%)": round(target_pct, 1),
            }
        )

    student_master = pd.DataFrame(student_master_rows)
    subject_term = pd.DataFrame(subject_term_rows)

    # performance band (tertiles) + at-risk flag (bottom quartile), matching
    # the modeling notebook's definitions
    student_master["performance_band"] = pd.qcut(
        student_master["current (%)"], q=3, labels=["Low", "Medium", "High"]
    )
    risk_cutoff = student_master["current (%)"].quantile(0.25)
    student_master["at_risk"] = student_master["current (%)"] <= risk_cutoff

    return student_master, subject_term


# ---------------------------------------------------------------------------
# Real data loader -- mirrors notebook 3, sections 0.1 and 2.1 exactly:
#   - current (%) / predicted (%) / teacherTarget (%) are CONSTANT per
#     (student, subject) -- one value, not per-term. Confirmed in notebook 3
#     Section 1 (the nunique-per-group check).
#   - The real per-term score is `sheetPercentage`, taken from rows whose
#     sheetName contains "Continuous Assessment" (e.g. "T1 - Continuous
#     Assessments"), with term (T1/T2/T3) extracted via regex.
# ---------------------------------------------------------------------------
def _is_pct_col(s: pd.Series) -> bool:
    if not (pd.api.types.is_string_dtype(s) or pd.api.types.is_object_dtype(s)):
        return False
    sample = s.dropna().astype(str).head(50)
    return len(sample) > 0 and sample.str.match(r"^\d+(\.\d+)?%$").sum() > len(sample) * 0.8


def _load_real_data():
    """Builds (student_master, subject_term) from the real CSVs, matching
    the demo schema exactly so every page works unchanged. Logic mirrors
    notebook 3 sections 0.1 (condensed load & clean) and 2.1 (student-level
    table build) precisely."""
    dead_cols_f1 = [
        "aspirational", "aspirational (%)", "additionalTarget",
        "additionalTarget (%)", "actual", "actual (%)",
    ]
    usecols = [c for c in pd.read_csv(F1_PATH, nrows=0).columns if c not in dead_cols_f1]
    df1 = pd.read_csv(F1_PATH, usecols=usecols, low_memory=False)
    df1["UPN"] = df1["UPN"].str.strip()

    # letter-graded rows only: drop free-text comments and progress tests,
    # which aren't percentage-graded subjects
    progress_test_subjects = [s for s in df1["subjectName"].unique() if "Progress Test" in str(s)]
    df1_letter = df1[
        (df1["subjectName"] != "Class Teacher Comments")
        & (~df1["subjectName"].isin(progress_test_subjects))
    ].copy()

    df2 = pd.read_csv(F2_PATH, low_memory=False)
    constant_cols = [c for c in df2.columns if df2[c].nunique(dropna=False) == 1]
    df2 = df2.drop(columns=constant_cols)
    df2["UPN"] = df2["UPN"].str.strip()
    pct_cols = [c for c in df2.columns if _is_pct_col(df2[c])]
    for c in pct_cols:
        df2[c] = pd.to_numeric(df2[c].astype(str).str.rstrip("%"), errors="coerce")

    # ---- student_master: one row per student -------------------------------
    agg1 = df1_letter.groupby("UPN").agg(
        **{
            "current (%)": ("current (%)", "mean"),
            "predicted (%)": ("predicted (%)", "mean"),
            "teacherTarget (%)": ("teacherTarget (%)", "mean"),
        }
    ).reset_index()

    prev_cols = [c for c in df2.columns if "percentage: Previous year attainment" in c]
    df2["Previous year attainment (%)"] = df2[prev_cols].mean(axis=1) if prev_cols else np.nan

    demo_cols = [
        c for c in
        ["UPN", "Sex", "House", "Registration group", "Attendance (%)", "Previous year attainment (%)"]
        if c in df2.columns
    ]
    demo = df2[demo_cols].rename(columns={"Registration group": "regGroup"})

    year_per_student = df1.groupby("UPN")["yearGroup"].first().reset_index()

    student_master = agg1.merge(demo, on="UPN", how="inner").merge(year_per_student, on="UPN", how="left")
    student_master["performance_band"] = pd.qcut(
        student_master["current (%)"], q=3, labels=["Low", "Medium", "High"]
    )
    risk_cutoff = student_master["current (%)"].quantile(0.25)
    student_master["at_risk"] = student_master["current (%)"] <= risk_cutoff

    # ---- subject_term: one row per (student, subject, term) ----------------
    # The real data has several assessment sheet types per term (Summative,
    # Continuous, Interim, AFL, ATL). Coverage differs a lot: "Summative
    # Assessment" covers ~87% of students with even T1/T2/T3 coverage,
    # "Continuous Assessment" covers ~26% with much weaker T3 coverage.
    # Every student has at least one of the two, so: prefer Summative for a
    # given (student, subject) when it exists there, otherwise fall back to
    # Continuous for that same (student, subject) -- this gets 100% coverage
    # without mixing both assessment types for the same student-subject pair.
    def _extract_term_rows(sheet_contains: str, source_label: str) -> pd.DataFrame:
        rows = df1_letter[df1_letter["sheetName"].astype(str).str.contains(sheet_contains, na=False)].copy()
        rows["term"] = rows["sheetName"].astype(str).str.extract(r"(T\d)")
        rows = rows.dropna(subset=["term"])
        rows["source"] = source_label
        return rows

    sa = _extract_term_rows("Summative Assessment", "Summative")
    ca = _extract_term_rows("Continuous Assessment", "Continuous")

    # Version-safe membership check (avoids merge + fillna(False) downcasting,
    # which behaves inconsistently across pandas versions and can silently
    # let duplicate Continuous rows slip through for students who have both
    # assessment types for the same subject).
    sa_pairs = set(zip(sa["UPN"], sa["subjectName"]))
    combined = pd.concat([sa, ca], ignore_index=True)
    combined["has_sa"] = [
        (upn, subj) in sa_pairs for upn, subj in zip(combined["UPN"], combined["subjectName"])
    ]
    # keep Summative rows outright, and Continuous rows only where that
    # (student, subject) pair has no Summative data at all
    subject_term = combined[(combined["source"] == "Summative") | (~combined["has_sa"])]
    subject_term = subject_term[
        ["UPN", "subjectName", "teacherName", "term", "sheetPercentage", "predicted (%)", "teacherTarget (%)"]
    ].copy()

    return student_master, subject_term


# ---------------------------------------------------------------------------
# Database loader -- reads from MySQL/MariaDB using credentials in st.secrets
# ---------------------------------------------------------------------------
def _load_from_database():
    """
    Reads student_master and subject_term from a MySQL/MariaDB database.
    Expects st.secrets to have:
      ["db"]["host"], ["port"], ["user"], ["password"], ["database"]
    Optionally uses SSL (required for Aiven):
      ["db"]["ssl_ca"] = relative path to CA certificate (e.g. "certs/aiven-ca.pem")

    Returns (student_master, subject_term) with the same schema as the real
    and demo data loaders, ensuring seamless swaps between data sources.
    """
    secrets_paths = [
        Path.home() / ".streamlit" / "secrets.toml",
        Path(__file__).resolve().parent.parent / ".streamlit" / "secrets.toml",
    ]
    if not any(p.exists() for p in secrets_paths):
        return None, None

    try:
        db_config = st.secrets["db"]
    except (KeyError, AttributeError, FileNotFoundError):
        return None, None

    host = db_config.get("host")
    port = db_config.get("port", 3306)
    user = db_config.get("user")
    password = db_config.get("password")
    database = db_config.get("database")

    if not all([host, user, password, database]):
        return None, None

    try:
        conn_str = f"mysql+pymysql://{user}:{password}@{host}:{port}/{database}"
        connect_args = {}

        ssl_ca_path = db_config.get("ssl_ca")
        if ssl_ca_path:
            cert_path = Path(__file__).resolve().parent.parent / ssl_ca_path
            if cert_path.exists():
                connect_args["ssl"] = {"ca": str(cert_path)}
            else:
                st.warning(f"SSL certificate not found at {cert_path}. Attempting connection without SSL.")

        engine = create_engine(conn_str, connect_args=connect_args)

        student_master = pd.read_sql("SELECT * FROM student_master", engine)
        subject_term = pd.read_sql("SELECT * FROM subject_term", engine)

        # Rename database snake_case columns to match app's CSV-style column names
        # so all three data sources (demo, CSV, database) produce identical schemas
        student_master = student_master.rename(columns={
            "year_group": "yearGroup",
            "reg_group": "regGroup",
            "current_pct": "current (%)",
            "predicted_pct": "predicted (%)",
            "teacher_target_pct": "teacherTarget (%)",
            "attendance_pct": "Attendance (%)",
            "prev_year_pct": "Previous year attainment (%)",
        })
        subject_term = subject_term.rename(columns={
            "subject_name": "subjectName",
            "teacher_name": "teacherName",
            "sheet_percentage": "sheetPercentage",
            "predicted_pct": "predicted (%)",
            "teacher_target_pct": "teacherTarget (%)",
        })

        engine.dispose()
        return student_master, subject_term
    except Exception as e:
        st.warning(f"Database connection failed: {e}")
        return None, None


@st.cache_data
def load_data():
    """
    Returns (student_master, subject_term, is_demo).
    Priority order:
      1. If st.secrets["db"] exists, connect to that database and use it
      2. Else if local CSV files exist, use those (real data mode)
      3. Else fall back to synthetic demo data
    """
    # Try database first
    student_master, subject_term = _load_from_database()
    if student_master is not None and subject_term is not None:
        return student_master, subject_term, False

    # Fall back to local CSV files
    if F1_PATH.exists() and F2_PATH.exists():
        student_master, subject_term = _load_real_data()
        return student_master, subject_term, False

    # Final fallback to synthetic demo data
    student_master, subject_term = _generate_demo_data()
    return student_master, subject_term, True



def band_label(pct_rank: float) -> str:
    if pct_rank >= 0.67:
        return "Top third"
    elif pct_rank >= 0.33:
        return "Middle third"
    return "Bottom third"


def year_sort_key(year_group):
    """Sorts year groups naturally whether they're ints (demo data) or
    strings like 'Year 7' (real data) -- plain sorted() would put
    'Year 10' before 'Year 2' alphabetically."""
    if isinstance(year_group, (int, float)):
        return year_group
    match = re.search(r"\d+", str(year_group))
    return int(match.group()) if match else 0


def trend_slope(scores: list[float]) -> float:
    """Simple slope across term scores (T1..Tn), positive = improving."""
    if len(scores) < 2:
        return 0.0
    x = np.arange(len(scores))
    return float(np.polyfit(x, scores, 1)[0])
