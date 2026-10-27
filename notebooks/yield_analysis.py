# %% [markdown]
# # Semiconductor Wafer Yield & Process Control Analytics
#
# **Business question:** A fab line is running at about 93% yield. Every failed run means scrap, rework
# and lost tool time. **Which process signals predict failure, how much is poor quality costing us,
# and what should the process engineering team do first?**
#
# **Data:** [UCI SECOM](https://archive.ics.uci.edu/dataset/179/secom) gives 1,567 real production runs
# from a semiconductor fab (Jul to Oct 2008). Each run has 590 anonymised sensor readings and a
# pass/fail result from in-house line testing.
#
# **Approach**
# 1. Data quality audit and cleaning
# 2. Yield KPIs and trends (SQL / DuckDB)
# 3. Root cause screening: which sensors differ between pass and fail runs?
# 4. Statistical process control (SPC) on the top driver
# 5. Early-warning model to flag at-risk runs before final test
# 6. Cost of poor quality and business case
#
# > Cost figures use **stated, adjustable assumptions** (cell below). The dataset contains no financials.

# %%
import sys
from pathlib import Path

import duckdb
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
from scipy import stats
from sklearn.ensemble import RandomForestClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import average_precision_score, roc_auc_score
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler

ROOT = Path.cwd().parent if Path.cwd().name == "notebooks" else Path.cwd()
sys.path.insert(0, str(ROOT / "src"))
import style  # noqa: E402

style.apply()
FIG = ROOT / "reports/figures"
FIG.mkdir(parents=True, exist_ok=True)
pd.set_option("display.width", 140)

# ---- Business assumptions (illustrative, change to your fab's numbers) ----
COST_PER_FAILED_RUN_EUR = 2_500      # scrap + rework + re-test + lost tool time per failed run
INSPECTION_COST_EUR = 150            # extra metrology/inspection on a flagged run
SAVING_IF_CAUGHT_EARLY = 0.60        # share of failure cost avoided when caught before final test
RUNS_PER_YEAR = 17.4 * 365           # observed throughput (see SQL KPI query) annualised

# %% [markdown]
# ## 1. Data quality audit
# Real sensor data is messy. Before any analysis, I audited every one of the 590 sensors.

# %%
wafers = pd.read_csv(ROOT / "data/processed/wafers.csv", parse_dates=["timestamp"])
X = pd.read_csv(ROOT / "data/processed/sensors_clean.csv").set_index("run_id")
audit = pd.read_csv(ROOT / "reports/data_quality_report.csv")

summary = (audit.assign(decision=audit["drop_reason"].fillna("kept").replace("", "kept"))
                .groupby("decision").size().rename("sensors").to_frame())
print(f"Overall missing values in raw data: {audit['missing_pct'].mean():.1f}%")
summary

# %% [markdown]
# **Takeaway:** 321 of 590 sensors (54%) carried no usable information. 116 were constant, 32 were
# mostly empty and 173 duplicated another sensor. Cutting them makes the analysis faster and the
# findings easier to explain to engineers. Remaining gaps were filled with each sensor's median.

# %% [markdown]
# ## 2. Yield KPIs and trends (SQL)
# All KPI queries live in [`/sql`](../sql) and run on DuckDB, the same SQL you would write against a
# manufacturing execution system (MES) database.

# %%
con = duckdb.connect()
con.execute(f"CREATE VIEW wafers AS SELECT * FROM read_csv_auto('{ROOT / 'data/processed/wafers.csv'}')")
run_sql = lambda name: con.sql((ROOT / "sql" / name).read_text()).df()

run_sql("01_yield_kpis.sql")

# %%
weekly = run_sql("02_weekly_yield.sql")
weekly["week_start"] = pd.to_datetime(weekly["week_start"])

fig, ax = plt.subplots(figsize=(9, 3.8))
ax.plot(weekly.week_start, weekly.yield_pct, color=style.MUTED, lw=1.2, marker="o", ms=4, label="Weekly yield")
ax.plot(weekly.week_start, weekly.rolling_4wk_yield_pct, color=style.BLUE, lw=2.2, label="4-week rolling yield")
ax.axhline(95, color=style.INK_2, lw=0.8, ls="--")
ax.text(weekly.week_start.iloc[0], 95.4, "95% target", color=style.INK_2, fontsize=9)
ax.set_title("Yield improved from ~85% to ~95% over the quarter")
ax.set_ylabel("Yield (%)")
ax.legend(loc="lower right")
style.save(fig, FIG / "01_weekly_yield.png")
display_cols = ["week_start", "runs", "fails", "yield_pct", "rolling_4wk_yield_pct"]
weekly[display_cols].tail(6)

