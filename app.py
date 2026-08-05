import sys
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parent))

import streamlit as st

from utils.styling import inject_css, page_header, callout
from utils.data_utils import load_data

st.set_page_config(
    page_title="School Insights",
    page_icon="🏫",
    layout="wide",
)
inject_css()

page_header("🏫 School Insights — Prototype")

st.markdown(
    """
This is a design prototype. It's running on **synthetic demo data** with the
same shape as the real dataset, so the layout and metrics can be reviewed
before wiring in real data and migrating to Frappe Insights.

Use the sidebar to pick a view:

- **🏫 School** — leadership / admin view, whole-school trends
- **👩‍🏫 Teacher** — a teacher's own classes, growth, and calibration
- **🎓 Student** — an individual student's own standing and trend
- **👪 Parent** — the same as the student view, in plain language

Each view pulls from the same underlying cleaned tables, so nothing is
computed twice or differently between roles.
"""
)

callout(
    "ℹ️ Data source: reading from <code>data/MSB_Private_School_2024-25_MASTER_ANON.csv</code> "
    "and <code>data/ReportExplorer_MASTER_ANON.csv</code> when present, falling back to "
    "synthetic demo data otherwise. Each page's caption tells you which one is active."
)

# DEBUG: Show data loading state
student_master, subject_term, is_demo = load_data()
st.write("DEBUG -- is_demo:", is_demo)
st.write("DEBUG -- student_master columns:", student_master.columns.tolist())
st.write("DEBUG -- subject_term columns:", subject_term.columns.tolist())
st.write("DEBUG -- student_master shape:", student_master.shape)
