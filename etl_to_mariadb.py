"""
ETL: load the two real school CSVs into MariaDB/MySQL, producing the same
student_master / subject_term tables the Streamlit dashboard already uses.

This intentionally duplicates the cleaning logic from
school_dashboard/utils/data_utils.py's _load_real_data() -- same column
mapping, same Summative-preferred-over-Continuous term extraction -- so
Frappe Insights and the Streamlit app show identical numbers.

Run this any time the source CSVs are updated to refresh the analytics DB.

Usage:
    pip install pandas numpy sqlalchemy pymysql --break-system-packages
    python etl_to_mariadb.py

Configure via environment variables (see below) rather than editing this
file -- keeps real credentials out of anything that might get committed.
"""

import os
import numpy as np
import pandas as pd
from pathlib import Path

# ---------------------------------------------------------------------------
# Config -- all overridable via environment variables. Defaults below match
# the local Docker MariaDB from earlier; set env vars to point at Aiven (or
# any other host) instead, without editing this file.
# ---------------------------------------------------------------------------
DATA_DIR = Path("data")  # folder containing the two CSVs, relative to this script
F1_PATH = DATA_DIR / "MSB_Private_School_2024-25_MASTER_ANON.csv"
F2_PATH = DATA_DIR / "ReportExplorer_MASTER_ANON.csv"

DB_USER = os.environ.get("DB_USER", "root")
DB_PASSWORD = os.environ.get("DB_PASSWORD", "changeme123")
DB_HOST = os.environ.get("DB_HOST", "localhost")
DB_PORT = int(os.environ.get("DB_PORT", "3307"))   # 3307 matches local Docker; Aiven uses its own port
DB_NAME = os.environ.get("DB_NAME", "school_analytics")
DB_SSL_CA = os.environ.get("DB_SSL_CA")  # path to ca.pem relative to repo root (e.g. "certs/aiven-ca.pem") -- required for Aiven, unset for local Docker


def _is_pct_col(s: pd.Series) -> bool:
    if not (pd.api.types.is_string_dtype(s) or pd.api.types.is_object_dtype(s)):
        return False
    sample = s.dropna().astype(str).head(50)
    return len(sample) > 0 and sample.str.match(r"^\d+(\.\d+)?%$").sum() > len(sample) * 0.8


def load_and_clean():
    dead_cols_f1 = [
        "aspirational", "aspirational (%)", "additionalTarget",
        "additionalTarget (%)", "actual", "actual (%)",
    ]
    usecols = [c for c in pd.read_csv(F1_PATH, nrows=0).columns if c not in dead_cols_f1]
    df1 = pd.read_csv(F1_PATH, usecols=usecols, low_memory=False)
    df1["UPN"] = df1["UPN"].str.strip()

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

    # ---- student_master ----
    agg1 = df1_letter.groupby("UPN").agg(**{
        "current_pct": ("current (%)", "mean"),
        "predicted_pct": ("predicted (%)", "mean"),
        "teacher_target_pct": ("teacherTarget (%)", "mean"),
    }).reset_index()

    prev_cols = [c for c in df2.columns if "percentage: Previous year attainment" in c]
    df2["prev_year_pct"] = df2[prev_cols].mean(axis=1) if prev_cols else np.nan

    demo_cols = [c for c in ["UPN", "Sex", "House", "Registration group", "Attendance (%)", "prev_year_pct"]
                 if c in df2.columns]
    demo = df2[demo_cols].rename(columns={
        "Registration group": "reg_group", "Attendance (%)": "attendance_pct",
    })

    year_per_student = df1.groupby("UPN")["yearGroup"].first().reset_index().rename(
        columns={"yearGroup": "year_group"}
    )

    student_master = agg1.merge(demo, on="UPN", how="inner").merge(year_per_student, on="UPN", how="left")
    student_master["performance_band"] = pd.qcut(
        student_master["current_pct"], q=3, labels=["Low", "Medium", "High"]
    )
    risk_cutoff = student_master["current_pct"].quantile(0.25)
    student_master["at_risk"] = student_master["current_pct"] <= risk_cutoff

    # ---- subject_term: prefer Summative Assessment, fall back to Continuous ----
    def extract_term_rows(sheet_contains, source_label):
        rows = df1_letter[df1_letter["sheetName"].astype(str).str.contains(sheet_contains, na=False)].copy()
        rows["term"] = rows["sheetName"].astype(str).str.extract(r"(T\d)")
        rows = rows.dropna(subset=["term"])
        rows["source"] = source_label
        return rows

    sa = extract_term_rows("Summative Assessment", "Summative")
    ca = extract_term_rows("Continuous Assessment", "Continuous")

    # Version-safe membership check (avoids merge + fillna(False) downcasting,
    # which behaves differently across pandas versions and silently changed
    # row counts between environments).
    sa_pairs = set(zip(sa["UPN"], sa["subjectName"]))
    combined = pd.concat([sa, ca], ignore_index=True)
    combined["has_sa"] = [
        (upn, subj) in sa_pairs for upn, subj in zip(combined["UPN"], combined["subjectName"])
    ]
    subject_term = combined[(combined["source"] == "Summative") | (~combined["has_sa"])]
    subject_term = subject_term[
        ["UPN", "subjectName", "teacherName", "term", "sheetPercentage", "predicted (%)", "teacherTarget (%)"]
    ].rename(columns={
        "subjectName": "subject_name", "teacherName": "teacher_name",
        "sheetPercentage": "sheet_percentage", "predicted (%)": "predicted_pct",
        "teacherTarget (%)": "teacher_target_pct",
    }).copy()

    return student_master, subject_term


