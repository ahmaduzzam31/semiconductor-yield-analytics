"""Load the raw UCI SECOM files, audit data quality, clean, and write analysis-ready tables.

Outputs
-------
data/processed/wafers.csv          one row per production run: id, timestamp, result, shift, week
data/processed/sensors_clean.csv   cleaned + imputed sensor matrix (kept sensors only)
reports/data_quality_report.csv    per-sensor audit: missing %, variance, keep/drop reason
"""
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
RAW, OUT, REP = ROOT / "data/raw", ROOT / "data/processed", ROOT / "reports"

MAX_MISSING = 0.40      # drop sensors missing in more than 40% of runs
MAX_CORR = 0.95         # drop one of each pair of near-duplicate sensors


def load_raw() -> tuple[pd.DataFrame, pd.DataFrame]:
    sensors = pd.read_csv(RAW / "secom.data", sep=r"\s+", header=None)
    sensors.columns = [f"S{i:03d}" for i in range(sensors.shape[1])]
    labels = pd.read_csv(RAW / "secom_labels.data", sep=r"\s+", header=None, names=["label", "timestamp"])
    labels["timestamp"] = pd.to_datetime(labels["timestamp"], format="%d/%m/%Y %H:%M:%S")
    return sensors, labels


def build_wafer_table(labels: pd.DataFrame) -> pd.DataFrame:
    w = labels.copy()
    w.insert(0, "run_id", np.arange(1, len(w) + 1))
    w["result"] = np.where(w["label"] == 1, "FAIL", "PASS")
    w["is_fail"] = (w["label"] == 1).astype(int)
    hour = w["timestamp"].dt.hour
    w["shift"] = np.select([hour.between(6, 13), hour.between(14, 21)], ["Early (06-14)", "Late (14-22)"], "Night (22-06)")
    w["week_start"] = w["timestamp"].dt.to_period("W-SUN").dt.start_time.dt.date
    w["weekday"] = w["timestamp"].dt.day_name()
    return w.drop(columns="label")


def audit_and_clean(sensors: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    audit = pd.DataFrame({
        "sensor": sensors.columns,
        "missing_pct": sensors.isna().mean().values * 100,
        "std": sensors.std().values,
        "n_unique": sensors.nunique().values,
    })
    audit["drop_reason"] = ""
    audit.loc[audit["missing_pct"] > MAX_MISSING * 100, "drop_reason"] = f"missing > {MAX_MISSING:.0%}"
    audit.loc[(audit["drop_reason"] == "") & (audit["n_unique"] <= 1), "drop_reason"] = "constant (zero variance)"

    kept = audit.loc[audit["drop_reason"] == "", "sensor"].tolist()
    X = sensors[kept].fillna(sensors[kept].median())

    # Remove redundant sensors: keep the first of any pair with |r| > MAX_CORR
    corr = X.corr().abs()
    upper = corr.where(np.triu(np.ones(corr.shape, dtype=bool), k=1))
    redundant = [c for c in upper.columns if (upper[c] > MAX_CORR).any()]
    audit.loc[audit["sensor"].isin(redundant), "drop_reason"] = f"redundant (|r| > {MAX_CORR})"
    X = X.drop(columns=redundant)

    audit["kept"] = audit["drop_reason"] == ""
    return X, audit


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    REP.mkdir(parents=True, exist_ok=True)
    sensors, labels = load_raw()
    wafers = build_wafer_table(labels)
    X, audit = audit_and_clean(sensors)

    wafers.to_csv(OUT / "wafers.csv", index=False)
    X = pd.concat([wafers[["run_id"]], X], axis=1)
    X.to_csv(OUT / "sensors_clean.csv", index=False)
    audit.round(4).to_csv(REP / "data_quality_report.csv", index=False)

    print(f"Runs: {len(wafers):,} | fails: {wafers.is_fail.sum()} | yield: {1 - wafers.is_fail.mean():.2%}")
    print(f"Sensors: {sensors.shape[1]} raw -> {X.shape[1] - 1} kept")
    print(audit.loc[~audit.kept, "drop_reason"].value_counts().to_string())


if __name__ == "__main__":
    main()
