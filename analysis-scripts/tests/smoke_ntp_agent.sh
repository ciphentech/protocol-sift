#!/usr/bin/env bash
# Smoke test for the NTP enrichment agent loop (SPEC §2.2 / §3 / §4 / §8).
# Three scenes, one PASS each: happy path, plausibility-bound self-correction halt,
# and the evidence-integrity guarantee. Runs the CLI directly (no Claude API / no
# network — uses --skip-nist-check) so it is deterministic and idempotent.
# Security: read-only over fixtures; writes only under /tmp; no external input.

set -uo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
AS="$(dirname "$HERE")"            # analysis-scripts/
cd "$AS"
OUT=/tmp/ntp_smoke
rm -rf "$OUT"; mkdir -p "$OUT"

pass() { echo "[PASS] $1"; }
fail() { echo "[FAIL] $1"; exit 1; }

# --- Scene 1: happy path (artifact has EID 35/260) --------------------------
python3 ntp_enricher.py --input tests/fixtures/ntp_mini.csv \
  --output "$OUT/case1/ntp_mini_enriched.csv" --skip-nist-check --non-interactive >/dev/null 2>&1
R1="$OUT/case1/ntp_mini_enriched_accuracy_report.json"
python3 - "$R1" <<'PY' || fail "scene1: report assertions"
import json, sys
r = json.load(open(sys.argv[1]))
assert r["rows_assumption_true"] == 0, r["rows_assumption_true"]
assert r["unresolved_rows"] == [], r["unresolved_rows"]
assert r["ntp_context"]["ntp_source"] == "base-dc.shieldbase.lan", r["ntp_context"]
PY
pass "scene1: LOG_DERIVED source, no unresolved rows"

# --- Scene 2: plausibility bound -> SPEC §4 Phase 3 halt --------------------
# CLI exits non-zero on a halt; capture but do not abort.
python3 ntp_enricher.py --input tests/fixtures/ntp_mini_implausible.csv \
  --output "$OUT/case2/imp_enriched.csv" --skip-nist-check --non-interactive >/dev/null 2>&1 || true
R2="$OUT/case2/imp_enriched_accuracy_report.json"
python3 - "$R2" <<'PY' || fail "scene2: report assertions"
import json, sys
r = json.load(open(sys.argv[1]))
assert len(r["unresolved_rows"]) >= 1, r["unresolved_rows"]
assert "1000" in r["unresolved_rows"][0]["rejection_basis"], r["unresolved_rows"][0]
PY
pass "scene2: implausible offset surfaces in §4 Phase 3 halt summary"

# --- Scene 3: evidence-integrity guarantee ----------------------------------
SRC=tests/fixtures/ntp_mini.csv
BEFORE="$(sha256sum "$SRC" | awk '{print $1}')"
python3 ntp_enricher.py --input "$SRC" \
  --output "$OUT/case3/ntp_mini_enriched.csv" --skip-nist-check --non-interactive >/dev/null 2>&1
AFTER="$(sha256sum "$SRC" | awk '{print $1}')"
[ "$BEFORE" = "$AFTER" ] || fail "scene3: source CSV was modified"
# Output into a protected evidence root must be rejected (non-zero exit).
if python3 ntp_enricher.py --input "$SRC" --output /cases/should_fail.csv \
     --skip-nist-check --non-interactive >/dev/null 2>&1; then
  fail "scene3: /cases/ output was NOT rejected"
fi
pass "scene3: source CSV unchanged AND /cases/ output rejected"

echo "OK: 3/3 scenes passed"
