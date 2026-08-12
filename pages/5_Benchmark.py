import sys
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parent.parent))

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

from utils.data_utils import load_benchmark_data, year_sort_key, INFLATION_THRESHOLD_DEFAULT
from utils.metrics import inflation_summary, gap_by_subject, gap_by_teacher
from utils.styling import (
    inject_css, page_header, stat_card, panel_header, apply_light_theme,
    PURPLE, BLUE, GREEN, RED, ORANGE, TEAL, HEATMAP_SCALE, BLUE_FAINT, BLUE_PALE,
)

st.set_page_config(page_title="Benchmark View", page_icon="📐", layout="wide")
inject_css()

benchmark, is_demo = load_benchmark_data()

page_header(
    "📐 External Benchmark Alignment",
    "Internal grades vs. CAT4 cognitive-ability benchmark" + (" · demo data" if is_demo else " · live data"),
)

st.caption(
    "KHDA inspectors compare internal marking against an external, standardized "
    "benchmark to check for grade inflation. CAT4 gives an externally-referenced "
    "expected grade per subject; this page compares it against the internal "
    "current grade for the same student and subject."
)

if len(benchmark) == 0:
    st.warning(
        "No CAT4-benchmarked rows found in the current data source. CAT4 is only "
        "administered to a subset of year groups, so this page will be empty if "
        "none of them are present in what's loaded.",
        icon="⚠️",
    )
    st.stop()

# ---------------------------------------------------------------------------
# Filter bar -- cascading, same pattern as the School page
# ---------------------------------------------------------------------------
f1, f2, f3, f4 = st.columns(4)
with f1:
    grade_filter = st.selectbox(
        "Select Grade Level",
        ["All Grades"] + sorted(benchmark["yearGroup"].unique().tolist(), key=year_sort_key),
    )
bm_scope = benchmark if grade_filter == "All Grades" else benchmark[benchmark["yearGroup"] == grade_filter]

with f2:
    subject_options = sorted(bm_scope["subjectName"].unique().tolist())
    subject_filter = st.selectbox("Select Subject", ["All Subjects"] + subject_options)
bm_scope = bm_scope if subject_filter == "All Subjects" else bm_scope[bm_scope["subjectName"] == subject_filter]

with f3:
    teacher_options = sorted(bm_scope["teacherName"].unique().tolist())
    teacher_filter = st.selectbox("Select Teacher", ["All Teachers"] + teacher_options)
bm_scope = bm_scope if teacher_filter == "All Teachers" else bm_scope[bm_scope["teacherName"] == teacher_filter]

with f4:
    threshold = st.slider(
        "Flag threshold (internal − external, pp)", min_value=5, max_value=30,
        value=INFLATION_THRESHOLD_DEFAULT, step=1,
    )

st.markdown("<div style='height:6px'></div>", unsafe_allow_html=True)

# ---------------------------------------------------------------------------
# KPI row
# ---------------------------------------------------------------------------
summary = inflation_summary(bm_scope, threshold)
subj_gaps = gap_by_subject(bm_scope, threshold)
most_inflated = subj_gaps.iloc[0]["subjectName"] if len(subj_gaps) else "—"

k1, k2, k3, k4 = st.columns(4)
with k1:
    stat_card("Student-Subject Pairs Benchmarked", f"{summary['n']}", accent=PURPLE)
with k2:
    stat_card(
        "Avg Gap (Internal − External)", f"{summary['mean_gap']:+.1f}pp",
        "positive = internal ahead of CAT4", summary["mean_gap"] <= 5, accent=BLUE,
    )
with k3:
    stat_card(
        f"Flagged (> {threshold}pp)", f"{summary['flagged_pct']:.1f}%",
        f"{summary['flagged_n']} of {summary['n']}", summary["flagged_pct"] < 20, accent=RED,
    )
with k4:
    stat_card("Most-Inflated Subject", most_inflated, accent=ORANGE)

st.markdown("<div style='height:4px'></div>", unsafe_allow_html=True)

# ---------------------------------------------------------------------------
# Row: alignment scatter + gap-by-subject bar
# ---------------------------------------------------------------------------
col_a, col_b = st.columns(2)

