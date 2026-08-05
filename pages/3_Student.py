import sys
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parent.parent))

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

from utils.data_utils import load_data, TERMS
from utils.metrics import band_of
from utils.styling import (
    inject_css, page_header, stat_card, panel_header, apply_light_theme, gauge_chart,
    BLUE_DEEP, BLUE_STRONG, BLUE_MED, BLUE_SOFT, BLUE_PALE, CHART_COLORWAY,
)

st.set_page_config(page_title="Student View", page_icon="🎓", layout="wide")
inject_css()

student_master, subject_term, is_demo = load_data()

page_header("🎓 My Performance", "Student view" + (" · demo data" if is_demo else " · live data"))

# ---------------------------------------------------------------------------
# Filter bar -- student, then subject (subject filter drives the two trend
# charts further down; everything else on this page covers all subjects)
# ---------------------------------------------------------------------------
students = sorted(student_master["UPN"].unique())
f1, f2 = st.columns([1.2, 1])
with f1:
    selected_upn = st.selectbox("Viewing as student:", students)

me = student_master[student_master["UPN"] == selected_upn].iloc[0]
my_rows = subject_term[subject_term["UPN"] == selected_upn]
year_peers = student_master[student_master["yearGroup"] == me["yearGroup"]]

subj_summary = my_rows.groupby("subjectName").agg(
    current=("sheetPercentage", "last"),
    predicted=("predicted (%)", "mean"),
    target=("teacherTarget (%)", "mean"),
).reset_index()

if len(subj_summary) == 0:
    st.warning(
        "No term-by-term subject data found for this student. This usually means "
        "their records don't have any 'Summative Assessment' or 'Continuous "
        "Assessment' sheet rows in the source file -- common if this student is "
        "from a different data export with a different sheet-naming convention. "
        "The loader in `utils/data_utils.py` would need to be extended to handle "
        "that export's format.",
        icon="⚠️",
    )
    st.stop()

with f2:
    subject_view = st.selectbox(
        "Filter trend charts by subject:", ["All Subjects"] + sorted(subj_summary["subjectName"].tolist()),
        key="student_subject_view",
    )
trend_rows = my_rows if subject_view == "All Subjects" else my_rows[my_rows["subjectName"] == subject_view]

st.markdown("<div style='height:6px'></div>", unsafe_allow_html=True)

# ---------------------------------------------------------------------------
# KPI row
# ---------------------------------------------------------------------------
overall_current = subj_summary["current"].mean()
overall_gap = (subj_summary["current"] - subj_summary["target"]).mean()
on_track_n = (subj_summary["current"] >= subj_summary["target"] - 3).sum()
overall_trend = my_rows.groupby("term")["sheetPercentage"].mean().reindex(TERMS)
term_delta = (overall_trend.iloc[-1] - overall_trend.iloc[0]) if overall_trend.notna().sum() >= 2 else 0

k1, k2, k3, k4 = st.columns(4)
with k1:
    stat_card("Overall Average", f"{overall_current:.1f}%", f"{term_delta:+.1f}pp since T1", term_delta >= 0, accent=BLUE_DEEP)
with k2:
    stat_card("Subjects On Track", f"{on_track_n}/{len(subj_summary)}", accent=BLUE_STRONG)
with k3:
    stat_card("Gap vs Target", f"{overall_gap:+.1f}pp", accent=BLUE_MED)
with k4:
    stat_card("My Attendance", f"{me['Attendance (%)']:.1f}%", accent=BLUE_SOFT)

# ---------------------------------------------------------------------------
# Row: subject table + gauge
# ---------------------------------------------------------------------------
st.markdown('<div class="chart-panel">', unsafe_allow_html=True)
panel_header("Where You Stand, By Subject", "Current score vs. your own target")
table_rows = []
for _, row in subj_summary.iterrows():
    if pd.isna(row["target"]):
        target_str, gap_str, status = "—", "—", "No target set"
    else:
        gap = row["current"] - row["target"]
        target_str = f"{row['target']:.0f}%"
        gap_str = f"{gap:+.0f}pp"
        status = "On track" if gap >= -3 else "Behind target"
    table_rows.append({
        "Subject": row["subjectName"], "Score": row["current"],
        "Target": target_str, "Gap": gap_str, "Status": status,
    })
