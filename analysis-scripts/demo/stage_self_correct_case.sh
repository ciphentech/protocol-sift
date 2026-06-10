#!/usr/bin/env bash
# Demo runner — stages the ntp-enrichment SELF-CORRECTION scene on demand.
#
# Purpose: reliably reproduce, on camera, the Phase 3 detect -> retry -> halt
# behavior (SPEC §4 Phase 3). Feeds the implausible-offset fixture so the
# enricher flags |offset| > ±1000 s, re-resolves (bounded by MAX_ITERATIONS=3),
# and then HALTS fail-closed with an unresolved-rows summary (exit code 3) —
# without ever modifying the source CSV or emitting a corrupted enriched CSV.
#
# Deterministic & offline: uses --skip-nist-check and --non-interactive, reuses
# the existing fixture (no invented data), writes only under /tmp.
#
# Usage:
#   bash stage_self_correct_case.sh            # run straight through
#   PAUSE=1 bash stage_self_correct_case.sh    # pause between beats for narration
#
# After it runs, point a live Claude Code session at the printed case path and
# ask it to enrich the timeline — Claude reaches the same halt and report.

set -uo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
AS="$(dirname "$HERE")"                         # analysis-scripts/
cd "$AS"

CASE="${CASE:-DEMO-NTP-2026-001}"
ROOT="/tmp/ntp_demo/${CASE}"
EXPORTS="${ROOT}/exports"
ANALYSIS="${ROOT}/analysis"
FIXTURE="tests/fixtures/ntp_mini_implausible.csv"
INPUT="${EXPORTS}/${CASE}_timeline.csv"
OUTPUT="${EXPORTS}/${CASE}_timeline_enriched.csv"
REPORT="${EXPORTS}/${CASE}_timeline_enriched_accuracy_report.json"

beat() {                                        # narration checkpoint
  echo
  echo "=== $1 ==="
  if [ "${PAUSE:-0}" = "1" ]; then
    read -r -p "   [press Enter to continue] " _ </dev/tty || true
  fi
}

# --- Beat 0: stage a realistic throwaway case -------------------------------
beat "Beat 0 — stage case ${CASE} under ${ROOT}"
rm -rf "$ROOT"; mkdir -p "$EXPORTS" "$ANALYSIS"
cp "$FIXTURE" "$INPUT"
echo "   psort export staged: ${INPUT}"
SRC_BEFORE="$(sha256sum "$INPUT" | awk '{print $1}')"
echo "   source sha256 (before): ${SRC_BEFORE}"

# --- Beat 1: run the enricher; expect the self-correction HALT --------------
beat "Beat 1 — run ntp_enricher.py (expect detect -> retry -> halt)"
set +e
python3 ntp_enricher.py \
  --input "$INPUT" \
  --output "$OUTPUT" \
  --case-dir "$ROOT" \
  --skip-nist-check \
  --non-interactive
RC=$?
set -e
echo "   exit code: ${RC}   (3 = Phase 3 self-correction halt, as designed)"

# --- Beat 2: show the unresolved-rows summary from the accuracy report -------
beat "Beat 2 — why it halted (accuracy report unresolved_rows)"
if [ -f "$REPORT" ]; then
  python3 - "$REPORT" <<'PY'
import json, sys
r = json.load(open(sys.argv[1]))
print("   rows_total              :", r.get("rows_total"))
print("   unresolved_rows         :", len(r.get("unresolved_rows", [])))
for u in r.get("unresolved_rows", []):
    print(f"     - row {u.get('row_id')}: {u.get('rejection_basis')}")
print("   spec_caveats_applicable :", r.get("spec_caveats_applicable"))
PY
else
  echo "   (!) accuracy report not found at ${REPORT}"
fi

# --- Beat 3: integrity guarantee --------------------------------------------
beat "Beat 3 — integrity: source untouched, no corrupted timeline emitted"
SRC_AFTER="$(sha256sum "$INPUT" | awk '{print $1}')"
echo "   source sha256 (after) : ${SRC_AFTER}"
if [ "$SRC_BEFORE" = "$SRC_AFTER" ]; then
  echo "   ✓ source CSV unchanged (chain of custody intact)"
else
  echo "   ✗ source CSV WAS MODIFIED — this should never happen"
fi
if [ -f "$OUTPUT" ]; then
  echo "   note: enriched CSV exists but contains no NIST-anchored bad data on halt"
else
  echo "   ✓ no enriched CSV written — it refused to ship an implausible timeline"
fi

# --- Done: hand off to the live Claude session ------------------------------
beat "Done — point Claude Code here for the live take"
echo "   cd ${ROOT}"
echo "   then prompt:  \"Enrich ${INPUT#${ROOT}/} to NIST UTC using the ntp-enrichment skill.\""
echo
