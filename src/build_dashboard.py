"""Build the interactive yield dashboard (docs/index.html, served by GitHub Pages)."""
from pathlib import Path

import duckdb
import numpy as np
import pandas as pd
import plotly.graph_objects as go

from dashboard_kit import AQUA, BLUE, CRITICAL, INK_2, MUTED, ORANGE, build_page

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data/processed"

wafers = pd.read_csv(DATA / "wafers.csv", parse_dates=["timestamp"])
X = pd.read_csv(DATA / "sensors_clean.csv").set_index("run_id")
screen = pd.read_csv(ROOT / "reports/sensor_screening_results.csv")
case = pd.read_csv(ROOT / "reports/business_case.csv", index_col=0).iloc[:, 0]

con = duckdb.connect()
con.execute(f"CREATE VIEW wafers AS SELECT * FROM read_csv_auto('{DATA / 'wafers.csv'}')")
sql = lambda f: con.sql((ROOT / "sql" / f).read_text()).df()
kpi = sql("01_yield_kpis.sql").iloc[0]
weekly = sql("02_weekly_yield.sql")
shift = sql("03_yield_by_shift.sql")

# Weekly yield
f1 = go.Figure()
f1.add_scatter(x=weekly.week_start, y=weekly.yield_pct, name="Weekly yield", mode="lines+markers",
               line=dict(color=MUTED, width=1.5), marker=dict(size=8),
               customdata=weekly[["runs", "fails"]], hovertemplate="Week of %{x|%d %b}<br>Yield %{y:.1f}%"
               "<br>%{customdata[0]} runs, %{customdata[1]} fails<extra></extra>")
f1.add_scatter(x=weekly.week_start, y=weekly.rolling_4wk_yield_pct, name="4-week rolling", mode="lines",
               line=dict(color=BLUE, width=2.5), hovertemplate="4-wk rolling %{y:.1f}%<extra></extra>")
f1.add_hline(y=95, line=dict(color=INK_2, width=1, dash="dash"), annotation_text="95% target",
             annotation_position="top left")
f1.update_layout(hovermode="x unified", yaxis_title="Yield (%)")

# Sensor pareto
top = screen.head(12).iloc[::-1]
f2 = go.Figure(go.Bar(x=top.abs_effect, y=top.sensor, orientation="h", marker_color=BLUE,
                      customdata=np.c_[top.q_value, top.fail_median, top.pass_median],
                      hovertemplate="%{y}<br>Effect size %{x:.3f}<br>FDR q = %{customdata[0]:.4f}"
                      "<br>Median fail %{customdata[1]:.2f} vs pass %{customdata[2]:.2f}<extra></extra>"))
f2.update_layout(xaxis_title="Effect size |rank-biserial r|", bargap=0.35)

# I-chart on lead sensor
lead = screen.sensor.iloc[0]
s = X[lead].reset_index(drop=True)
base = s.iloc[600:]
sigma, center = base.diff().abs().mean() / 1.128, base.mean()
fails = wafers.is_fail.astype(bool)
f3 = go.Figure()
f3.add_scatter(x=wafers.timestamp, y=s.clip(-30, 60), mode="lines", name=lead, line=dict(color=BLUE, width=1),
               hovertemplate="%{x|%d %b %H:%M}<br>Reading %{y:.2f}<extra></extra>")
f3.add_scatter(x=wafers.timestamp[fails], y=s[fails].clip(-30, 60), mode="markers", name="Failed run",
               marker=dict(color=CRITICAL, size=7, line=dict(color="white", width=1)),
               hovertemplate="FAILED run<br>%{x|%d %b %H:%M}<br>Reading %{y:.2f}<extra></extra>")
for lvl, name in [(center + 3 * sigma, "UCL"), (center, "Center"), (center - 3 * sigma, "LCL")]:
    f3.add_hline(y=lvl, line=dict(color=INK_2, width=1, dash="solid" if name == "Center" else "dash"),
                 annotation_text=name, annotation_position="top right")
