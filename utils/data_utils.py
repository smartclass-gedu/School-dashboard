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
from urllib.parse import quote_plus

REPO_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = REPO_ROOT / "data"
F1_PATH = DATA_DIR / "MSB_Private_School_2024-25_MASTER_ANON.csv"
F2_PATH = DATA_DIR / "ReportExplorer_MASTER_ANON.csv"

TERMS = ["T1", "T2", "T3"]
SUBJECTS = ["Maths", "English", "Science", "Humanities", "Art", "PE"]
YEAR_GROUPS = list(range(1, 12))  # Grade/Year 1 through 11

# CAT4 letter grade <-> the discrete externalTarget (%) banding it maps to in the
# source file (confirmed against the real data: A*=90, A=80, B=70, C=60, D=50,
# E=40, F=0, with a small number of noisy E/F rows folded into the dominant band).
CAT4_GRADE_TO_PCT = {"A*": 90, "A": 80, "B": 70, "C": 60, "D": 50, "E": 40, "F": 0}
INFLATION_THRESHOLD_DEFAULT = 10  # pp; internal - external above this is flagged


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


def _generate_demo_benchmark(student_master: pd.DataFrame, subject_term: pd.DataFrame, seed: int = 7) -> pd.DataFrame:
    """Synthetic CAT4-style external benchmark, built on top of the already-generated
    demo student_master/subject_term so it stays consistent with the rest of the demo
    dataset. Mirrors the real file's coverage pattern: only the oldest year groups
    (proxy for the real data's Year 7-10-only CAT4 rollout) and roughly the same ~30%
    of students. A subset of teachers get a deliberate positive bias baked in, so the
    resulting chart actually has something to flag when reviewing the design."""
    rng = np.random.default_rng(seed)

    # per-(student, subject) internal % -- last recorded term score, same "current"
    # concept the rest of the app uses
    internal = (
        subject_term.sort_values("term")
        .groupby(["UPN", "subjectName"])
        .agg(internal_pct=("sheetPercentage", "last"), teacherName=("teacherName", "last"))
        .reset_index()
    )

    older_years = sorted(student_master["yearGroup"].unique())[-4:]  # proxy for "Year 7-10 only"
    eligible = student_master[student_master["yearGroup"].isin(older_years)]["UPN"].unique()
    eligible = pd.Series(eligible)
    benchmarked_students = set(eligible[rng.random(len(eligible)) < 0.30])

    bench = internal[internal["UPN"].isin(benchmarked_students)].copy()
    if len(bench) == 0:
        return bench.assign(yearGroup=[], regGroup=[], CAT4_grade=[], external_pct=[], **{"gap (pp)": []})

    # deliberately-biased teachers, so the demo shows a mix of aligned and inflated rows
    unique_teachers = pd.Series(sorted(bench["teacherName"].unique()))
    biased_teachers = set(unique_teachers.sample(frac=0.2, random_state=seed))
    bias = bench["teacherName"].isin(biased_teachers).map({True: 14, False: 0}).astype(float)

    noise = rng.normal(0, 5, size=len(bench))
    external_raw = (bench["internal_pct"].to_numpy() - bias.to_numpy() + noise).clip(0, 100)

    bands = np.array(sorted(set(CAT4_GRADE_TO_PCT.values())))
    nearest_idx = np.abs(external_raw[:, None] - bands[None, :]).argmin(axis=1)
    external_pct = bands[nearest_idx]
    pct_to_grade = {v: k for k, v in CAT4_GRADE_TO_PCT.items()}
    bench["external_pct"] = external_pct
    bench["CAT4_grade"] = [pct_to_grade[p] for p in external_pct]

    bench = bench.merge(student_master[["UPN", "yearGroup", "regGroup"]], on="UPN", how="left")
    bench["gap (pp)"] = bench["internal_pct"] - bench["external_pct"]
    return bench[["UPN", "yearGroup", "regGroup", "subjectName", "teacherName",
                  "CAT4_grade", "external_pct", "internal_pct", "gap (pp)"]]


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

    has_summative = sa[["UPN", "subjectName"]].drop_duplicates()
    has_summative["has_sa"] = True

    combined = pd.concat([sa, ca], ignore_index=True)
    combined = combined.merge(has_summative, on=["UPN", "subjectName"], how="left")
    combined["has_sa"] = combined["has_sa"].fillna(False)
    # keep Summative rows outright, and Continuous rows only where that
    # (student, subject) pair has no Summative data at all
    subject_term = combined[(combined["source"] == "Summative") | (~combined["has_sa"])]
    subject_term = subject_term[
        ["UPN", "subjectName", "teacherName", "term", "sheetPercentage", "predicted (%)", "teacherTarget (%)"]
    ].copy()

    return student_master, subject_term


