#!/usr/bin/env bash
# One-button acceptance gate for the ntp-enrichment feature.
# Runs the full offline verification stack and exits non-zero on the
# first failure. This is the same command CI runs on every push.
set -euo pipefail
cd "$(dirname "$0")/.."           # -> analysis-scripts/

python3 -m pytest tests/ -q       # unit suite
bash tests/smoke_ntp_agent.sh     # 3 end-to-end smoke scenes
bash tests/verify_install.sh      # install/file-presence checks

echo "ACCEPTANCE: all checks passed"
