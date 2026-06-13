#!/usr/bin/env bash
# tlcorr_pipeline.sh — NIST-anchored Plaso timeline enrichment orchestrator
# Delegates enrichment to the ntp_*.py helpers that sit alongside this script.
#
# Usage:
#   bash analysis-scripts/tlcorr_pipeline.sh \
#     --input  <csv>  --case <id>  --outdir <dir>  [--ntp-source <host>]  [--skip-ntp]
#
# Required arguments:
#   --input  <csv>   Path to the Plaso-exported CSV timeline (read-only; never modified).
#   --case   <id>    Case identifier used to name all output files (e.g. "case42").
#   --outdir <dir>   Root output directory.  Must not overlap with the input file's
#                    directory or any evidence-protected mount (/cases, /mnt, /media).
#
# Optional arguments:
#   --ntp-source <host>  Override the NTP server used for NIST anchoring instead of
#                        the one discovered from case artifacts or the built-in default.
#   --skip-ntp           Skip NTP/NIST enrichment entirely.  Output will NOT be
#                        NIST-anchored; a warning is printed and logged.
#   --nist-server <host> Override the NIST server hostname (testing — lets the
#                        smoke suite force the NIST-unreachable halt, exit 2).
#
# Outputs:
#   <outdir>/exports/<case>_correlated.csv  — enriched timeline
#   <outdir>/analysis/<case>_accuracy.json  — assumption + accuracy report (SPEC §2.3)
#   <outdir>/analysis/forensic_audit.log    — append-only UTC audit trail
#
# Requires the ntp_*.py helpers in the same directory as this script
# (in-repo: analysis-scripts/; deployed: ~/.claude/analysis-scripts/):
#   ntp_enricher.py  (+ ntp_resolver, ntp_nist_client, ntp_manifest)
# Dependencies (from requirements.txt): pandas>=2.0, ntplib>=0.4

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
HELPERS_DIR="$SCRIPT_DIR"

# ── Helper check (runs before arg parsing so failure is instant) ──────────────
_require_helpers() {
    if [[ ! -f "$HELPERS_DIR/ntp_enricher.py" ]]; then
        echo "ERROR: ntp_enricher.py not found at: $HELPERS_DIR/ntp_enricher.py" >&2
        echo "       The ntp_*.py helpers must sit alongside this script (re-run install.sh)." >&2
        exit 1
    fi
    # Check Python dependencies (pandas + ntplib required by ntp_enricher.py)
    if ! PYTHONPATH="$HELPERS_DIR" python3 -c "import pandas, ntplib" 2>/dev/null; then
        echo "ERROR: Missing Python dependencies (pandas, ntplib)." >&2
        echo "       Install from requirements.txt:" >&2
        echo "       pip install -r requirements.txt" >&2
        exit 1
    fi
}
_require_helpers

# ── Argument parsing ──────────────────────────────────────────────────────────
INPUT="" CASE="" OUTDIR="" NTP_SRC_OVERRIDE="" NIST_SERVER_OVERRIDE="" SKIP_NTP=false

while [[ $# -gt 0 ]]; do
    case "$1" in
        --input)       INPUT="$2";                shift 2 ;;
        --case)        CASE="$2";                 shift 2 ;;
        --outdir)      OUTDIR="$2";               shift 2 ;;
        --ntp-source)  NTP_SRC_OVERRIDE="$2";     shift 2 ;;
        --nist-server) NIST_SERVER_OVERRIDE="$2"; shift 2 ;;
        --skip-ntp)    SKIP_NTP=true;             shift   ;;
        -h|--help)    sed -n '2p' "$0"; exit 0 ;;
        *)            echo "ERROR: unknown flag: $1" >&2; exit 1 ;;
    esac
done

[[ -n "$INPUT"  ]] || { echo "ERROR: --input is required"  >&2; exit 1; }
[[ -n "$CASE"   ]] || { echo "ERROR: --case is required"   >&2; exit 1; }
[[ -n "$OUTDIR" ]] || { echo "ERROR: --outdir is required" >&2; exit 1; }
[[ -f "$INPUT"  ]] || { echo "ERROR: input not found: $INPUT" >&2; exit 1; }

