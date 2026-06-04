#!/usr/bin/env bash
# Minimum-viable install verifier for the NTP enrichment enhancement.
# Five assertions tied to files the build produces. Security: read-only checks.

set -uo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
AS="$(dirname "$HERE")"            # analysis-scripts/
ROOT="$(dirname "$AS")"           # protocol-sift/

ok() { echo "[PASS] $1"; }
no() { echo "[FAIL] $1"; exit 1; }

[ -f "$AS/ntp_resolver.py" ]    && ok "ntp_resolver.py present"    || no "ntp_resolver.py missing"
[ -f "$AS/ntp_enricher.py" ]    && ok "ntp_enricher.py present"    || no "ntp_enricher.py missing"
[ -f "$AS/ntp_nist_client.py" ] && ok "ntp_nist_client.py present" || no "ntp_nist_client.py missing"
[ -f "$AS/ntp_manifest.py" ]    && ok "ntp_manifest.py present"    || no "ntp_manifest.py missing"
grep -q "ntplib" "$ROOT/requirements.txt" && ok "ntplib pinned in requirements.txt" \
  || no "ntplib missing from requirements.txt"

echo "OK: 5/5 checks passed"
