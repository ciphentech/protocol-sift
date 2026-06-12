#!/usr/bin/env bash
# One-button acceptance gate for Protocol SIFT.
# Runs the full offline verification stack and exits non-zero on the
# first failure. This is the same command CI runs on every push.
set -euo pipefail
cd "$(dirname "$0")/.."           # -> analysis-scripts/

python3 -m pytest tests/ -q           # unit suite
bash tests/smoke_ntp_agent.sh         # NTP enrichment: 3 end-to-end scenes
bash tests/verify_install.sh          # install/file-presence checks
bash tests/smoke_protocol_sift.sh     # full smoke: NIST, log files, token usage, plaso
python3 tests/smoke_test.py --offline # tlcorr pipeline T-01..T-08 (live-NTP cases skipped)

echo "ACCEPTANCE: all checks passed"