# ── Evidence integrity: refuse writes back to source paths (Feature 1 / SPEC §8) ──
INPUT_ABS="$(python3 -c "import os,sys; print(os.path.realpath(sys.argv[1]))" "$INPUT")"
OUTDIR_ABS="$(python3 -c "import os,sys; print(os.path.abspath(sys.argv[1]))"  "$OUTDIR")"
INPUT_DIR="$(dirname "$INPUT_ABS")"

for guarded in /cases /mnt /media; do
    if [[ "$OUTDIR_ABS" == "$guarded"* ]]; then
        echo "ERROR: --outdir ($OUTDIR_ABS) is inside evidence-protected path $guarded" >&2
        exit 1
    fi
done
if [[ "$OUTDIR_ABS" == "$INPUT_DIR" || "$OUTDIR_ABS" == "$INPUT_DIR/"* ]]; then
    echo "ERROR: --outdir must not overlap with the input file's directory (evidence integrity)" >&2
    exit 1
fi

# ── Output directory structure ────────────────────────────────────────────────
EXPORTS="$OUTDIR/exports"
ANALYSIS="$OUTDIR/analysis"
mkdir -p "$EXPORTS" "$ANALYSIS" "$OUTDIR/reports"

CORR_CSV="$EXPORTS/${CASE}_correlated.csv"
ACC_JSON="$ANALYSIS/${CASE}_accuracy.json"
AUDIT_LOG="$ANALYSIS/forensic_audit.log"

# ntp_enricher.py writes its accuracy report alongside the output CSV
ENRICHER_REPORT="$EXPORTS/${CASE}_correlated_accuracy_report.json"

# ── Helpers ───────────────────────────────────────────────────────────────────
ts()     { python3 -c "from datetime import datetime,timezone; print(datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ'))"; }
audit()  { printf '%s  %s\n' "$(ts)" "$*" >> "$AUDIT_LOG"; }
banner() { local n="$1"; shift; echo "[tlcorr] stage $n/4 — $*"; audit "STAGE $n/4: $*"; }

INPUT_SHA="$(python3 -c "
import hashlib, sys
print(hashlib.sha256(open(sys.argv[1],'rb').read()).hexdigest())
" "$INPUT")"

audit "RUN START  case=$CASE  input=$INPUT_ABS  sha256=$INPUT_SHA"
audit "FLAGS  skip-ntp=$SKIP_NTP  ntp-override=${NTP_SRC_OVERRIDE:-none}"
audit "HELPERS  dir=$HELPERS_DIR"

# ── Stage 1/5: Ingest ─────────────────────────────────────────────────────────
banner 1 "ingesting $INPUT"
EVENT_COUNT="$(python3 -c "
import csv
print(sum(1 for _ in csv.DictReader(open('$INPUT', newline=''))))
")"
echo "[tlcorr]   events: $EVENT_COUNT"
echo "[tlcorr]   helpers: $HELPERS_DIR"
audit "INGEST events=$EVENT_COUNT"

# ── Stage 2/5: NTP enrichment ─────────────────────────────────────────────────
# Delegates to ntp_enricher.py (same directory), which handles:
#   - Phase 2 NTP source resolution (artifact scan → flag → default)
#   - Phase 3 NIST time query
#   - CSV enrichment (5 new fields + re-sort on nist_time)
#   - Self-correction loop (up to 3 iterations, ±1000 s bound)
#   - Accuracy report emit (SPEC §2.3)
banner 2 "NTP enrichment (ntp_enricher.py)"

ENRICHER_ARGS=(
    "--input"           "$INPUT_ABS"
    "--output"          "$CORR_CSV"
    "--case-dir"        "$OUTDIR"
    "--non-interactive"
)
[[ -n "$NTP_SRC_OVERRIDE" ]]     && ENRICHER_ARGS+=("--ntp-source" "$NTP_SRC_OVERRIDE")
[[ -n "$NIST_SERVER_OVERRIDE" ]] && ENRICHER_ARGS+=("--nist-server" "$NIST_SERVER_OVERRIDE")
$SKIP_NTP                        && ENRICHER_ARGS+=("--skip-ntp")

# `|| ENRICHER_EXIT=$?` keeps set -e from aborting before the case block below
# can log ENRICHER_FAIL and emit the analyst-facing error message.
ENRICHER_EXIT=0
PYTHONPATH="$HELPERS_DIR${PYTHONPATH:+:$PYTHONPATH}" \
    python3 "$HELPERS_DIR/ntp_enricher.py" "${ENRICHER_ARGS[@]}" || ENRICHER_EXIT=$?

