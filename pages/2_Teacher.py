import sys
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parent.parent))

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

from utils.data_utils import load_data, TERMS
from utils.metrics import calibration_bias, growth, r_squared, summary_stats
from utils.styling import (
    inject_css, page_header, stat_card, panel_header, apply_light_theme,
    PURPLE, BLUE, GREEN, RED, ORANGE, TEAL, HEATMAP_SCALE, BLUE_PALE, BLUE_MED, CHART_COLORWAY,
)

st.set_page_config(page_title="Teacher View", page_icon="👩‍🏫", layout="wide")
inject_css()

student_master, subject_term, is_demo = load_data()

page_header("👩‍🏫 Teacher Performance Dashboard",
            "Class & subject growth, calibration, and roster" + (" · demo data" if is_demo else " · live data"))

# ---------------------------------------------------------------------------
# Filter bar
# ---------------------------------------------------------------------------
teachers = sorted(subject_term["teacherName"].unique())
f1, f2, f3 = st.columns([1.4, 1, 1])
with f1:
    selected_teacher = st.selectbox("Viewing as teacher:", teachers)

my_rows_all = subject_term[subject_term["teacherName"] == selected_teacher]
my_subjects = sorted(my_rows_all["subjectName"].unique())

with f2:
    subject_filter = st.selectbox("Subject", ["All Subjects"] + my_subjects)
with f3:
    term_filter = st.selectbox("Term", ["All Terms"] + TERMS)

my_rows = my_rows_all.copy()
if subject_filter != "All Subjects":
    my_rows = my_rows[my_rows["subjectName"] == subject_filter]
if term_filter != "All Terms":
    my_rows = my_rows[my_rows["term"] == term_filter]

my_students = my_rows["UPN"].unique()
my_master = student_master[student_master["UPN"].isin(my_students)]

st.markdown("<div style='height:6px'></div>", unsafe_allow_html=True)

# ---------------------------------------------------------------------------
# Precompute
# ---------------------------------------------------------------------------
current_by_student = my_rows.groupby("UPN")["sheetPercentage"].mean()
prior_by_student = my_master.set_index("UPN")["Previous year attainment (%)"].reindex(current_by_student.index)
class_stats = summary_stats(current_by_student) if len(current_by_student) else summary_stats(pd.Series([0]))
bias = calibration_bias(my_rows["predicted (%)"], my_rows["sheetPercentage"]) if len(my_rows) else 0
r2 = r_squared(my_rows["predicted (%)"], my_rows["sheetPercentage"]) if len(my_rows) else 0
my_growth = growth(current_by_student, prior_by_student) if len(current_by_student) else 0

dept_rows = subject_term[subject_term["subjectName"].isin(my_subjects)]
all_teacher_growth, all_teacher_bias = {}, {}
for t in dept_rows["teacherName"].unique():
    t_rows = dept_rows[dept_rows["teacherName"] == t]
    t_students = t_rows["UPN"].unique()
    t_master = student_master[student_master["UPN"].isin(t_students)]
    t_current = t_rows.groupby("UPN")["sheetPercentage"].mean()
    t_prior = t_master.set_index("UPN")["Previous year attainment (%)"].reindex(t_current.index)
    all_teacher_growth[t] = growth(t_current, t_prior)
    all_teacher_bias[t] = calibration_bias(t_rows["predicted (%)"], t_rows["sheetPercentage"])
dept_growth_mean = pd.Series(all_teacher_growth).mean() if all_teacher_growth else 0

# ---------------------------------------------------------------------------
# KPI row
# ---------------------------------------------------------------------------
k1, k2, k3, k4, k5, k6 = st.columns(6)
with k1:
    stat_card("Students", f"{len(my_students)}", accent=PURPLE)
with k2:
    stat_card("Class Average", f"{class_stats['mean']:.1f}%", f"median {class_stats['median']:.1f}%", accent=BLUE)
with k3:
    stat_card("Growth vs Prior Yr", f"{my_growth:+.1f}pp", f"dept avg {dept_growth_mean:+.1f}pp",
               my_growth >= dept_growth_mean, accent=GREEN)
with k4:
    stat_card("Prediction Bias", f"{bias:+.1f}pp", "vs. Prediction 1 in dataset", abs(bias) < 3, accent=ORANGE)
with k5:
    stat_card("Prediction Fit (R²)", f"{r2:.2f}", "how well Prediction 1 tracks actual", r2 > 0.5, accent=TEAL)
with k6:
    at_risk_n = int(my_master["at_risk"].sum()) if len(my_master) else 0
    stat_card("At-Risk in Class", f"{at_risk_n}", f"of {len(my_master)} students", at_risk_n == 0, accent=RED)

st.markdown("<div style='height:4px'></div>", unsafe_allow_html=True)

# ---------------------------------------------------------------------------
# Row: trend (wide) + donut
# ---------------------------------------------------------------------------
col_wide, col_donut = st.columns([2, 1])

