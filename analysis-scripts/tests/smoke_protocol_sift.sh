#!/usr/bin/env bash
# smoke_protocol_sift.sh — end-to-end smoke test for Protocol SIFT.
#
# Verifies three core guarantees before running a real investigation:
#   1. NIST time service is reachable (checked first — fail fast)
#   2. Skill runs produce forensic log files (sift_logger JSONL)
#   3. Token usage is captured and written to token_usage.json
#
# Also covers: install completeness, NTP enrichment pipeline (offline + live),
# plaso tool availability (SIFT workstation), evidence integrity, S3 sync.
#
# Usage:
#   bash analysis-scripts/tests/smoke_protocol_sift.sh
#
# Plaso tool checks (Scene 6) are skipped gracefully when not on a SIFT
# workstation. All other scenes run fully offline except Scene 2 (NIST).

set -uo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
AS="$(dirname "$HERE")"            # analysis-scripts/
ROOT="$(dirname "$AS")"           # protocol-sift/
HOOKS="$ROOT/scripts/hooks"
OUT=/tmp/sift_smoke_$$
mkdir -p "$OUT"
cleanup() { rm -rf "$OUT"; }
trap cleanup EXIT

PASS=0; SKIP=0; NIST_OK=false

pass() { printf '[PASS] %s\n' "$1"; ((PASS++)) || true; }
skip() { printf '[SKIP] %s\n' "$1"; ((SKIP++)) || true; }
fail() { printf '[FAIL] %s\n' "$1"; exit 1; }
warn() { printf '[WARN] %s\n' "$1"; }

echo "========================================================================"
echo "Protocol SIFT — Smoke Test"
echo "Repo root:  $ROOT"
echo "Temp dir:   $OUT"
echo "========================================================================"
echo

# ── Scene 1: Install completeness ────────────────────────────────────────────
echo "── Scene 1: Install completeness ──────────────────────────────────────"

for script in ntp_resolver.py ntp_enricher.py ntp_nist_client.py ntp_manifest.py \
              sift_logger.py sift_s3_sync.py; do
    [ -f "$AS/$script" ] && pass "$script present" || fail "$script MISSING"
done

for skill in plaso-timeline ntp-enrichment memory-analysis sleuthkit \
             windows-artifacts yara-hunting; do
    [ -f "$ROOT/skills/$skill/SKILL.md" ] \
        && pass "skills/$skill/SKILL.md present" \
        || fail "skills/$skill/SKILL.md MISSING"
done

for hook in log_agent_trace.py capture_session.py; do
    [ -f "$HOOKS/$hook" ] && pass "hooks/$hook present" || fail "hooks/$hook MISSING"
done

grep -q "capture_session" "$ROOT/global/settings.json" \
    && pass "Stop hook wired to capture_session.py" \
    || fail "Stop hook does NOT reference capture_session.py"

grep -q "ntplib"  "$ROOT/requirements.txt" && pass "ntplib in requirements.txt"  || fail "ntplib MISSING"
grep -q "boto3"   "$ROOT/requirements.txt" && pass "boto3 in requirements.txt"   || fail "boto3 MISSING"
[ -f "$ROOT/sift.env.template" ]           && pass "sift.env.template present"   || fail "sift.env.template MISSING"
echo

# ── Scene 2: NIST reachability (checked FIRST — fail fast) ───────────────────
echo "── Scene 2: NIST reachability (early check) ────────────────────────────"
echo "  Checking NIST time servers before going further..."

python3 - "$AS" <<'PY'
import sys, socket
sys.path.insert(0, sys.argv[1])
from ntp_nist_client import DEFAULT_SERVERS, query, NistUnreachable
try:
    resp = query(DEFAULT_SERVERS, timeout_s=5.0, retries=1)
    print(f"  NIST responded: server={resp.server_used}  offset={resp.offset_s:+.4f}s  stratum={resp.stratum}")
    sys.exit(0)
except NistUnreachable as e:
    print(f"  NIST unreachable: {e}", file=sys.stderr)
    sys.exit(1)
PY
if [ $? -eq 0 ]; then
    pass "scene2: NIST time server reachable — NTP enrichment will use live NIST anchor"
    NIST_OK=true
else
    warn "scene2: NIST unreachable — live enrichment will halt fail-closed (SPEC §3.2)"
    warn "        Offline scenes will continue with --skip-nist-check"
    SKIP=$((SKIP+1))
fi
echo

# ── Scene 3: Log file creation (sift_logger JSONL) ───────────────────────────
echo "── Scene 3: Log file creation (sift_logger JSONL) ─────────────────────"

