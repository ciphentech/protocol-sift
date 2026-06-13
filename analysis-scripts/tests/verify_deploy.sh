#!/usr/bin/env bash
# Post-deploy verifier for the SIFT workstation: asserts that `bash install.sh`
# actually landed everything under ~/.claude. Run from the repo checkout after
# each deploy — this file is never copied to the workstation runtime tree.
# Security: read-only checks; never writes to $CLAUDE_DIR.
#
# Expected lists below must mirror install.sh's deploy list — update both together.
#
# Test affordances (not for workstation use):
#   CLAUDE_DIR=<path>          verify a staged tree instead of ~/.claude
#   VERIFY_DEPLOY_SKIP_CRON=1  skip the crontab check (no crontab in test envs)

set -uo pipefail
CLAUDE_DIR="${CLAUDE_DIR:-$HOME/.claude}"

ok() { echo "[PASS] $1"; }
no() { echo "[FAIL] $1"; FAILED=1; }
FAILED=0

# 1/5 — analysis scripts (install.sh copy loop)
missing=""
for script in generate_pdf_report.py ntp_resolver.py ntp_enricher.py ntp_nist_client.py ntp_manifest.py sift_logger.py sift_s3_sync.py tlcorr_pipeline.sh; do
    [ -f "$CLAUDE_DIR/analysis-scripts/$script" ] || missing="$missing $script"
done
[ -z "$missing" ] && ok "8/8 analysis scripts deployed" \
    || no "analysis scripts missing from $CLAUDE_DIR/analysis-scripts:$missing"

# 2/5 — skills (install.sh SKILLS array)
missing=""
for skill in memory-analysis plaso-timeline sleuthkit windows-artifacts yara-hunting ntp-enrichment; do
    [ -f "$CLAUDE_DIR/skills/$skill/SKILL.md" ] || missing="$missing $skill"
done
[ -z "$missing" ] && ok "6/6 skills deployed" \
    || no "skills missing SKILL.md under $CLAUDE_DIR/skills:$missing"

# 3/5 — hooks (install.sh global/hooks glob)
missing=""
for hook in pretool_block_cases.py log_agent_trace.py capture_session.py; do
    [ -f "$CLAUDE_DIR/hooks/$hook" ] || missing="$missing $hook"
done
[ -z "$missing" ] && ok "3/3 hooks deployed" \
    || no "hooks missing from $CLAUDE_DIR/hooks:$missing"

# 4/5 — config: sift.env + global config files
missing=""
for cfg in sift.env CLAUDE.md settings.json; do
    [ -f "$CLAUDE_DIR/$cfg" ] || missing="$missing $cfg"
done
[ -z "$missing" ] && ok "config present (sift.env, CLAUDE.md, settings.json)" \
    || no "config missing from $CLAUDE_DIR:$missing"

# 5/5 — S3-sync cron entry (same marker install.sh greps for idempotency)
if [ "${VERIFY_DEPLOY_SKIP_CRON:-0}" = "1" ]; then
    echo "[SKIP] cron check skipped (VERIFY_DEPLOY_SKIP_CRON=1)"
elif crontab -l 2>/dev/null | grep -qF "sift_s3_sync.py"; then
    ok "sift_s3_sync cron entry installed"
else
    no "no sift_s3_sync.py entry in crontab"
fi

if [ "$FAILED" -ne 0 ]; then
    echo "FAIL: deploy incomplete — re-run 'bash install.sh' and check the misses above"
    exit 1
fi
echo "OK: 5/5 deploy checks passed"
