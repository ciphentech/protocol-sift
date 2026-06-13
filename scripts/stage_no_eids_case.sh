#!/usr/bin/env bash
# Demo runner — stages the ntp-enrichment OPERATOR-QUESTION scene on demand.
#
# Purpose: reproduce the Phase 2 interaction where no EID 35/260 events are
# present in the exported timeline, so the enricher cannot auto-resolve the
# NTP source and must ask the operator: "What NTP source did this workstation
# use?" (the decision diamond in docs/time_sync_diagram.drawio).
#
# Deterministic & offline: uses --skip-nist-check, reuses the no-EID fixture
# (no invented data), writes only under /tmp.  The live take is intentionally
# NOT run non-interactively so Claude can pause and ask the operator.
#
# Lives in the authoring repo; the enricher and fixture it drives live in the
# sibling protocol-sift checkout (override with PROTOCOL_SIFT_DIR).
#
# Usage (from the hackasans-correlator repo root):
#   bash scripts/stage_no_eids_case.sh            # run straight through
#   PAUSE=1 bash scripts/stage_no_eids_case.sh    # pause between beats for narration
#
# After it runs, point a live Claude Code session at the printed case path and
# ask it to enrich the timeline — Claude will pause and ask for the NTP source.

set -uo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(dirname "$SCRIPT_DIR")"
PROTOCOL_SIFT_DIR="${PROTOCOL_SIFT_DIR:-$(dirname "$REPO_ROOT")/protocol-sift}"
AS="$PROTOCOL_SIFT_DIR/analysis-scripts"
if [ ! -f "$AS/ntp_enricher.py" ]; then
  echo "ERROR: ntp_enricher.py not found at $AS/" >&2
  echo "       Expected the sibling protocol-sift checkout at $PROTOCOL_SIFT_DIR" >&2
  echo "       (override with PROTOCOL_SIFT_DIR=/path/to/protocol-sift)" >&2
  exit 1
fi
cd "$AS"

CASE="${CASE:-DEMO-NTP-2026-001-no-eids}"
ROOT="/tmp/ntp_demo/${CASE}"
EXPORTS="${ROOT}/exports"
ANALYSIS="${ROOT}/analysis"
FIXTURE="tests/fixtures/ntp_mini_no_eids.csv"
INPUT="${EXPORTS}/${CASE}_timeline.csv"

beat() {
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
echo "   psort export staged : ${INPUT}"
echo "   fixture             : ntp_mini_no_eids.csv (no EID 35/260 events)"
echo "   row count           : $(tail -n +2 "$INPUT" | wc -l | tr -d ' ')"

# --- Beat 1: verify the fixture has no NTP sync events ----------------------
beat "Beat 1 — confirm no EID 35/260 events in the staged timeline"
if python3 - "$INPUT" <<'PY'; then
import csv, sys
eids = [r.get("event_identifier","") for r in csv.DictReader(open(sys.argv[1]))]
found = [e for e in eids if e in ("35","260")]
if found:
    print(f"   (!) found EID(s) {found} — wrong fixture")
    sys.exit(1)
print(f"   confirmed: no EID 35 or 260 entries ({len(eids)} rows total)")
PY
  echo "   the enricher will pause and ask the operator for the NTP source"
else
  echo "ERROR: fixture check failed" >&2; exit 1
fi

# --- Done: hand off to the live Claude session ------------------------------
beat "Done — point Claude Code here for the live take"
echo "   cd ${ROOT}"
echo "   then prompt:  \"Using the ntp-enrichment skill, enrich ${INPUT#${ROOT}/} to NIST UTC.\""
echo "   Claude will ask: 'What is the NTP source for this workstation?'"
echo "   Answer on camera: 'On-prem Windows, domain-joined. NTP source is base-dc.shieldbase.lan'"
echo