SIFT_LOGS_DIR="$OUT/logger_logs" python3 - "$AS" "$OUT/logger_logs" <<'PY' \
    || fail "scene3: sift_logger SiftSession failed"
import sys, json, os
from pathlib import Path
sys.path.insert(0, sys.argv[1])
import sift_logger   # SIFT_LOGS_DIR env var already set
from sift_logger import SiftSession

with SiftSession("smoke-test-plaso-timeline") as sess:
    sess.log("tool_called",
             tool_name="log2timeline.py",
             tool_input={"image": "/cases/test/suspect.E01"},
             reasoning="Smoke test: simulating plaso-timeline skill tool call.")
    sess.log("tool_called",
             tool_name="psort.py",
             tool_input={"input": "exports/test.plaso", "output": "exports/timeline.csv"},
             reasoning="Smoke test: simulating psort CSV export.")
    sess.log("evidence_integrity",
             path="exports/timeline.csv",
             sha256_before="abc123", sha256_after="abc123", ok=True,
             files_accessed=["exports/timeline.csv"],
             reasoning="Smoke test: integrity check.")
    sess.set_exit_code(0)

logs_dir = Path(sys.argv[2])
logs = sorted(logs_dir.glob("*.jsonl"))
assert logs, f"No JSONL written to {logs_dir}"

log_path = logs[0]
events = [json.loads(l) for l in log_path.read_text().splitlines() if l.strip()]
types_seen = {e["type"] for e in events}

assert "session_init"     in types_seen, f"session_init missing: {types_seen}"
assert "tool_called"      in types_seen, f"tool_called missing: {types_seen}"
assert "session_complete" in types_seen, f"session_complete missing: {types_seen}"

required_fields = {"os_user", "timestamp", "session_id", "type"}
for e in events:
    missing = required_fields - e.keys()
    assert not missing, f"Fields {missing} missing in event: {e}"

print(f"  Log file: {log_path.name}")
print(f"  Events: {len(events)}  types: {sorted(types_seen)}")
PY
pass "scene3: JSONL log file created with session_init / tool_called / session_complete and all required fields"

# Verify file exists on disk with content
LOG_FILES=$(ls "$OUT/logger_logs/"*.jsonl 2>/dev/null | wc -l)
[ "$LOG_FILES" -ge 1 ] \
    && pass "scene3: $LOG_FILES JSONL log file(s) present in logs directory" \
    || fail "scene3: no JSONL log files found"
echo

# ── Scene 4: Token usage capture (capture_session.py) ────────────────────────
echo "── Scene 4: Token usage capture (token_usage.json) ────────────────────"

# Build a synthetic Claude session JSONL with token usage data
mkdir -p "$OUT/fake_projects/test-session"
cat > "$OUT/fake_projects/test-session/abc12345.jsonl" <<'JSON'
{"type":"user","sessionId":"abc12345","message":{"role":"user","content":"Run NTP enrichment"}}
{"type":"assistant","sessionId":"abc12345","model":"claude-sonnet-4-6","message":{"role":"assistant","content":"Running enrichment..."},"usage":{"input_tokens":1250,"output_tokens":310,"cache_read_input_tokens":8400,"cache_creation_input_tokens":0}}
{"type":"assistant","sessionId":"abc12345","model":"claude-sonnet-4-6","message":{"role":"assistant","content":"Enrichment complete."},"usage":{"input_tokens":980,"output_tokens":185,"cache_read_input_tokens":9100,"cache_creation_input_tokens":0}}
JSON

mkdir -p "$OUT/token_analysis"
SIFT_PROJECTS_DIR="$OUT/fake_projects" \
SIFT_ANALYSIS_DIR="$OUT/token_analysis" \
python3 "$HOOKS/capture_session.py" \
    || fail "scene4: capture_session.py exited non-zero"

[ -f "$OUT/token_analysis/token_usage.json" ] \
    || fail "scene4: token_usage.json not written"

python3 - "$OUT/token_analysis/token_usage.json" <<'PY' || fail "scene4: token_usage.json assertions"
import json, sys
r = json.load(open(sys.argv[1]))
assert "session_id"   in r, "session_id missing"
assert "generated_at" in r, "generated_at missing"
assert "by_model"     in r, "by_model missing"
assert "_total_estimated_usd" in r["by_model"], "_total_estimated_usd missing"