with col_wide:
    st.markdown('<div class="chart-panel">', unsafe_allow_html=True)
    panel_header("Class Trend", "Average score by term" + (f", split by subject" if subject_filter == "All Subjects" and len(my_subjects) > 1 else ""))
    if len(my_rows):
        if subject_filter == "All Subjects" and len(my_subjects) > 1:
            trend = my_rows.groupby(["subjectName", "term"])["sheetPercentage"].mean().reset_index()
            # force all three terms onto the axis even if a term has no data yet
            # (e.g. T3 assessments not recorded yet) -- shows a gap, not a cut-off axis
            full_idx = pd.MultiIndex.from_product([trend["subjectName"].unique(), TERMS],
                                                    names=["subjectName", "term"])
            trend = trend.set_index(["subjectName", "term"]).reindex(full_idx).reset_index()
            fig = px.line(trend, x="term", y="sheetPercentage", color="subjectName", markers=True,
                          category_orders={"term": TERMS}, color_discrete_sequence=CHART_COLORWAY)
        else:
            trend = my_rows.groupby("term")["sheetPercentage"].mean().reindex(TERMS).reset_index()
            fig = go.Figure(go.Scatter(x=trend["term"], y=trend["sheetPercentage"], mode="lines+markers",
                                        line=dict(color=PURPLE, width=3), marker=dict(size=9),
                                        fill="tozeroy", fillcolor="rgba(11,83,148,0.08)",
                                        name="Avg score", showlegend=False))
        fig = apply_light_theme(fig)
        fig.update_layout(height=260, yaxis_title="Avg %")
        st.plotly_chart(fig, use_container_width=True)
        st.caption("If a term is missing from the axis or shows a gap, that term's assessments haven't been recorded yet.")
    st.markdown('</div>', unsafe_allow_html=True)

with col_donut:
    st.markdown('<div class="chart-panel">', unsafe_allow_html=True)
    panel_header("Class Mastery Split")
    if len(my_master):
        band_counts = my_master["performance_band"].value_counts().reindex(["Low", "Medium", "High"]).fillna(0)
        fig = go.Figure(go.Pie(
            labels=["Needs Support", "On Track", "Excelling"], values=band_counts.values,
            hole=0.55, marker=dict(colors=[RED, ORANGE, GREEN]),
        ))
        fig = apply_light_theme(fig)
        fig.update_layout(height=260)
        st.plotly_chart(fig, use_container_width=True)
    st.markdown('</div>', unsafe_allow_html=True)

# ---------------------------------------------------------------------------
# Row: calibration scatter + spread
# ---------------------------------------------------------------------------
col_a, col_b = st.columns(2)

with col_a:
    st.markdown('<div class="chart-panel">', unsafe_allow_html=True)
    panel_header("Prediction 1 vs. Actual", "Per student -- 'Prediction 1' is the forecast already in the source data, not a model we generated")
    if len(my_rows):
        scatter_data = my_rows.groupby("UPN").agg(
            predicted=("predicted (%)", "mean"), actual=("sheetPercentage", "mean")
        ).reset_index()
        fig = px.scatter(scatter_data, x="predicted", y="actual", hover_data=["UPN"], trendline="ols",
                         color_discrete_sequence=[BLUE_MED])
        max_val = max(scatter_data["predicted"].max(), scatter_data["actual"].max()) + 5
        fig.add_shape(type="line", x0=0, y0=0, x1=max_val, y1=max_val, line=dict(dash="dot", color=BLUE_PALE))
        fig = apply_light_theme(fig)
        fig.update_layout(height=280, xaxis_title="Prediction 1 (%, from dataset)", yaxis_title="Actual %")
        st.plotly_chart(fig, use_container_width=True)
    st.markdown('</div>', unsafe_allow_html=True)

with col_b:
    st.markdown('<div class="chart-panel">', unsafe_allow_html=True)
    panel_header("Score Spread", f"min {class_stats['min']:.0f}% · max {class_stats['max']:.0f}% · IQR {class_stats['iqr']:.1f}pp")
    if len(current_by_student):
        fig = go.Figure(go.Box(y=current_by_student.values, boxpoints="all", marker_color=PURPLE,
                                fillcolor="rgba(11,83,148,0.12)", line_color=PURPLE, name="Your class"))
        fig = apply_light_theme(fig)
        fig.update_layout(height=280, yaxis_title="Current %", showlegend=False)
        fig.update_xaxes(showticklabels=False)
        st.plotly_chart(fig, use_container_width=True)
    st.markdown('</div>', unsafe_allow_html=True)