f3.add_vline(x=wafers.timestamp.iloc[500], line=dict(color=ORANGE, width=2))
f3.update_layout(yaxis_title="Sensor reading (clipped)")

# Process window
dec = pd.qcut(X[lead].rank(method="first"), 10, labels=range(1, 11)).astype(int).values
win = pd.DataFrame({"d": dec, "f": wafers.is_fail.values}).groupby("d")["f"].agg(["mean", "count"])
f4 = go.Figure(go.Bar(x=win.index, y=win["mean"] * 100, marker_color=[CRITICAL if d >= 9 else BLUE for d in win.index],
                      customdata=win["count"], hovertemplate="Decile %{x}<br>Fail rate %{y:.1f}%"
                      "<br>%{customdata} runs<extra></extra>"))
f4.add_hline(y=wafers.is_fail.mean() * 100, line=dict(color=INK_2, width=1, dash="dash"),
             annotation_text="plant average", annotation_position="top left")
f4.update_layout(xaxis=dict(title=f"{lead} decile (1 = lowest reading)", dtick=1), yaxis_title="Fail rate (%)", bargap=0.3)

# Shift
f5 = go.Figure(go.Bar(x=shift["shift"], y=shift.fail_rate_pct, marker_color=AQUA, width=0.5,
                      customdata=shift[["runs", "fails"]],
                      hovertemplate="%{x}<br>Fail rate %{y:.2f}%<br>%{customdata[0]} runs, %{customdata[1]} fails<extra></extra>"))
f5.update_layout(yaxis_title="Fail rate (%)")

build_page(
    title="Semiconductor Yield & Process Control Dashboard",
    intro="1,567 real production runs from a semiconductor fab (UCI SECOM, Jul to Oct 2008), each with 590 sensor "
          "readings. Hover over any chart for details.",
    kpis=[("Overall yield", f"{kpi.yield_pct:.1f}%", f"{int(kpi.failed_runs)} failed of {int(kpi.total_runs):,} runs"),
          ("Latest 4-week yield", f"{weekly.rolling_4wk_yield_pct.iloc[-1]:.1f}%", "up from 76.9% at start"),
          ("Sensors that matter", "16 of 590", "significant after FDR correction"),
          ("Cost of poor quality", case["Annual cost of poor quality"], "per year (assumed €2.5k per fail)"),
          ("Risk-based inspection", case["Net annual saving (risk-based inspection)"], "net saving per year (model)")],
    cards=[
        {"title": "Weekly yield trend", "sub": "Yield recovered from ~85% to ~95% after late August.", "fig": f1, "wide": True},
        {"title": f"I-chart for {lead}, the top failure driver",
         "sub": "Unstable until the step change on 28 Aug (orange). Out-of-control runs fail 3.6x more often.",
         "fig": f3, "wide": True, "height": 380},
        {"title": "Top sensors separating pass from fail", "sub": "Mann-Whitney U effect size, ranked.", "fig": f2, "height": 400},
        {"title": f"Process window for {lead}", "sub": "Top-20% readings fail 4x more often (red).", "fig": f4, "height": 400},
        {"title": "Failure rate by shift", "sub": "No shift effect (chi-square p = 0.88), so the cause is equipment, not people.", "fig": f5,
         "wide": True, "height": 260},
    ],
    insights=[
        f"<b>Sensor {lead} is the main lever.</b> It ran unstable until 28 Aug, and the fail rate dropped from 11.8% to 4.2% once it stabilised.",
        "<b>Shift has no effect on yield.</b> The cause is equipment and process parameters, not operators.",
        "<b>54% of sensors were noise</b> (constant, empty or duplicated). 16 sensors carry the signal.",
        "<b>The early-warning model</b> catches 43% of failures by inspecting 16% of runs. It needs rolling retraining because of process drift.",
    ],
    footer="Data: UCI Machine Learning Repository, SECOM dataset (McCann &amp; Johnston, 2008). "
           "Cost figures use stated assumptions. See the notebook for the full method.",
    path=ROOT / "docs/index.html",
)
print("Dashboard written to docs/index.html")