model = "claude-sonnet-4-6"
assert model in r["by_model"], f"{model} not found in by_model"
m = r["by_model"][model]
assert m["input_tokens"]  == 2230, f"input_tokens mismatch: {m['input_tokens']}"
assert m["output_tokens"] == 495,  f"output_tokens mismatch: {m['output_tokens']}"
assert m["estimated_usd"] > 0,     f"estimated_usd is zero"
print(f"  session_id={r['session_id']}")
print(f"  model={model}  input={m['input_tokens']}  output={m['output_tokens']}  usd=${m['estimated_usd']:.6f}")
print(f"  total_usd=${r['by_model']['_total_estimated_usd']:.6f}")
PY
pass "scene4: token_usage.json written with per-model token counts and USD cost estimate"

[ -f "$OUT/token_analysis/abc12345_session.jsonl" ] \
    && pass "scene4: session transcript copy written alongside token_usage.json" \
    || fail "scene4: session transcript copy not found"
echo

# ── Scene 5: NTP enrichment — offline happy path + log file verification ──────
echo "── Scene 5: NTP enrichment — offline (--skip-nist-check) ──────────────"

mkdir -p "$OUT/ntp_logs" "$OUT/ntp_out"
SIFT_LOGS_DIR="$OUT/ntp_logs" \
python3 "$AS/ntp_enricher.py" \
    --input  "$HERE/fixtures/ntp_mini.csv" \
    --output "$OUT/ntp_out/timeline_enriched.csv" \
    --skip-nist-check --non-interactive >/dev/null 2>&1 \
    || fail "scene5: ntp_enricher.py exited non-zero"

[ -f "$OUT/ntp_out/timeline_enriched.csv" ] \
    && pass "scene5: enriched CSV written" \
    || fail "scene5: enriched CSV not found"

REPORT="$OUT/ntp_out/timeline_enriched_accuracy_report.json"
[ -f "$REPORT" ] && pass "scene5: accuracy report JSON written" || fail "scene5: accuracy report not found"

python3 - "$REPORT" <<'PY' || fail "scene5: report assertions"
import json, sys
r = json.load(open(sys.argv[1]))
assert r["rows_assumption_true"] == 0,          f"unexpected assumptions: {r}"
assert r["unresolved_rows"]      == [],          f"unresolved rows: {r['unresolved_rows']}"
assert "base-dc.shieldbase.lan" in r["ntp_context"]["ntp_source"], r["ntp_context"]
print(f"  ntp_source={r['ntp_context']['ntp_source']}  confidence={r['ntp_context'].get('confidence_rank','?')}")
PY
pass "scene5: LOG_DERIVED source resolved, zero unresolved rows, correct NTP server identified"

# Verify sift_logger wrote a log file during this run
NTP_LOG_COUNT=$(ls "$OUT/ntp_logs/"*.jsonl 2>/dev/null | wc -l)
[ "$NTP_LOG_COUNT" -ge 1 ] \
    && pass "scene5: sift_logger JSONL written during ntp_enricher run ($NTP_LOG_COUNT file(s))" \
    || skip "scene5: sift_logger JSONL not found (ntp_enricher may not use SiftSession)"
echo

# ── Scene 6 (optional): NTP enrichment — live NIST validation ────────────────
echo "── Scene 6: NTP enrichment — live NIST validation ──────────────────────"

if [ "$NIST_OK" = true ]; then
    mkdir -p "$OUT/ntp_live_logs" "$OUT/ntp_live_out"
    SIFT_LOGS_DIR="$OUT/ntp_live_logs" \
    python3 "$AS/ntp_enricher.py" \
        --input  "$HERE/fixtures/ntp_mini.csv" \
        --output "$OUT/ntp_live_out/timeline_enriched.csv" \
        --non-interactive >/dev/null 2>&1 \
        && pass "scene6: live NIST enrichment completed without error" \
        || fail "scene6: live NIST enrichment failed (NIST was reachable — check for regression)"
else
    skip "scene6: skipped — NIST unreachable (see Scene 2)"
fi
echo

# ── Scene 7: Evidence integrity ──────────────────────────────────────────────
echo "── Scene 7: Evidence integrity ─────────────────────────────────────────"

SRC="$HERE/fixtures/ntp_mini.csv"
BEFORE="$(sha256sum "$SRC" | awk '{print $1}')"
SIFT_LOGS_DIR="$OUT/integ_logs" \
python3 "$AS/ntp_enricher.py" \
    --input "$SRC" --output "$OUT/integ_enriched.csv" \
    --skip-nist-check --non-interactive >/dev/null 2>&1
AFTER="$(sha256sum "$SRC" | awk '{print $1}')"
[ "$BEFORE" = "$AFTER" ] \
    && pass "scene7: source CSV SHA-256 unchanged after enrichment" \
    || fail "scene7: source CSV was MODIFIED during enrichment"