# ---------------------------------------------------------------------------
# Roster, ranked
# ---------------------------------------------------------------------------
st.markdown('<div class="chart-panel">', unsafe_allow_html=True)
panel_header("Class Roster", "Ranked by current score")
if len(my_master):
    roster = my_master[["UPN", "yearGroup", "regGroup", "current (%)", "predicted (%)", "Attendance (%)", "performance_band"]].copy()
    roster = roster.sort_values("current (%)", ascending=False).reset_index(drop=True)
    roster.insert(0, "Rank", range(1, len(roster) + 1))
    roster = roster.rename(columns={"performance_band": "Mastery Level", "yearGroup": "Grade", "regGroup": "Section"})
    st.dataframe(
        roster.style.background_gradient(subset=["current (%)"], cmap=HEATMAP_SCALE, vmin=40, vmax=100),
        use_container_width=True, hide_index=True,
    )
st.markdown('</div>', unsafe_allow_html=True)

# ---------------------------------------------------------------------------
# Department comparison
# ---------------------------------------------------------------------------
col_c, col_d = st.columns(2)
with col_c:
    st.markdown('<div class="chart-panel">', unsafe_allow_html=True)
    panel_header("Growth vs. Department", "Each dot is one teacher's growth (current − prior year); box = middle 50%, line = median")
    n_dept_teachers = len(all_teacher_growth)
    if n_dept_teachers >= 3:
        growth_series = pd.Series(all_teacher_growth)
        fig = go.Figure(go.Box(y=growth_series.values, boxpoints="all", marker_color=BLUE,
                                fillcolor="rgba(61,133,198,0.12)", line_color=BLUE, name="Department"))
        fig.add_trace(go.Scatter(x=[0], y=[my_growth], mode="markers+text", text=["You"],
                                  textposition="middle right", marker=dict(symbol="diamond", size=14, color=RED),
                                  showlegend=False))
        fig = apply_light_theme(fig)
        fig.update_layout(height=260, yaxis_title="Growth (pp)", showlegend=False)
        fig.update_xaxes(showticklabels=False)
        st.plotly_chart(fig, use_container_width=True)
        st.caption(
            f"Your growth is {my_growth:+.1f}pp; the department ({n_dept_teachers} teachers of the "
            f"same subject(s)) ranges from {growth_series.min():+.1f} to {growth_series.max():+.1f}pp, "
            f"median {growth_series.median():+.1f}pp. The red diamond marks you among them."
        )
    elif n_dept_teachers == 1:
        st.info(
            f"You're the only teacher of this subject in the data, so there's no one to compare "
            f"against yet. Your growth is **{my_growth:+.1f}pp**.",
            icon="ℹ️",
        )
    else:
        st.info(
            f"Only {n_dept_teachers} teachers share this subject in the data -- too few for a "
            f"meaningful range. Your growth is **{my_growth:+.1f}pp**.",
            icon="ℹ️",
        )
    st.markdown('</div>', unsafe_allow_html=True)

with col_d:
    st.markdown('<div class="chart-panel">', unsafe_allow_html=True)
    panel_header("Prediction Bias vs. Department", "Each dot is one teacher's bias vs. Prediction 1 (the dataset's own forecast field)")
    n_dept_bias = len(all_teacher_bias)
    if n_dept_bias >= 3:
        bias_series = pd.Series(all_teacher_bias)
        fig = go.Figure(go.Box(y=bias_series.values, boxpoints="all", marker_color=TEAL,
                                fillcolor="rgba(46,134,171,0.12)", line_color=TEAL, name="Department"))
        fig.add_trace(go.Scatter(x=[0], y=[bias], mode="markers+text", text=["You"],
                                  textposition="middle right", marker=dict(symbol="diamond", size=14, color=RED),
                                  showlegend=False))
        fig.add_hline(y=0, line_dash="dot", line_color=BLUE_PALE)
        fig = apply_light_theme(fig)
        fig.update_layout(height=260, yaxis_title="Bias (pp)", showlegend=False)
        fig.update_xaxes(showticklabels=False)
        st.plotly_chart(fig, use_container_width=True)
        st.caption(
            f"0 = your students land exactly where Prediction 1 said. Your bias is {bias:+.1f}pp "
            f"across {n_dept_bias} teachers; the dotted line at 0 is the 'perfectly calibrated' "
            f"reference. This never uses a model we built -- it's always the Prediction 1 value "
            f"already in the source file."
        )
    elif n_dept_bias == 1:
        st.info(
            f"You're the only teacher of this subject in the data, so there's no one to compare "
            f"against yet. Your bias vs. Prediction 1 is **{bias:+.1f}pp**.",
            icon="ℹ️",
        )
    else:
        st.info(
            f"Only {n_dept_bias} teachers share this subject in the data -- too few for a "
            f"meaningful range. Your bias vs. Prediction 1 is **{bias:+.1f}pp**.",
            icon="ℹ️",
        )
    st.markdown('</div>', unsafe_allow_html=True)


with st.expander("ℹ️ Why is department comparison a range, not a leaderboard?"):
    st.markdown(
        "Ranking teachers by raw scores rewards who they were assigned to teach, "
        "not how well they taught. Growth and calibration control for starting "
        "point, and the department view is shown as an anonymized range rather "
        "than naming colleagues individually."
    )