with col_a:
    st.markdown('<div class="chart-panel">', unsafe_allow_html=True)
    panel_header("CAT4 vs. Internal Grade", "Each dot is one student-subject pair; the dotted line is perfect alignment")
    plot_df = bm_scope.copy()
    plot_df["Flagged"] = plot_df["gap (pp)"] > threshold
    fig = px.scatter(
        plot_df, x="external_pct", y="internal_pct", color="Flagged",
        color_discrete_map={True: RED, False: BLUE},
        hover_data=["subjectName", "teacherName", "CAT4_grade"],
    )
    fig.add_shape(type="line", x0=0, y0=0, x1=100, y1=100, line=dict(dash="dot", color=BLUE_PALE))
    fig = apply_light_theme(fig)
    fig.update_layout(height=320, xaxis_title="External (CAT4-predicted) %", yaxis_title="Internal (current) %")
    st.plotly_chart(fig, use_container_width=True)
    st.markdown('</div>', unsafe_allow_html=True)

with col_b:
    st.markdown('<div class="chart-panel">', unsafe_allow_html=True)
    panel_header("Average Gap by Subject", "Internal − external, ranked most-inflated first")
    if len(subj_gaps):
        fig = go.Figure(
            go.Bar(
                y=subj_gaps["subjectName"], x=subj_gaps["mean_gap"], orientation="h",
                marker_color=[RED if v > threshold else (ORANGE if v > 0 else BLUE) for v in subj_gaps["mean_gap"]],
            )
        )
        fig.add_vline(x=0, line_dash="dot", line_color=BLUE_PALE)
        fig = apply_light_theme(fig)
        fig.update_layout(height=320, xaxis_title="Avg gap (pp)")
        st.plotly_chart(fig, use_container_width=True)
    st.markdown('</div>', unsafe_allow_html=True)

# ---------------------------------------------------------------------------
# Ranked table: subject x teacher
# ---------------------------------------------------------------------------
st.markdown('<div class="chart-panel">', unsafe_allow_html=True)
panel_header("Ranked Alignment by Subject & Teacher", "Sorted by average gap, most-inflated first — this is the grain KHDA audits typically operate at")
teacher_gaps = gap_by_teacher(bm_scope, threshold)
if len(teacher_gaps):
    view = teacher_gaps.rename(columns={
        "subjectName": "Subject", "teacherName": "Teacher", "mean_gap": "Avg Gap (pp)",
        "n": "Students", "flagged_pct": "% Flagged",
    })
    view["Avg Gap (pp)"] = view["Avg Gap (pp)"].round(1)
    view["% Flagged"] = view["% Flagged"].round(0)
    st.dataframe(
        view.style.background_gradient(subset=["Avg Gap (pp)"], cmap=HEATMAP_SCALE),
        use_container_width=True, hide_index=True,
    )
st.markdown('</div>', unsafe_allow_html=True)

# ---------------------------------------------------------------------------
# Transparency notes
# ---------------------------------------------------------------------------
with st.expander("ℹ️ What is CAT4, and how is the gap calculated?"):
    st.markdown(
        "CAT4 (Cognitive Abilities Test) is an externally standardized, "
        "content-free battery -- unlike internal assessments, it isn't written or "
        "marked by the school's own teachers, which is why KHDA treats it as a "
        "reference point rather than something a school could inflate.\n\n"
        "Each student's CAT4-derived expected grade is converted here to a "
        "percentage band (A\\*=90, A=80, B=70, C=60, D=50, E=40, F=0) and compared "
        "against that same student's internal current (%) grade in the same "
        "subject. `gap (pp) = internal − external`: a large positive gap means the "
        "internal grade is running well ahead of what the external benchmark would "
        "predict -- the pattern KHDA inspectors look for as a grade-inflation "
        "signal, not a definitive finding on its own."
    )

with st.expander("📋 Coverage & limitations"):
    st.markdown(
        "CAT4 is only administered to a subset of year groups and subjects, so "
        "this page will only ever cover the students who sat it -- it is not a "
        "whole-school comparison the way the School page's other charts are. "
        "A gap flag is a starting point for a conversation about marking "
        "consistency, not proof of inflation on its own: cohort ability mix, "
        "timing of the CAT4 sitting relative to the internal assessment, and "
        "genuine teaching impact can all move this number too."
    )