def _load_real_benchmark() -> pd.DataFrame:
    """CAT4-derived external benchmark vs. internal grade, one row per (student,
    subject) -- the KHDA-relevant view: is the internal current (%) running ahead
    of what the CAT4 cognitive-ability battery would predict?

    Reads F1_PATH directly rather than reusing _load_real_data()'s df1_letter,
    since load_data() is a 3-tuple every existing page already unpacks and
    threading a 4th value through it would touch all four pages for no reason.
    CAT4 / externalTarget (%) are constant per (student, subject) -- same as
    current (%) / predicted (%) / teacherTarget (%) -- confirmed against the
    real file (max 1 distinct value per group)."""
    needed = ["UPN", "yearGroup", "regGroup", "subjectName", "teacherName",
              "CAT4", "externalTarget (%)", "current (%)"]
    df = pd.read_csv(F1_PATH, usecols=lambda c: c in needed, low_memory=False)
    df["UPN"] = df["UPN"].str.strip()
    df = df.dropna(subset=["CAT4", "externalTarget (%)"])

    bench = df.groupby(["UPN", "subjectName"]).agg(
        yearGroup=("yearGroup", "first"),
        regGroup=("regGroup", "first"),
        teacherName=("teacherName", "first"),
        CAT4_grade=("CAT4", "first"),
        external_pct=("externalTarget (%)", "first"),
        internal_pct=("current (%)", "mean"),
    ).reset_index()
    bench["gap (pp)"] = bench["internal_pct"] - bench["external_pct"]
    return bench[["UPN", "yearGroup", "regGroup", "subjectName", "teacherName",
                  "CAT4_grade", "external_pct", "internal_pct", "gap (pp)"]]


def _get_db_secrets():
    """Returns st.secrets["db"] if a [db] section is configured, else None.
    Safe to call even when no secrets.toml exists at all (local dev)."""
    try:
        if "db" in st.secrets:
            return st.secrets["db"]
    except Exception:
        pass
    return None


def _make_engine(db_config):
    """Builds the SQLAlchemy engine used by both the student/subject loader and
    the benchmark loader. Mirrors etl_to_mariadb.py's SSL handling: if db_config
    has an ssl_ca entry (as documented in .streamlit/secrets.toml.example for
    Aiven and most other managed MySQL/MariaDB hosts, which enforce SSL),
    resolve it relative to the repo root and pass it through connect_args --
    without this, a plain connection string to a host that requires SSL just
    fails to connect."""
    from sqlalchemy import create_engine
    url = (
        f"mysql+pymysql://{db_config['user']}:{quote_plus(db_config['password'])}"
        f"@{db_config['host']}:{db_config['port']}/{db_config['database']}"
    )

    connect_args = {}
    ssl_ca = db_config.get("ssl_ca") if hasattr(db_config, "get") else None
    if ssl_ca:
        ssl_ca_path = Path(ssl_ca)
        if not ssl_ca_path.is_absolute():
            ssl_ca_path = REPO_ROOT / ssl_ca_path
        connect_args["ssl"] = {"ca": str(ssl_ca_path)}

    return create_engine(url, connect_args=connect_args)


