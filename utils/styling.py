"""One consistent pastel sky-blue theme, shared by all four dashboard pages.
Every color anywhere in the app -- backgrounds, text, charts, status
indicators -- comes from this palette. Status/severity is encoded by
shade (darker = more attention needed) rather than by hue, so nothing
outside the blue family ever appears, and nothing is pure black.

Actual light/dark base theming (so Streamlit's own native text and widget
colors don't inherit the user's OS dark mode) lives in
.streamlit/config.toml -- this file only styles the custom card/chart
layer on top of that.
"""

import plotly.graph_objects as go
import streamlit as st

# --- Core palette: shades of blue only, from pale to deep -----------------
PAGE_BG = "#EAF4FC"        # page background -- very light sky blue
CARD_BG = "#F7FBFF"        # card background -- near-white, faint blue tint
TEXT_DARK = "#173A5E"      # main text -- deep navy, never pure black
TEXT_MUTED = "#5B7FA6"     # secondary text / captions

BLUE_DEEP = "#0B5394"      # strongest accent -- primary series, "you" markers
BLUE_STRONG = "#2E86AB"    # secondary series
BLUE_MED = "#3D85C6"       # tertiary series / primary buttons
BLUE_SOFT = "#6FA8DC"      # fourth series
BLUE_PALE = "#9FC5E8"      # comparison / "predicted" series
BLUE_FAINT = "#CFE2F3"     # fills, faint bars

# Semantic aliases kept so chart code reads naturally; all map into the
# blue family only, differentiated by shade rather than hue.
GOOD = BLUE_DEEP           # "good" / positive -- deepest, most saturated blue
NEUTRAL = BLUE_MED         # neutral / on-track
CAUTION = BLUE_SOFT        # needs attention -- lighter, softer blue
CONCERN = BLUE_PALE        # highest concern -- palest, "faded out" blue

# Back-compat names used across pages (all now blue-family only)
PURPLE = BLUE_DEEP
BLUE = BLUE_MED
GREEN = GOOD
RED = CONCERN
ORANGE = CAUTION
TEAL = BLUE_STRONG

CHART_COLORWAY = [BLUE_DEEP, BLUE_STRONG, BLUE_MED, BLUE_SOFT, BLUE_PALE, BLUE_FAINT]
HEATMAP_SCALE = "Blues"

CARD_CSS = f"""
<style>
div[data-testid="stAppViewContainer"] {{
    background-color: {PAGE_BG};
}}
section[data-testid="stSidebar"] {{
    background-color: {CARD_BG};
}}
.stat-card {{
    background: {CARD_BG};
    border-radius: 12px;
    padding: 14px 16px;
    box-shadow: 0 1px 4px rgba(23, 58, 94, 0.10);
    border-left: 4px solid var(--accent, {BLUE_DEEP});
    margin-bottom: 10px;
    min-height: 92px;
}}
.stat-label {{
    font-size: 0.72rem;
    text-transform: uppercase;
    letter-spacing: 0.03em;
    color: {TEXT_MUTED};
    font-weight: 600;
    margin-bottom: 4px;
}}
.stat-value {{
    font-size: 1.55rem;
    font-weight: 700;
    color: {TEXT_DARK};
    line-height: 1.1;
}}
.stat-delta-pos {{ color: {BLUE_DEEP}; font-size: 0.78rem; font-weight: 700; }}
.stat-delta-neg {{ color: {TEXT_MUTED}; font-size: 0.78rem; font-weight: 700; }}
.stat-delta-neutral {{ color: {TEXT_MUTED}; font-size: 0.78rem; font-weight: 600; }}
.panel-title {{
    font-size: 0.95rem;
    font-weight: 700;
    color: {TEXT_DARK};
    margin-bottom: 2px;
}}
.panel-sub {{
    font-size: 0.78rem;
    color: {TEXT_MUTED};
    margin-bottom: 10px;
}}
.chart-panel {{
    background: {CARD_BG};
    border-radius: 12px;
    padding: 14px 16px 4px 16px;
    box-shadow: 0 1px 4px rgba(23, 58, 94, 0.10);
    margin-bottom: 14px;
}}
.page-title {{
    color: {TEXT_DARK};
    margin-bottom: 0;
}}
.page-subtitle {{
    color: {TEXT_MUTED};
    font-size: 0.85rem;
    margin-bottom: 14px;
}}
.plain-callout {{
    background: {CARD_BG};
    border-radius: 12px;
    padding: 14px 18px;
    border-left: 4px solid {BLUE_DEEP};
    color: {TEXT_DARK};
    margin-bottom: 10px;
}}
</style>
"""