case $ENRICHER_EXIT in
    0) audit "ENRICHER_OK" ;;
    2) echo "[tlcorr] ERROR: all NIST/NTP servers unreachable (exit 2)" >&2
       echo "[tlcorr]        Verify outbound UDP/123 or use --skip-ntp to bypass." >&2
       audit "ENRICHER_FAIL exit=2 nist-unreachable"
       exit 2 ;;
    3) echo "[tlcorr] ERROR: self-correction exhausted — implausible offsets remain (exit 3)" >&2
       echo "[tlcorr]        Review $CORR_CSV for rows with |ntp_offset_s| > 1000 s." >&2
       audit "ENRICHER_FAIL exit=3 self-correction-exhausted"
       exit 3 ;;
    *) echo "[tlcorr] ERROR: ntp_enricher.py exited with unexpected code $ENRICHER_EXIT" >&2
       audit "ENRICHER_FAIL exit=$ENRICHER_EXIT"
       exit "$ENRICHER_EXIT" ;;
esac

# ── Stage 3/4: Input integrity verification ───────────────────────────────────
banner 3 "evidence integrity check"
FINAL_SHA="$(python3 -c "
import hashlib, sys
print(hashlib.sha256(open(sys.argv[1],'rb').read()).hexdigest())
" "$INPUT")"
if [[ "$FINAL_SHA" != "$INPUT_SHA" ]]; then
    echo "[tlcorr] ERROR: input file SHA-256 changed during run — possible spoliation!" >&2
    echo "[tlcorr]        Before: $INPUT_SHA" >&2
    echo "[tlcorr]        After:  $FINAL_SHA" >&2
    audit "INTEGRITY VIOLATION pre=$INPUT_SHA post=$FINAL_SHA"
    exit 1
fi
echo "[tlcorr]   SHA-256 unchanged: $INPUT_SHA"
audit "INTEGRITY_OK post-run-sha256=$FINAL_SHA"

# ── Stage 4/4: Collect accuracy report + summary ─────────────────────────────
banner 4 "collecting accuracy report"

# ntp_enricher.py writes the report next to the output CSV; move it to ANALYSIS/
if [[ -f "$ENRICHER_REPORT" ]]; then
    mv "$ENRICHER_REPORT" "$ACC_JSON"
    audit "ACCURACY_REPORT $ENRICHER_REPORT → $ACC_JSON"
else
    echo "[tlcorr]   WARN: accuracy report not found at expected path: $ENRICHER_REPORT" >&2
    audit "ACCURACY_REPORT not found at $ENRICHER_REPORT"
fi

# Extract summary fields from the accuracy report for display
NTP_SOURCE="n/a" ASSUMED_COUNT=0 ITERATIONS=1
if [[ -f "$ACC_JSON" ]]; then
    NTP_SOURCE="$(python3 -c "
import json, sys
d = json.load(open(sys.argv[1]))
print(d.get('ntp_context', {}).get('ntp_source', 'n/a'))
" "$ACC_JSON" 2>/dev/null || echo 'n/a')"
    ASSUMED_COUNT="$(python3 -c "
import json, sys
d = json.load(open(sys.argv[1]))
print(d.get('rows_assumption_true', 0))
" "$ACC_JSON" 2>/dev/null || echo '0')"
fi

audit "CORRELATED written: $CORR_CSV"
audit "RUN END  case=$CASE"

echo ""
echo "[tlcorr] ──────────────────────────────────────────────────────"
printf "[tlcorr] DONE  case=%s\n"                       "$CASE"
printf "[tlcorr]   Events processed:     %s\n"          "$EVENT_COUNT"
printf "[tlcorr]   NTP source:           %s\n"          "$NTP_SOURCE"
printf "[tlcorr]   Assumed NTP events:   %s / %s\n"     "$ASSUMED_COUNT" "$EVENT_COUNT"
$SKIP_NTP && printf "[tlcorr]   *** Output is NOT NIST-anchored (--skip-ntp) ***\n"
printf "[tlcorr]   Correlated timeline:  %s\n"          "$CORR_CSV"
printf "[tlcorr]   Accuracy report:      %s\n"          "$ACC_JSON"
printf "[tlcorr]   Audit log:            %s\n"          "$AUDIT_LOG"
printf "[tlcorr]   helpers:              %s\n"          "$HELPERS_DIR"
echo "[tlcorr] ──────────────────────────────────────────────────────"