# %%
shift = run_sql("03_yield_by_shift.sql")
chi2, p_shift, *_ = stats.chi2_contingency(pd.crosstab(wafers["shift"], wafers["is_fail"]))
print(f"Chi-square test, shift vs failure: p = {p_shift:.2f}")
shift

# %% [markdown]
# **Takeaway:** Failure rates are almost identical across shifts (p ≈ 0.9). Failures are **not** driven
# by people or shift handovers, which points the investigation at **equipment and process
# parameters**, so the next step looks at the sensors.

# %%
clusters = run_sql("04_failure_clusters.sql")
mtbf = run_sql("05_time_between_failures.sql")
print(f"Failure clusters (2+ consecutive failed runs): {len(clusters)}")
mtbf

# %% [markdown]
# ## 3. Root cause screening: which sensors separate pass from fail?
# For each of the 269 remaining sensors I ran a **Mann-Whitney U test** (no normality assumption,
# robust to outliers) comparing pass and fail runs. I measured effect size with the **rank-biserial
# correlation** and controlled for testing 269 sensors with the **Benjamini-Hochberg** false discovery rate.

# %%
y = wafers.set_index("run_id")["is_fail"].loc[X.index]
rows = []
for col in X.columns:
    fail_vals, pass_vals = X.loc[y == 1, col], X.loc[y == 0, col]
    u, p = stats.mannwhitneyu(fail_vals, pass_vals, alternative="two-sided")
    rows.append({"sensor": col, "p_value": p,
                 "effect_size": 2 * u / (len(fail_vals) * len(pass_vals)) - 1,
                 "fail_median": fail_vals.median(), "pass_median": pass_vals.median()})
screen = pd.DataFrame(rows)
screen["q_value"] = stats.false_discovery_control(screen["p_value"])
screen["abs_effect"] = screen["effect_size"].abs()
screen = screen.sort_values("abs_effect", ascending=False).reset_index(drop=True)
significant = screen[screen.q_value < 0.05]
print(f"Sensors significantly different between pass and fail (FDR < 5%): {len(significant)}")
screen.head(10).round(4)

# %%
top = screen.head(15).iloc[::-1]
fig, ax = plt.subplots(figsize=(8, 5))
colors = [style.BLUE if q < 0.05 else style.AXIS for q in top.q_value]
ax.barh(top.sensor, top.abs_effect, color=colors, height=0.6)
for yv, (e, q) in enumerate(zip(top.abs_effect, top.q_value)):
    ax.text(e + 0.004, yv, f"{e:.2f}", va="center", fontsize=8.5, color=style.INK_2)
ax.set_title("Top 15 sensors by effect on pass/fail")
ax.set_xlabel("Effect size |rank-biserial r|  (blue = significant after FDR correction)")
ax.grid(axis="x"); ax.grid(axis="y", visible=False)
style.save(fig, FIG / "02_sensor_pareto.png")
screen.to_csv(ROOT / "reports/sensor_screening_results.csv", index=False)

# %% [markdown]
# **Takeaway:** Out of 269 sensors, only a short list differs meaningfully between pass and fail runs.
# This is the **Pareto principle** applied to process control: engineers can start their investigation
# with a handful of signals instead of 590.

# %% [markdown]
# ## 4. Statistical process control on the top driver
# An **Individuals (I) control chart** is the standard tool fab engineers use. Control limits are mean ± 3σ,
# with σ estimated from the average moving range (MR̄ / 1.128). Limits come from the **stable period**
# (runs 600 onward), so the chart shows how far earlier production was from a well-controlled process.

# %%
lead = screen.sensor.iloc[0]
series = X[lead].reset_index(drop=True)
fails = y.reset_index(drop=True).astype(bool)
times = wafers["timestamp"]
STEP = 500                                  # visible step change in the sensor (late August)
base = series.iloc[600:]
sigma = base.diff().abs().mean() / 1.128
center = base.mean()
ucl, lcl = center + 3 * sigma, center - 3 * sigma
ooc = (series > ucl) | (series < lcl)

fig, ax = plt.subplots(figsize=(10, 4))
ax.plot(series.index, series.clip(-30, 60), color=style.BLUE, lw=0.8)
ax.scatter(series.index[fails], series[fails].clip(-30, 60), color=style.CRITICAL, s=14, zorder=3,
           label="Failed run", edgecolor=style.SURFACE, linewidth=0.8)