def inject_css():
    st.markdown(CARD_CSS, unsafe_allow_html=True)


def page_header(title: str, subtitle: str = ""):
    st.markdown(f'<h2 class="page-title">{title}</h2>', unsafe_allow_html=True)
    if subtitle:
        st.markdown(f'<div class="page-subtitle">{subtitle}</div>', unsafe_allow_html=True)


def stat_card(label: str, value: str, delta: str | None = None, delta_good: bool | None = None,
              accent: str = BLUE_DEEP):
    delta_html = ""
    if delta is not None:
        cls = (
            "stat-delta-neutral" if delta_good is None
            else ("stat-delta-pos" if delta_good else "stat-delta-neg")
        )
        arrow = "" if delta_good is None else ("▲ " if delta_good else "▽ ")
        delta_html = f'<div class="{cls}">{arrow}{delta}</div>'
    st.markdown(
        f"""
        <div class="stat-card" style="--accent:{accent}">
            <div class="stat-label">{label}</div>
            <div class="stat-value">{value}</div>
            {delta_html}
        </div>
        """,
        unsafe_allow_html=True,
    )


def stat_card_grid(items: list[dict], cols_per_row: int = 4):
    """Renders a list of stat cards wrapped into rows of `cols_per_row`,
    instead of cramming an arbitrary number of subjects into one row of
    columns (which overlaps/clips once there are more than ~5-6 items).
    Each item: {"label", "value", "delta"?, "delta_good"?, "accent"?}."""
    for i in range(0, len(items), cols_per_row):
        batch = items[i:i + cols_per_row]
        cols = st.columns(len(batch))
        for col, item in zip(cols, batch):
            with col:
                stat_card(
                    item["label"], item["value"],
                    item.get("delta"), item.get("delta_good"),
                    item.get("accent", BLUE_MED),
                )


def panel_header(title: str, subtitle: str | None = None):
    st.markdown(f'<div class="panel-title">{title}</div>', unsafe_allow_html=True)
    if subtitle:
        st.markdown(f'<div class="panel-sub">{subtitle}</div>', unsafe_allow_html=True)


def callout(text: str):
    st.markdown(f'<div class="plain-callout">{text}</div>', unsafe_allow_html=True)


def apply_light_theme(fig):
    fig.update_layout(
        template="plotly_white",
        colorway=CHART_COLORWAY,
        font=dict(color=TEXT_DARK, size=12),
        paper_bgcolor=CARD_BG,
        plot_bgcolor=CARD_BG,
        margin=dict(l=10, r=10, t=30, b=10),
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="left", x=0),
    )
    return fig


def gauge_chart(value: float, title: str, max_value: float = 100,
                 good_threshold: float = 75, warn_threshold: float = 50):
    """Severity encoded by shade of blue, not hue -- deepest blue = best."""
    color = BLUE_DEEP if value >= good_threshold else BLUE_MED if value >= warn_threshold else BLUE_PALE
    fig = go.Figure(
        go.Indicator(
            mode="gauge+number",
            value=value,
            title={"text": title, "font": {"size": 13, "color": TEXT_MUTED}},
            number={"suffix": "%", "font": {"size": 26, "color": TEXT_DARK}},
            gauge={
                "axis": {"range": [0, max_value], "tickcolor": BLUE_FAINT},
                "bar": {"color": color, "thickness": 0.25},
                "bgcolor": PAGE_BG,
                "borderwidth": 0,
                "steps": [
                    {"range": [0, warn_threshold], "color": BLUE_FAINT},
                    {"range": [warn_threshold, good_threshold], "color": BLUE_PALE},
                    {"range": [good_threshold, max_value], "color": BLUE_SOFT},
                ],
            },
        )
    )
    fig.update_layout(
        height=180, margin=dict(l=20, r=20, t=40, b=10),
        paper_bgcolor=CARD_BG, font=dict(color=TEXT_DARK),
    )
    return fig
