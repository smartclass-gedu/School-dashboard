import sys
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parent.parent))

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

from utils.data_utils import load_data, TERMS, year_sort_key
from utils.metrics import (
    at_risk_rate,
    declining_students,
    correlation_with_p,
    anova_across_groups,
    summary_stats,
)
from utils.styling import (
    inject_css, page_header, stat_card, panel_header, apply_light_theme, gauge_chart,
    PURPLE, BLUE, GREEN, RED, ORANGE, TEAL, HEATMAP_SCALE, BLUE_FAINT, CHART_COLORWAY,
)

st.set_page_config(page_title="School View", page_icon="🏫", layout="wide")
inject_css()

student_master, subject_term, is_demo = load_data()

page_header("🏫 Student Performance Dashboard", "School Academic Performance" + (" · demo data" if is_demo else " · live data"))

# ---------------------------------------------------------------------------
# Filter bar -- cascading: each dropdown only offers options that actually
# exist within whatever's selected above it (grades don't all offer the same
# subjects/sections -- e.g. Year 1 has 8 subjects, Year 10 has 23, and
# section codes like "1A" vs "10A" are grade-specific).
# ---------------------------------------------------------------------------
with st.container():
    f1, f2, f3, f4, f5 = st.columns(5)
    with f1:
        grade_filter = st.selectbox("Select Grade Level", ["All Grades"] + sorted(student_master["yearGroup"].unique().tolist(), key=year_sort_key))

    sm_scope = student_master if grade_filter == "All Grades" else student_master[student_master["yearGroup"] == grade_filter]

    with f2:
        section_options = sorted(sm_scope["regGroup"].unique().tolist())
        section_filter = st.selectbox("Select Section", ["All Sections"] + section_options)

    sm_scope = sm_scope if section_filter == "All Sections" else sm_scope[sm_scope["regGroup"] == section_filter]
    st_scope = subject_term[subject_term["UPN"].isin(sm_scope["UPN"])]

    with f3:
        subject_options = sorted(st_scope["subjectName"].unique().tolist())
        subject_filter = st.selectbox("Select Subject", ["All Subjects"] + subject_options)

    if subject_filter != "All Subjects":
        st_scope = st_scope[st_scope["subjectName"] == subject_filter]

    with f4:
        teacher_options = sorted(st_scope["teacherName"].unique().tolist())
        teacher_filter = st.selectbox("Select Teacher", ["All Teachers"] + teacher_options)
    with f5:
        term_filter = st.selectbox("Select Term", ["All Terms"] + TERMS)

# apply filters
sm = student_master.copy()
st_ = subject_term.copy()
if grade_filter != "All Grades":
    sm = sm[sm["yearGroup"] == grade_filter]
    st_ = st_[st_["UPN"].isin(sm["UPN"])]
if section_filter != "All Sections":
    sm = sm[sm["regGroup"] == section_filter]
    st_ = st_[st_["UPN"].isin(sm["UPN"])]
if subject_filter != "All Subjects":
    st_ = st_[st_["subjectName"] == subject_filter]
if teacher_filter != "All Teachers":
    st_ = st_[st_["teacherName"] == teacher_filter]
if term_filter != "All Terms":
    st_ = st_[st_["term"] == term_filter]
# keep student master aligned to whichever students remain in the filtered subject_term
sm = sm[sm["UPN"].isin(st_["UPN"])] if len(st_) else sm

st.markdown("<div style='height:6px'></div>", unsafe_allow_html=True)

# ---------------------------------------------------------------------------
# KPI row 1
# ---------------------------------------------------------------------------
stats_current = summary_stats(sm["current (%)"]) if len(sm) else summary_stats(pd.Series([0]))
avg_score = st_["sheetPercentage"].mean() if len(st_) else 0
meeting_standard_pct = (sm["current (%)"] >= sm["teacherTarget (%)"] - 3).mean() * 100 if len(sm) else 0
top_performers = int((sm["current (%)"] >= 85).sum())
by_term = st_.groupby("term")["sheetPercentage"].mean().reindex(TERMS) if len(st_) else pd.Series()
term_delta = (by_term.iloc[-1] - by_term.iloc[0]) if by_term.notna().sum() >= 2 else 0

k1, k2, k3, k4, k5, k6 = st.columns(6)
with k1:
    stat_card("Total Students", f"{len(sm)}", accent=PURPLE)
with k2:
    stat_card("Avg Score (%)", f"{avg_score:.1f}%", f"{term_delta:+.1f}pp T1→T3", term_delta >= 0, accent=BLUE)
with k3:
    stat_card("Meeting Standards", f"{meeting_standard_pct:.1f}%", "within 3pp of target", meeting_standard_pct >= 70, accent=GREEN)