for level, name in [(ucl, "UCL"), (center, "Center"), (lcl, "LCL")]:
    ax.axhline(level, color=style.INK_2, lw=0.8, ls="--" if name != "Center" else "-")
    ax.text(len(series) + 8, level, name, va="center", fontsize=8.5, color=style.INK_2)
ax.axvline(STEP, color=style.ORANGE, lw=1.5)
ax.text(STEP + 10, 56, f"step change ~{times.iloc[STEP]:%d %b}", color=style.INK, fontsize=9, va="top")
ax.set_ylim(-32, 62)
ax.set_title(f"I-chart for sensor {lead}: unstable before late August, in control after")
ax.set_xlabel("Production run (time order)"); ax.set_ylabel("Sensor reading (clipped to ±60)")
ax.legend(loc="upper right")
style.save(fig, FIG / "03_spc_chart.png")

regime = pd.DataFrame({
    "period": np.where(series.index < STEP, f"Before {times.iloc[STEP]:%d %b}", f"From {times.iloc[STEP]:%d %b}"),
    "value": series, "fail": fails, "out_of_control": ooc})
by_period = regime.groupby("period", sort=False).agg(
    runs=("fail", "size"), sensor_mean=("value", "mean"), sensor_std=("value", "std"),
    out_of_control_pct=("out_of_control", "mean"), fail_rate_pct=("fail", "mean"))
by_period[["out_of_control_pct", "fail_rate_pct"]] *= 100
by_ooc = regime.groupby("out_of_control")["fail"].mean() * 100
print(f"Fail rate when {lead} is out of control: {by_ooc[True]:.1f}%  vs in control: {by_ooc[False]:.1f}%"
      f"  -> {by_ooc[True] / by_ooc[False]:.1f}x")
by_period.round(2)

# %% [markdown]
# **Takeaway:** sensor S059 ran **high and unstable until late August**, with almost half of runs outside the
# control limits. When it stabilised, the failure rate fell from about 12% to about 4%. Runs outside the control
# limits fail **3.6x more often** than runs inside them. This matches the yield recovery in the weekly
# trend and makes S059 the first parameter to lock down with real-time SPC alarms.
#
# The **process window** view below shows the same effect across the sensor's operating range.

# %%
decile = pd.qcut(X[lead].rank(method="first"), 10, labels=range(1, 11))
window = (pd.DataFrame({"decile": decile.values, "fail": y.values})
            .groupby("decile", observed=True)["fail"].agg(runs="count", fail_rate="mean"))
window["fail_rate"] *= 100
high = decile.astype(int).values >= 9
risk_high, risk_rest = y[high].mean(), y[~high].mean()

fig, ax = plt.subplots(figsize=(8, 3.8))
bars = ax.bar(window.index.astype(str), window.fail_rate, width=0.65,
              color=[style.CRITICAL if d >= 9 else style.BLUE for d in window.index.astype(int)])
ax.axhline(y.mean() * 100, color=style.INK_2, lw=0.8, ls="--")
ax.text(9.6, y.mean() * 100 + 0.4, f"plant average {y.mean():.1%}", fontsize=8.5, color=style.INK_2, ha="right")
for b, v in zip(bars, window.fail_rate):
    ax.text(b.get_x() + b.get_width() / 2, v + 0.3, f"{v:.1f}%", ha="center", fontsize=8.5, color=style.INK_2)
ax.set_title(f"Process window: failure rate by {lead} reading (decile 1 = lowest)")
ax.set_xlabel(f"{lead} decile"); ax.set_ylabel("Failure rate (%)")
style.save(fig, FIG / "05_process_window.png")
print(f"Top-20% {lead} readings: fail rate {risk_high:.1%} vs {risk_rest:.1%} elsewhere "
      f"-> {risk_high / risk_rest:.1f}x the risk")
window.round(1)

# %% [markdown]
# **Takeaway:** when the top driver reads in its **upper 20%**, runs fail about **4x more often**.
# That gives engineers a concrete action: set an upper specification limit for this parameter and alarm on it.

# %% [markdown]
# ## 5. Early-warning model: flag at-risk runs before final test
# Can sensor data identify likely failures early enough to intervene?
#
# * **5-fold stratified cross-validation** keeps roughly 21 failures in every test fold.
# * Sensor screening is redone **inside each fold on training data only**. Selecting features on the full
#   data first is a common leakage mistake that inflates results.
# * Two models: an interpretable **logistic regression** and a **random forest**, both weighted for the
#   heavy class imbalance (6.6% failures).
# * Every run gets an **out-of-fold** risk score, a prediction from a model that never saw that run.