def _load_db_data(db_config):
    """Builds (student_master, subject_term) from a MySQL/MariaDB database.
    db_config is st.secrets["db"] with host/port/user/password/database keys.

    etl_to_mariadb.py writes these tables with snake_case columns (current_pct,
    reg_group, year_group, subject_name, ...) to satisfy MySQL/Aiven's primary-key
    and naming conventions. The rest of this app -- all four existing pages --
    expects the original CSV-style names (current (%), regGroup, yearGroup,
    subjectName, ...), so both tables need renaming right after the read, the
    same way _load_db_benchmark() already does for external_benchmark."""
    engine = _make_engine(db_config)

    student_master = pd.read_sql("SELECT * FROM student_master", engine)
    student_master = student_master.rename(columns={
        "current_pct": "current (%)", "predicted_pct": "predicted (%)",
        "teacher_target_pct": "teacherTarget (%)", "reg_group": "regGroup",
        "attendance_pct": "Attendance (%)", "prev_year_pct": "Previous year attainment (%)",
        "year_group": "yearGroup",
    })

    subject_term = pd.read_sql("SELECT * FROM subject_term", engine)
    subject_term = subject_term.rename(columns={
        "subject_name": "subjectName", "teacher_name": "teacherName",
        "sheet_percentage": "sheetPercentage", "predicted_pct": "predicted (%)",
        "teacher_target_pct": "teacherTarget (%)",
    })

    # recomputed fresh rather than trusting the DB's stored performance_band/at_risk,
    # same as _load_real_data() -- keeps the tertile/quartile cuts consistent with
    # whatever's actually in this student_master, not whatever was true at ETL time
    student_master["performance_band"] = pd.qcut(
        student_master["current (%)"], q=3, labels=["Low", "Medium", "High"]
    )
    risk_cutoff = student_master["current (%)"].quantile(0.25)
    student_master["at_risk"] = student_master["current (%)"] <= risk_cutoff

    return student_master, subject_term


def _load_db_benchmark(db_config) -> pd.DataFrame:
    """Reads the external_benchmark table written by etl_to_mariadb.py and renames
    its snake_case columns back to the naming convention the rest of this app uses."""
    engine = _make_engine(db_config)
    bench = pd.read_sql("SELECT * FROM external_benchmark", engine)
    return bench.rename(columns={
        "year_group": "yearGroup", "reg_group": "regGroup",
        "subject_name": "subjectName", "teacher_name": "teacherName",
        "cat4_grade": "CAT4_grade", "gap_pp": "gap (pp)",
    })


@st.cache_data(ttl=600)
def load_data():
    """
    Returns (student_master, subject_term, is_demo).
    Priority: MySQL/MariaDB via st.secrets["db"] > local CSVs in data/ > synthetic demo data.
    """
    db_config = _get_db_secrets()
    if db_config is not None:
        student_master, subject_term = _load_db_data(db_config)
        return student_master, subject_term, False

    if F1_PATH.exists() and F2_PATH.exists():
        student_master, subject_term = _load_real_data()
        return student_master, subject_term, False

    student_master, subject_term = _generate_demo_data()
    return student_master, subject_term, True


@st.cache_data(ttl=600)
def load_benchmark_data():
    """
    Returns (external_benchmark, is_demo) -- the CAT4-vs-internal-grade table behind
    the Benchmark page. Same source priority as load_data(), kept as a separate
    function so the four existing pages (which all unpack load_data() as a 3-tuple)
    don't need to change.

    Columns: UPN, yearGroup, regGroup, subjectName, teacherName, CAT4_grade,
    external_pct, internal_pct, "gap (pp)" (= internal_pct - external_pct; positive
    means the internal grade is running ahead of the CAT4-predicted grade -- the
    grade-inflation signal KHDA inspectors look for).
    """
    db_config = _get_db_secrets()
    if db_config is not None:
        try:
            return _load_db_benchmark(db_config), False
        except Exception:
            pass  # table not migrated yet on this DB -- fall through to CSV/demo

    if F1_PATH.exists():
        return _load_real_benchmark(), False

    student_master, subject_term = _generate_demo_data()
    return _generate_demo_benchmark(student_master, subject_term), True


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