with k4:
    stat_card("Top Performers", f"{top_performers}", f"{top_performers/len(sm)*100:.0f}% of cohort" if len(sm) else "0%", accent=TEAL)
with k5:
    risk_pct = at_risk_rate(sm) * 100 if len(sm) else 0
    stat_card("At-Risk Students", f"{risk_pct:.1f}%", f"{int(sm['at_risk'].sum()) if len(sm) else 0} students", risk_pct < 25, accent=RED)
with k6:
    stat_card("Avg Attendance", f"{sm['Attendance (%)'].mean():.1f}%" if len(sm) else "—", accent=ORANGE)

st.markdown("<div style='height:4px'></div>", unsafe_allow_html=True)

# ---------------------------------------------------------------------------
# Row: performance progression (left, wide) + gauge + donut (right)
# ---------------------------------------------------------------------------
col_wide, col_gauge, col_donut = st.columns([2, 1, 1])

with col_wide:
    st.markdown('<div class="chart-panel">', unsafe_allow_html=True)
    panel_header("Performance Progression", "Average score by term")
    if len(st_):
        prog = st_.groupby("term")["sheetPercentage"].mean().reindex(TERMS).reset_index()
        fig = go.Figure()
        fig.add_trace(go.Scatter(x=prog["term"], y=prog["sheetPercentage"], mode="lines+markers",
                                  line=dict(color=PURPLE, width=3), marker=dict(size=9),
                                  fill="tozeroy", fillcolor="rgba(11,83,148,0.08)", name="Avg Score"))
        fig = apply_light_theme(fig)
        fig.update_layout(height=260, yaxis_title="Avg Score (%)")
        st.plotly_chart(fig, use_container_width=True)
    st.markdown('</div>', unsafe_allow_html=True)

with col_gauge:
    st.markdown('<div class="chart-panel">', unsafe_allow_html=True)
    panel_header("School Health Index")
    idx = (
        (sm["current (%)"].mean() if len(sm) else 0) * 0.5
        + (sm["Attendance (%)"].mean() if len(sm) else 0) * 0.3
        + (100 - risk_pct) * 0.2
    )
    fig = gauge_chart(idx, "Composite score")
    st.plotly_chart(fig, use_container_width=True)
    st.caption("50% avg score · 30% attendance · 20% (100 − at-risk %)")
    st.markdown('</div>', unsafe_allow_html=True)

with col_donut:
    st.markdown('<div class="chart-panel">', unsafe_allow_html=True)
    panel_header("Mastery Distribution")
    if len(sm):
        band_counts = sm["performance_band"].value_counts().reindex(["Low", "Medium", "High"]).fillna(0)
        fig = go.Figure(
            go.Pie(
                labels=["Needs Support", "On Track", "Excelling"],
                values=band_counts.values,
                hole=0.55,
                marker=dict(colors=[RED, ORANGE, GREEN]),
            )
        )
        fig = apply_light_theme(fig)
        fig.update_layout(height=260, showlegend=True)
        st.plotly_chart(fig, use_container_width=True)
    st.markdown('</div>', unsafe_allow_html=True)

# ---------------------------------------------------------------------------
# Row: subject performance dual-bar + academic standards heatmap
# ---------------------------------------------------------------------------
col_a, col_b = st.columns(2)

with col_a:
    st.markdown('<div class="chart-panel">', unsafe_allow_html=True)
    panel_header("Subject Performance", "Actual vs. predicted, by subject")
    if len(st_):
        subj_perf = st_.groupby("subjectName").agg(
            actual=("sheetPercentage", "mean"), predicted=("predicted (%)", "mean")
        ).reset_index().sort_values("actual")
        fig = go.Figure()
        fig.add_trace(go.Bar(y=subj_perf["subjectName"], x=subj_perf["actual"], name="Actual",
                              orientation="h", marker_color=PURPLE))
        fig.add_trace(go.Bar(y=subj_perf["subjectName"], x=subj_perf["predicted"], name="Predicted",
                              orientation="h", marker_color=BLUE_FAINT))
        fig = apply_light_theme(fig)
        fig.update_layout(barmode="group", height=280, xaxis_title="%")
        st.plotly_chart(fig, use_container_width=True)
    st.markdown('</div>', unsafe_allow_html=True)