# %%
from sklearn.model_selection import StratifiedKFold

N_FEATURES = 40

def screen_features(X_train, y_train, n=N_FEATURES):
    p = {c: stats.mannwhitneyu(X_train.loc[y_train == 1, c], X_train.loc[y_train == 0, c]).pvalue
         for c in X_train.columns}
    return sorted(p, key=p.get)[:n]

model_factories = {
    "Logistic regression": lambda: make_pipeline(StandardScaler(), LogisticRegression(
        C=0.05, class_weight="balanced", max_iter=3000)),
    "Random forest": lambda: RandomForestClassifier(
        n_estimators=500, min_samples_leaf=3, class_weight="balanced_subsample", random_state=42, n_jobs=-1),
}
cv = StratifiedKFold(n_splits=5, shuffle=True, random_state=1)
oof = {name: np.zeros(len(X)) for name in model_factories}
fold_rows = []
for fold, (tr, te) in enumerate(cv.split(X, y), 1):
    feats = screen_features(X.iloc[tr], y.iloc[tr])
    for name, make in model_factories.items():
        m = make().fit(X.iloc[tr][feats], y.iloc[tr])
        oof[name][te] = m.predict_proba(X.iloc[te][feats])[:, 1]
        fold_rows.append({"model": name, "fold": fold,
                          "ROC AUC": roc_auc_score(y.iloc[te], oof[name][te]),
                          "PR AUC": average_precision_score(y.iloc[te], oof[name][te])})
cv_results = (pd.DataFrame(fold_rows).groupby("model")[["ROC AUC", "PR AUC"]].agg(["mean", "std"]).round(3))
cv_results["random-flagging PR AUC"] = round(y.mean(), 3)
cv_results

# %% [markdown]
# With rare failures, **PR AUC** is the honest metric. Random flagging scores 0.066, so the random forest is
# **several times better than chance**: useful for prioritising inspection, not a perfect classifier.
# The next cell turns scores into a decision: *if we inspect the top X% riskiest runs, what share of
# failures do we catch, and does it pay?*

# %%
best = cv_results[("PR AUC", "mean")].idxmax()
s = oof[best]
order = np.argsort(-s)
y_sorted = y.values[order]
k = np.arange(1, len(s) + 1)
pct_inspected = k / len(s)
pct_caught = np.cumsum(y_sorted) / y_sorted.sum()
annualise = RUNS_PER_YEAR / len(s)
savings = (np.cumsum(y_sorted) * COST_PER_FAILED_RUN_EUR * SAVING_IF_CAUGHT_EARLY
           - k * INSPECTION_COST_EUR) * annualise
best_k = int(np.argmax(savings))

fig, axes = plt.subplots(1, 2, figsize=(11, 4))
ax = axes[0]
ax.plot(pct_inspected * 100, pct_caught * 100, color=style.BLUE, label=best)
ax.plot([0, 100], [0, 100], color=style.MUTED, lw=1, ls="--", label="Random inspection")
ax.scatter([pct_inspected[best_k] * 100], [pct_caught[best_k] * 100], color=style.ORANGE, s=60, zorder=3,
           edgecolor=style.SURFACE, linewidth=2)
ax.annotate(f"Inspect {pct_inspected[best_k]:.0%} of runs\n-> catch {pct_caught[best_k]:.0%} of failures",
            (pct_inspected[best_k] * 100, pct_caught[best_k] * 100), xytext=(14, -30),
            textcoords="offset points", fontsize=9, color=style.INK)
ax.set_title("Failure capture curve (out-of-fold)")
ax.set_xlabel("% of runs inspected (highest risk first)"); ax.set_ylabel("% of failures caught")
ax.legend(loc="lower right")
ax = axes[1]
ax.plot(pct_inspected * 100, savings / 1000, color=style.AQUA)
ax.axhline(0, color=style.AXIS, lw=0.8)
ax.scatter([pct_inspected[best_k] * 100], [savings[best_k] / 1000], color=style.ORANGE, s=60, zorder=3,
           edgecolor=style.SURFACE, linewidth=2)
ax.annotate(f"€{savings[best_k] / 1000:,.0f}k / year", (pct_inspected[best_k] * 100, savings[best_k] / 1000),
            xytext=(10, 6), textcoords="offset points", fontsize=9, color=style.INK)
ax.set_title("Net annual saving vs inspection depth")
ax.set_xlabel("% of runs inspected"); ax.set_ylabel("Net saving (€ thousands / year)")
fig.tight_layout()
style.save(fig, FIG / "04_capture_and_savings.png")