subject_table = pd.DataFrame(table_rows)
st.dataframe(
    subject_table,
    column_config={
        "Score": st.column_config.ProgressColumn("Score (%)", min_value=0, max_value=100, format="%.0f%%"),
    },
    hide_index=True, use_container_width=True,
)
st.markdown('</div>', unsafe_allow_html=True)

col_wide, col_gauge = st.columns([2, 1])

with col_wide:
    st.markdown('<div class="chart-panel">', unsafe_allow_html=True)
    panel_header("Your Trend This Year",
                  f"Showing {'all subjects' if subject_view == 'All Subjects' else subject_view}, term by term")
    trend_data = trend_rows.groupby(["subjectName", "term"])["sheetPercentage"].mean().reset_index()
    full_idx = pd.MultiIndex.from_product([trend_data["subjectName"].unique(), TERMS],
                                            names=["subjectName", "term"])
    trend_data = trend_data.set_index(["subjectName", "term"]).reindex(full_idx).reset_index()
    fig = px.line(
        trend_data, x="term", y="sheetPercentage", color="subjectName",
        markers=True, category_orders={"term": TERMS},
        color_discrete_sequence=CHART_COLORWAY,
    )
    fig = apply_light_theme(fig)
    fig.update_layout(height=280, yaxis_title="%")
    st.plotly_chart(fig, use_container_width=True)
    st.caption("A gap or missing term means that term's assessments haven't been recorded yet.")
    st.markdown('</div>', unsafe_allow_html=True)

with col_gauge:
    st.markdown('<div class="chart-panel">', unsafe_allow_html=True)
    panel_header("Overall Standing")
    fig = gauge_chart(overall_current, "Avg score")
    st.plotly_chart(fig, use_container_width=True)
    st.markdown('</div>', unsafe_allow_html=True)

# ---------------------------------------------------------------------------
# Band context (not raw rank)
# ---------------------------------------------------------------------------
st.markdown('<div class="chart-panel">', unsafe_allow_html=True)
panel_header("How You Compare", "Band within your year group -- no other student's data is shown")
band_rows = []
for _, row in subj_summary.iterrows():
    peer_scores = (
        subject_term[
            (subject_term["subjectName"] == row["subjectName"])
            & (subject_term["UPN"].isin(year_peers["UPN"]))
        ]
        .groupby("UPN")["sheetPercentage"]
        .mean()
    )
    band = band_of(row["current"], peer_scores)
    band_rows.append({"Subject": row["subjectName"], "Band": band})
st.dataframe(pd.DataFrame(band_rows), hide_index=True, use_container_width=True)
st.markdown('</div>', unsafe_allow_html=True)

# ---------------------------------------------------------------------------
# Attendance vs personal grade trend
# ---------------------------------------------------------------------------
st.markdown('<div class="chart-panel">', unsafe_allow_html=True)
panel_header(
    "Your Attendance Alongside Your Grades",
    f"Showing {'all subjects averaged' if subject_view == 'All Subjects' else subject_view} -- your own numbers only, not a schoolwide claim",
)
grade_trend = trend_rows.groupby("term")["sheetPercentage"].mean().reindex(TERMS)
fig = go.Figure()
fig.add_trace(go.Scatter(x=TERMS, y=grade_trend.values, name="Grade (%)",
                          yaxis="y1", line=dict(color=BLUE_DEEP, width=3), marker=dict(size=8)))
fig.add_trace(go.Scatter(x=TERMS, y=[me["Attendance (%)"]] * len(TERMS), name="Attendance (%)",
                          yaxis="y2", line=dict(dash="dot", color=BLUE_PALE)))
fig = apply_light_theme(fig)
fig.update_layout(
    height=280,
    yaxis=dict(title="Grade (%)"),
    yaxis2=dict(title="Attendance (%)", overlaying="y", side="right"),
)
st.plotly_chart(fig, use_container_width=True)
st.caption(
    "This shows your own attendance next to your own grades over time. "
    "Schoolwide, attendance explains only a small part of grade variation -- "
    "so a dip in one doesn't automatically explain a dip in the other."
)
st.markdown('</div>', unsafe_allow_html=True)
