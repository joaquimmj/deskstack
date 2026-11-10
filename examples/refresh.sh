#!/usr/bin/env bash
# Re-records every example from the live connector, then rebuilds the workbooks and reports.
# Needs Node (server/) and Python with openpyxl. Calls the hosted connector about 20 times.
set -euo pipefail
cd "$(dirname "$0")/.."
(cd server && npx tsx scripts/examples.ts data)
python3 examples/build.py || true          # writes batches.json; reports wait for the verify step
(cd server && npx tsx scripts/examples.ts verify)
python3 examples/build.py