# %%
fail_rate = y.mean()
copq = RUNS_PER_YEAR * fail_rate * COST_PER_FAILED_RUN_EUR
business_case = pd.Series({
    "Annual runs (observed rate)": f"{RUNS_PER_YEAR:,.0f}",
    "Fail rate": f"{fail_rate:.2%}",
    "Annual cost of poor quality": f"€{copq:,.0f}",
    "Model used": best,
    "Inspect top-risk share of runs": f"{pct_inspected[best_k]:.0%}",
    "Failures caught early": f"{pct_caught[best_k]:.0%}",
    "Net annual saving (risk-based inspection)": f"€{savings[best_k]:,.0f}",
    "Saving per +1pp yield (process fix)": f"€{RUNS_PER_YEAR * 0.01 * COST_PER_FAILED_RUN_EUR:,.0f}",
}, name="value")
business_case.to_csv(ROOT / "reports/business_case.csv")
business_case.to_frame()

# %% [markdown]
# ### Reality check: does the model hold up on *future* data?
# Cross-validation mixes time periods. Before recommending deployment I ran a stricter test: **train on
# the first 70% of runs (Jul to Sep) and predict the last 30% (Sep to Oct)**.

# %%
cut = int(len(X) * 0.70)
feats = screen_features(X.iloc[:cut], y.iloc[:cut])
fwd = {}
for name, make in model_factories.items():
    m = make().fit(X.iloc[:cut][feats], y.iloc[:cut])
    p = m.predict_proba(X.iloc[cut:][feats])[:, 1]
    fwd[name] = {"ROC AUC": roc_auc_score(y.iloc[cut:], p), "PR AUC": average_precision_score(y.iloc[cut:], p)}
forward = pd.DataFrame(fwd).T.round(3)
forward["random-flagging PR AUC"] = round(y.iloc[cut:].mean(), 3)

# Drift check: how far did the key sensors move between the two periods?
drift = pd.DataFrame({
    s_: {"train median": X[s_].iloc[:cut].median(), "test median": X[s_].iloc[cut:].median(),
         "KS-test p": stats.ks_2samp(X[s_].iloc[:cut], X[s_].iloc[cut:]).pvalue}
    for s_ in screen.sensor.head(5)}).T
print(forward.to_string(), "\n")
drift.round(4)

# %% [markdown]
# **Takeaway:** on future data the model is barely better than random, and the key sensors' distributions
# **shifted significantly** between periods (KS tests). The process changed as yield improved, so relationships
# learned in July no longer hold in October. This is **concept drift**, and it changes the recommendation:
# the model should be **retrained on a rolling window and monitored**, not deployed once and forgotten.
# The process-window finding in Section 4 is the more robust action today.

# %% [markdown]
# ### Which signals does the model rely on?

# %%
rf = model_factories["Random forest"]().fit(X[screen_features(X, y)], y)
imp = pd.Series(rf.feature_importances_, index=screen_features(X, y)).sort_values(ascending=False).head(10)
overlap = sorted(set(imp.index) & set(screen.sensor.head(15)))
print("Top model features also in top-15 statistical screen:", overlap)
imp.round(4).to_frame("importance")

# %% [markdown]
# ## 6. Recommendations for the process engineering team
#
# 1. **Lock down sensor S059 with live SPC alarms.** Its instability before late August lines up with the
#    worst yield. Out-of-control runs fail 3.6x more often, and readings in its top 20% fail 4x more often.
#    Set an upper spec limit and work through the rest of the short list the same way.
# 2. **Rule out people and focus on equipment.** Shift has no effect on yield (p ≈ 0.9), while failures
#    cluster in time, which is typical of tool drift or a process excursion.
# 3. **Pilot risk-based inspection with retraining built in.** Score each run and send the highest-risk runs
#    to extra metrology. Because the process drifts, retrain the model on a rolling window (e.g. monthly) and
#    track its PR AUC as a KPI, retiring it if performance falls to random.
# 4. **Fix the data pipeline.** 54% of sensors are constant, empty or duplicated. Removing them from
#    the MES export cuts storage and noise for every future analysis.
# 5. **Track the KPIs weekly:** yield %, 4-week rolling yield, MTBF and SPC alarm rate (see the dashboard).
#
# **Limitations:** sensor names are anonymised, so findings point engineers to *where* to look rather than
# a physical mechanism. Only 104 failures exist, so model metrics carry wide uncertainty. Cost inputs are
# assumptions and should be replaced with the fab's own figures.