def write_to_mariadb(student_master: pd.DataFrame, subject_term: pd.DataFrame):
    from sqlalchemy import create_engine, text
    conn_str = f"mysql+pymysql://{DB_USER}:{DB_PASSWORD}@{DB_HOST}:{DB_PORT}/{DB_NAME}"

    connect_args = {}
    if DB_SSL_CA:
        # Aiven (and most managed MySQL/MariaDB hosts) require SSL. pymysql
        # expects the CA cert path nested under a "ssl" dict.
        cert_path = Path(__file__).resolve().parent / DB_SSL_CA
        if cert_path.exists():
            connect_args["ssl"] = {"ca": str(cert_path)}
        else:
            print(f"Warning: SSL certificate not found at {cert_path}. Attempting connection without SSL.")

    engine = create_engine(conn_str, connect_args=connect_args)

    student_master = student_master.copy()
    student_master["performance_band"] = student_master["performance_band"].astype(str)

    # Aiven (and most managed MySQL hosts) enforce sql_require_primary_key,
    # which pandas.to_sql's auto-created tables don't satisfy on their own.
    # So: create both tables explicitly with a real PRIMARY KEY first, then
    # append the data into them (rather than letting to_sql create the
    # table itself).
    with engine.begin() as conn:
        conn.execute(text("DROP TABLE IF EXISTS student_master"))
        conn.execute(text("""
            CREATE TABLE student_master (
                UPN VARCHAR(64) PRIMARY KEY,
                current_pct DOUBLE,
                predicted_pct DOUBLE,
                teacher_target_pct DOUBLE,
                Sex TEXT,
                House TEXT,
                reg_group TEXT,
                attendance_pct DOUBLE,
                prev_year_pct DOUBLE,
                year_group TEXT,
                performance_band TEXT,
                at_risk BOOLEAN
            )
        """))

        conn.execute(text("DROP TABLE IF EXISTS subject_term"))
        conn.execute(text("""
            CREATE TABLE subject_term (
                id INT AUTO_INCREMENT PRIMARY KEY,
                UPN VARCHAR(64),
                subject_name TEXT,
                teacher_name TEXT,
                term VARCHAR(8),
                sheet_percentage DOUBLE,
                predicted_pct DOUBLE,
                teacher_target_pct DOUBLE
            )
        """))

    student_master.to_sql("student_master", engine, if_exists="append", index=False, chunksize=1000)
    subject_term.to_sql("subject_term", engine, if_exists="append", index=False, chunksize=1000)

    print(f"Wrote {len(student_master)} rows to student_master")
    print(f"Wrote {len(subject_term)} rows to subject_term")


if __name__ == "__main__":
    print("Loading and cleaning CSVs...")
    student_master, subject_term = load_and_clean()
    print("Writing to MariaDB...")
    write_to_mariadb(student_master, subject_term)
    print("Done.")
