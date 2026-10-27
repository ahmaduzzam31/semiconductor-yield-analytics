#!/usr/bin/env bash
# Reproduce every output in this repository from the raw data.
set -euo pipefail
cd "$(dirname "$0")"
python src/prepare_data.py
jupyter nbconvert --to notebook --execute --inplace notebooks/yield_analysis.ipynb
python src/build_dashboard.py