if python3 "$AS/ntp_enricher.py" \
       --input "$SRC" --output /cases/must_be_rejected.csv \
       --skip-nist-check --non-interactive >/dev/null 2>&1; then
    fail "scene7: /cases/ write was NOT rejected (evidence path guard broken)"
else
    pass "scene7: write to /cases/ correctly rejected by evidence path guard"
fi
echo

# ── Scene 8: Plaso tool availability + psort sanity (SIFT workstation) ────────
echo "── Scene 8: Plaso tool availability (SIFT workstation) ─────────────────"
# Override PLASO_FIXTURE to point at your targeted evtx plaso (small file, fast).
# Avoid full-disk plaso files (9M+ events) — psort scans every event even for
# narrow filters and will hang for 25+ minutes.
PLASO_FIXTURE="${PLASO_FIXTURE:-/cases/rd01/analysis/rd01-system-evtx.plaso}"
# Anchor --slice to a timestamp known to exist in rd01-system-evtx.plaso.
# Do NOT use a date-range filter against a plaso whose events are in a different
# era — all events will be filtered out and psort writes an empty CSV.
PLASO_SLICE="${PLASO_SLICE:-2018-05-04T22:14:29}"

for tool in log2timeline.py psort.py pinfo.py; do
    if command -v "$tool" >/dev/null 2>&1; then
        pass "scene8: $tool in PATH"
    else
        skip "scene8: $tool not found (not on SIFT workstation)"
    fi
done

if command -v log2timeline.py >/dev/null 2>&1; then
    log2timeline.py --version >/dev/null 2>&1 \
        && pass "scene8: log2timeline.py --version exits 0" \
        || skip "scene8: log2timeline.py --version returned non-zero"
fi

if command -v psort.py >/dev/null 2>&1 && [ -f "$PLASO_FIXTURE" ]; then
    PSORT_OUT="$OUT/scene8_slice.csv"
    PSORT_ERR=$(mktemp)
    rm -f "$PSORT_OUT"  # psort refuses to overwrite — remove stale file first
    # timeout 120: a targeted evtx plaso (~15K events) completes in seconds;
    # if PLASO_FIXTURE is accidentally set to a full-disk plaso, cap the hang.
    timeout 120 psort.py -o l2tcsv \
        -w "$PSORT_OUT" \
        --slice "$PLASO_SLICE" \
        "$PLASO_FIXTURE" >/dev/null 2>"$PSORT_ERR"
    PSORT_RC=$?
    if [ "$PSORT_RC" -eq 0 ]; then
        pass "scene8: psort --slice completed against $(basename "$PLASO_FIXTURE")"
    elif [ "$PSORT_RC" -eq 124 ]; then
        fail "scene8: psort --slice timed out after 120 s — PLASO_FIXTURE may be a full-disk plaso; use a targeted evtx plaso instead"
    else
        fail "scene8: psort --slice returned $PSORT_RC — stderr: $(cat "$PSORT_ERR")"
    fi
    rm -f "$PSORT_ERR"

    EVENT_COUNT=$(wc -l < "$PSORT_OUT" 2>/dev/null || echo 0)
    [ "$EVENT_COUNT" -gt 1 ] \
        && pass "scene8: psort output has $((EVENT_COUNT - 1)) event rows (slice non-empty)" \
        || fail "scene8: psort output is empty — wrong plaso file or slice timestamp has no nearby events"
elif command -v psort.py >/dev/null 2>&1; then
    skip "scene8: psort in PATH but $PLASO_FIXTURE not found — set PLASO_FIXTURE env var to a targeted evtx plaso"
fi
echo

# ── Scene 9: S3 sync dry run ─────────────────────────────────────────────────
echo "── Scene 9: S3 sync dry run ────────────────────────────────────────────"

mkdir -p "$OUT/sync_logs"
echo '{"type":"session_init","session_id":"SIFT-2026-06-11-deadbeef"}' \
    > "$OUT/sync_logs/SIFT-2026-06-11-deadbeef.jsonl"

python3 "$AS/sift_s3_sync.py" --logs-dir "$OUT/sync_logs" --dry-run 2>/dev/null \
    && pass "scene9: sift_s3_sync.py --dry-run exits 0 with no bucket set" \
    || fail "scene9: sift_s3_sync.py --dry-run returned non-zero"
echo

# ── Summary ───────────────────────────────────────────────────────────────────
echo "========================================================================"
printf 'RESULT: %d passed, %d skipped\n' "$PASS" "$SKIP"
if [ "$NIST_OK" = false ]; then
    echo "ACTION REQUIRED: NIST was unreachable. Resolve network access to"
    echo "  time-a-wwv.nist.gov before running a live investigation."
fi
echo "========================================================================"
