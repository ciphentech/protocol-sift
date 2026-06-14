#!/usr/bin/env bash
# integration_ntp.sh — end-to-end integration test: psort slice → NTP enrichment.
# Requires Plaso tools (psort.py) on a SIFT workstation and a real .plaso file.
# Override defaults via env vars: CASE_DIR, PLASO, EXPORTS, SLICE_TS
# Security: read-only on the .plaso file; writes only to ${EXPORTS} under the case dir.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# ── SIFT workstation preflight ────────────────────────────────────────────────
if ! command -v psort.py >/dev/null 2>&1; then
    echo "[warn] psort.py not found — this script requires a SIFT workstation" >&2
    echo "[warn] with Plaso installed. Install via:" >&2
    echo "[warn]   sudo add-apt-repository ppa:gift/stable" >&2
    echo "[warn]   sudo apt-get update && sudo apt-get install python3-plaso plaso-tools" >&2
    exit 1
fi

CASE_DIR="${CASE_DIR:-/cases/CLIENT-IR-2025-001}"
PLASO="${PLASO:-${CASE_DIR}/analysis/rd01-system-evtx.plaso}"
EXPORTS="${EXPORTS:-${CASE_DIR}/exports}"
SLICE_TS="${SLICE_TS:-2018-05-04T22:14:29}"

TS=$(date -u +"%Y%m%d_%H%M%S")
SLICE_CSV="${EXPORTS}/smoke_test_slice_${TS}.csv"
ENRICHED_CSV="${EXPORTS}/smoke_test_slice_${TS}_enriched.csv"

echo "[0/2] Removing stale smoke_test_slice files from ${EXPORTS}..."
find "${EXPORTS}" -maxdepth 1 -name 'smoke_test_slice_*' -delete
echo "      Done."

echo "[1/2] psort --slice ${SLICE_TS} -> $(basename "${SLICE_CSV}")"
psort.py -o l2tcsv -w "${SLICE_CSV}" --slice "${SLICE_TS}" "${PLASO}"

echo "[2/2] ntp_enricher -> $(basename "${ENRICHED_CSV}")"
python3 "${SCRIPT_DIR}/ntp_enricher.py" \
  --input  "${SLICE_CSV}" \
  --output "${ENRICHED_CSV}" \
  --case-dir "${CASE_DIR}" \
  --windows-domain-joined

echo "Done: ${ENRICHED_CSV}"