with col_b:
    st.markdown('<div class="chart-panel">', unsafe_allow_html=True)
    panel_header("Academic Standards Heatmap", "Student count by mastery level × subject")
    if len(st_) and len(sm):
        merged_hm = st_.merge(sm[["UPN", "performance_band"]], on="UPN")
        hm = merged_hm.groupby(["performance_band", "subjectName"])["UPN"].nunique().unstack(fill_value=0)
        hm = hm.reindex(["Low", "Medium", "High"])
        fig = px.imshow(
            hm, text_auto=True, color_continuous_scale=HEATMAP_SCALE, aspect="auto",
            labels=dict(color="Students"),
        )
        fig = apply_light_theme(fig)
        fig.update_layout(height=280)
        st.plotly_chart(fig, use_container_width=True)
    st.markdown('</div>', unsafe_allow_html=True)

# ---------------------------------------------------------------------------
# Row: attendance correlation + declining trajectory + significance
# ---------------------------------------------------------------------------
col_c, col_d = st.columns(2)

with col_c:
    st.markdown('<div class="chart-panel">', unsafe_allow_html=True)
    panel_header("Attendance vs. Performance", "Each dot is one student")
    if len(sm) >= 3:
        r, p = correlation_with_p(sm["Attendance (%)"], sm["current (%)"])
        fig = px.scatter(
            sm, x="Attendance (%)", y="current (%)", color="performance_band",
            color_discrete_map={"Low": RED, "Medium": ORANGE, "High": GREEN}, trendline="ols",
            category_orders={"performance_band": ["Low", "Medium", "High"]},
        )
        fig = apply_light_theme(fig)
        fig.update_layout(height=280)
        st.plotly_chart(fig, use_container_width=True)
        st.caption(
            f"r = {r:.2f} (p = {p:.4f}) — attendance explains ~{r**2*100:.1f}% of grade variance. "
            f"{'Significant' if p < 0.05 else 'Not statistically significant'}."
        )
    st.markdown('</div>', unsafe_allow_html=True)

with col_d:
    st.markdown('<div class="chart-panel">', unsafe_allow_html=True)
    panel_header("Early Warning: Declining Trajectories", "Trending down T1→T3, not just currently low")
    if len(st_):
        declining = declining_students(st_, TERMS)
        declining_view = declining.merge(
            sm[["UPN", "yearGroup", "regGroup", "current (%)"]], on="UPN", how="inner"
        ).rename(columns={"slope": "Slope (pp/term)"})
        declining_view["Slope (pp/term)"] = declining_view["Slope (pp/term)"].round(2)
        declining_view = declining_view.sort_values("Slope (pp/term)").head(8)
        st.dataframe(declining_view, use_container_width=True, hide_index=True, height=250)
    st.markdown('</div>', unsafe_allow_html=True)

# ---------------------------------------------------------------------------
# Detailed student table, ranked
# ---------------------------------------------------------------------------
st.markdown('<div class="chart-panel">', unsafe_allow_html=True)
panel_header("Detailed Student Performance", "Ranked by current score, within current filters")
if len(sm):
    detail = sm[["UPN", "yearGroup", "regGroup", "current (%)", "predicted (%)", "Attendance (%)", "performance_band"]].copy()
    detail = detail.sort_values("current (%)", ascending=False).reset_index(drop=True)
    detail.insert(0, "Rank", range(1, len(detail) + 1))
    detail = detail.rename(columns={"performance_band": "Mastery Level", "yearGroup": "Grade", "regGroup": "Section"})
    st.dataframe(
        detail.head(15).style.background_gradient(subset=["current (%)"], cmap=HEATMAP_SCALE, vmin=40, vmax=100),
        use_container_width=True, hide_index=True,
    )
st.markdown('</div>', unsafe_allow_html=True)

# ---------------------------------------------------------------------------
# Significance + transparency notes
# ---------------------------------------------------------------------------
with st.expander("📐 Significance checks behind this dashboard"):
    if len(sm) >= 3:
        f_stat, p_val = anova_across_groups(sm, "yearGroup", "current (%)")
        st.markdown(f"- Year-group differences: ANOVA F={f_stat:.1f}, p={p_val:.4f} "
                    f"({'significant' if p_val < 0.05 else 'not significant'})")
        f_stat2, p_val2 = anova_across_groups(sm, "regGroup", "current (%)")
        st.markdown(f"- Class-level differences: ANOVA F={f_stat2:.1f}, p={p_val2:.4f} "
                    f"({'significant' if p_val2 < 0.05 else 'not significant'})")

with st.expander("ℹ️ Why isn't 'House' used anywhere in this dashboard?"):
    st.markdown(
        "Statistical testing found **House carries no learnable academic signal** — "
        "it's a pastoral/sports grouping, not an academic one. Showing it as a "
        "comparison dimension would imply a pattern that isn't real."
    )

with st.expander("📋 What this dashboard can't tell you yet"):
    st.markdown(
        "This covers academic performance and attendance only — nothing on "
        "wellbeing, staffing, admissions, finance, or facilities. Those would "
        "need separate data collection."
    )
