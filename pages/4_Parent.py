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
    inject_css, page_header, stat_card, panel_header, callout, apply_light_theme, gauge_chart,
    CHART_COLORWAY, BLUE_DEEP, BLUE_STRONG, BLUE_MED, BLUE_SOFT, BLUE_PALE,
)

st.set_page_config(page_title="Parent View", page_icon="👪", layout="wide")
inject_css()

student_master, subject_term, is_demo = load_data()

page_header("👪 Your Child's Progress", "Parent view" + (" · demo data" if is_demo else " · live data"))

# ---------------------------------------------------------------------------
# Filter bar -- child, then subject (subject filter drives the two trend
# charts further down; everything else on this page covers all subjects)
# ---------------------------------------------------------------------------
students = sorted(student_master["UPN"].unique())
f1, f2 = st.columns([1.2, 1])
with f1:
    selected_upn = st.selectbox("Viewing your child:", students)

me = student_master[student_master["UPN"] == selected_upn].iloc[0]
my_rows = subject_term[subject_term["UPN"] == selected_upn]
year_peers = student_master[student_master["yearGroup"] == me["yearGroup"]]

subj_summary = my_rows.groupby("subjectName").agg(
    current=("sheetPercentage", "last"),
    target=("teacherTarget (%)", "mean"),
).reset_index()

if len(subj_summary) == 0:
    st.warning(
        "No term-by-term subject data found for this student. This usually means "
        "their records don't have any 'Summative Assessment' or 'Continuous "
        "Assessment' sheet rows in the source file -- common if this student is "
        "from a different data export with a different sheet-naming convention.",
        icon="⚠️",
    )
    st.stop()

with f2:
    subject_view = st.selectbox(
        "Filter trend charts by subject:", ["All Subjects"] + sorted(subj_summary["subjectName"].tolist()),
        key="parent_subject_view",
    )
trend_rows = my_rows if subject_view == "All Subjects" else my_rows[my_rows["subjectName"] == subject_view]

on_track = (subj_summary["current"] >= subj_summary["target"] - 3).sum()
total_subjects = len(subj_summary)
overall_current = subj_summary["current"].mean()
overall_gap = (subj_summary["current"] - subj_summary["target"]).mean()
overall_trend = my_rows.groupby("term")["sheetPercentage"].mean().reindex(TERMS)
term_delta = (overall_trend.iloc[-1] - overall_trend.iloc[0]) if overall_trend.notna().sum() >= 2 else 0

st.markdown("<div style='height:6px'></div>", unsafe_allow_html=True)

# ---------------------------------------------------------------------------
# KPI row (same numbers the child sees on their own page)
# ---------------------------------------------------------------------------
k1, k2, k3, k4 = st.columns(4)
with k1:
    stat_card("Overall Average", f"{overall_current:.1f}%", f"{term_delta:+.1f}pp since T1", term_delta >= 0, accent=BLUE_DEEP)
with k2:
    stat_card("Subjects On Track", f"{on_track}/{total_subjects}", accent=BLUE_STRONG)
with k3:
    stat_card("Gap vs Target", f"{overall_gap:+.1f}pp", accent=BLUE_MED)
with k4:
    stat_card("Attendance", f"{me['Attendance (%)']:.1f}%", accent=BLUE_SOFT)

# ---------------------------------------------------------------------------
# Plain-language summary
# ---------------------------------------------------------------------------
callout(
    f"<b>Your child is averaging {overall_current:.0f}% overall</b>, on track in "
    f"{on_track} of {total_subjects} subjects, with attendance at "
    f"<b>{me['Attendance (%)']:.0f}%</b>."
)

if me["at_risk"]:
    callout(
        f"⚠️ Your child's overall average is <b>{overall_current:.0f}%</b>, which is "
        f"currently in the lower range for their year group. This is worth a "
        f"conversation with their form tutor -- it's a flag to look into together, "
        f"not a fixed outcome."
    )
else:
    callout(f"✅ Overall average is <b>{overall_current:.0f}%</b> -- no academic flags at this time.")

st.markdown("<div style='height:6px'></div>", unsafe_allow_html=True)

# ---------------------------------------------------------------------------
# Per-subject, plain language
# ---------------------------------------------------------------------------
st.markdown('<div class="chart-panel">', unsafe_allow_html=True)
panel_header("By Subject")
table_rows = []
for _, row in subj_summary.iterrows():
    if pd.isna(row["target"]):
        status = "No target set"
    else:
        diff = row["current"] - row["target"]
        status = "On track" if diff >= -3 else "Slightly behind" if diff >= -10 else "Behind target"
    table_rows.append({"Subject": row["subjectName"], "Score": row["current"], "Status": status})
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
    panel_header("Progress Over the Year",
                  f"Showing {'all subjects' if subject_view == 'All Subjects' else subject_view}")
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
    st.caption("A gap means that term's results haven't been recorded yet.")
    st.markdown('</div>', unsafe_allow_html=True)

with col_gauge:
    st.markdown('<div class="chart-panel">', unsafe_allow_html=True)
    panel_header("Attendance")
    fig = gauge_chart(me["Attendance (%)"], "This year")
    st.plotly_chart(fig, use_container_width=True)
    st.markdown('</div>', unsafe_allow_html=True)

# ---------------------------------------------------------------------------
# Attendance alongside grades, plain language
# ---------------------------------------------------------------------------
st.markdown('<div class="chart-panel">', unsafe_allow_html=True)
panel_header(
    "Attendance Alongside Grades",
    f"Showing {'all subjects averaged' if subject_view == 'All Subjects' else subject_view} -- their own numbers only",
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
    "Attendance overall explains only a small part of grade variation, so a dip in one "
    "doesn't automatically explain a dip in the other -- this is just their own numbers side by side."
)
st.markdown('</div>', unsafe_allow_html=True)

# ---------------------------------------------------------------------------
# Band context, plain language
# ---------------------------------------------------------------------------
st.markdown('<div class="chart-panel">', unsafe_allow_html=True)
panel_header("How This Compares to Their Year Group", "No other individual student's data is shown or identifiable")
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
