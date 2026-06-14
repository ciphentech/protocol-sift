#!/usr/bin/env bash
# record-demo.sh — Reproducible AI-agent demo recording for the hackathon video submission.
#
# Usage:
#   bash scripts/record-demo.sh              # record to demo.cast
#   bash scripts/record-demo.sh --dry-run    # print the demo commands without recording
#
# Output:
#   demo.cast  — asciinema cast file (replay: asciinema play demo.cast)
#   demo.gif   — optional animated GIF (requires: brew install agg)
#                 agg demo.cast demo.gif
#
# What the agent does across three scenes (~4 min total):
#   1. Implausible NTP artifact (1500 s offset) — agent detects, self-correction triggers, halts
#   2. Analyst supplies NTP source hint          — agent enriches cleanly, writes accuracy report
#   3. Analyst requests --skip-ntp bypass        — agent warns (ISC2 chain-of-custody), passes through
#
# Prerequisites:
#   claude CLI installed (https://docs.claude.com/claude-code)
#   ANTHROPIC_API_KEY set in environment
#   ~/.claude/skills/ntp-enrichment/SKILL.md accessible (created by deploy-to-workstation.sh,
#     or symlink ~/.claude → protocol-sift/global manually for dev use)
#   brew install asciinema   (recording)
#   brew install agg         (optional GIF export)

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(dirname "$SCRIPT_DIR")"
PROTOCOL_SIFT_DIR="$(dirname "$REPO_ROOT")/protocol-sift"
DEMO_OUTDIR="/tmp/tlcorr_demo"
CAST_FILE="$REPO_ROOT/demo.cast"

IMPLAUSIBLE_FIXTURE="$PROTOCOL_SIFT_DIR/analysis-scripts/tests/fixtures/test_timeline_implausible.csv"
CLEAN_FIXTURE="$PROTOCOL_SIFT_DIR/analysis-scripts/tests/fixtures/test_timeline.csv"

# Path the agent will use — must be reachable as ~/.claude/analysis-scripts/tlcorr_pipeline.sh
# on a deployed SIFT workstation. For local dev, we use the absolute path in the case CLAUDE.md.
PIPELINE_ABS="$PROTOCOL_SIFT_DIR/analysis-scripts/tlcorr_pipeline.sh"

DRY_RUN=false
SETUP=false
for arg in "$@"; do
    case "$arg" in
        --dry-run) DRY_RUN=true ;;
        --setup)   SETUP=true  ;;
    esac
done

# ── Optional one-time setup: install the NTP skill into ~/.claude/skills/ ─────
if $SETUP; then
    SKILL_SRC="$PROTOCOL_SIFT_DIR/global/skills/ntp-enrichment"
    SKILL_DEST="$HOME/.claude/skills/ntp-enrichment"
    mkdir -p "$HOME/.claude/skills"
    ln -sfn "$SKILL_SRC" "$SKILL_DEST"
    echo "Linked: $SKILL_DEST → $SKILL_SRC"
    echo "Run without --setup to record the demo."
    exit 0
fi

# ── Preflight ─────────────────────────────────────────────────────────────────
_check_prereqs() {
    local ok=true

    command -v claude >/dev/null || {
        echo "ERROR: claude CLI not found." >&2
        echo "       Install: https://docs.claude.com/claude-code" >&2
        ok=false
    }

    [[ -n "${ANTHROPIC_API_KEY:-}" ]] || {
        echo "ERROR: ANTHROPIC_API_KEY is not set." >&2
        echo "       export ANTHROPIC_API_KEY=<your-key>" >&2
        ok=false
    }

    [[ -f "$HOME/.claude/skills/ntp-enrichment/SKILL.md" ]] || {
        echo "ERROR: ~/.claude/skills/ntp-enrichment/SKILL.md not found." >&2
        echo "       Run once to install the skill:" >&2
        echo "       bash scripts/record-demo.sh --setup" >&2
        ok=false
    }

    [[ -f "$IMPLAUSIBLE_FIXTURE" && -f "$CLEAN_FIXTURE" ]] || {
        echo "ERROR: demo fixtures not found under analysis-scripts/tests/fixtures/" >&2
        ok=false
    }

    if ! $DRY_RUN; then
        command -v asciinema >/dev/null || {
            echo "ERROR: asciinema not found. Install: brew install asciinema" >&2
            ok=false
        }
    fi

    $ok || exit 1
}
_check_prereqs

# ── Set up a case directory for each scene ────────────────────────────────────
# Each scene gets its own case dir with:
#   exports/<case>_timeline.csv   — the fixture (read-only input)
#   CLAUDE.md                     — tells the agent the pipeline path and case context
_setup_case() {
    local scene_dir="$1" case_id="$2" fixture="$3" extra_context="${4:-}"
    mkdir -p "$scene_dir/exports"
    cp "$fixture" "$scene_dir/exports/${case_id}_timeline.csv"

    cat > "$scene_dir/CLAUDE.md" << CASEMD
# Case: $case_id

## Pipeline
Run NTP enrichment with:
  bash $PIPELINE_ABS --input exports/${case_id}_timeline.csv --case $case_id --outdir .

## Context
$extra_context

## Evidence constraint
Do not modify any existing file under exports/. The enriched timeline is written to
exports/ as a new file (<case>_correlated.csv — never the same filename as the source).
Analysis reports and audit logs go to ./analysis/.
CASEMD
}

rm -rf "$DEMO_OUTDIR"
_setup_case "$DEMO_OUTDIR/scene1" "demo_implausible" "$IMPLAUSIBLE_FIXTURE" \
    "Incident timeline from WIN-WORKSTATION. No NTP source override — let the agent resolve from artifacts."

_setup_case "$DEMO_OUTDIR/scene2" "demo_enriched" "$CLEAN_FIXTURE" \
    "Analyst has confirmed the NTP source is time.windows.com. Use --ntp-source time.windows.com."

_setup_case "$DEMO_OUTDIR/scene3" "demo_skip" "$CLEAN_FIXTURE" \
    "Analyst requests NTP enrichment be skipped. Use --skip-ntp. Chain-of-custody implications must be documented."

# ── Write demo steps to a temp file ──────────────────────────────────────────
DEMO_STEPS="$(mktemp /tmp/tlcorr_demo_XXXX.sh)"
trap 'rm -f "$DEMO_STEPS"' EXIT

cat > "$DEMO_STEPS" << 'STEPS_EOF'
#!/usr/bin/env bash
set -uo pipefail

_pause() { sleep "${1:-1}"; }
_banner() {
    echo ""
    echo "╔══════════════════════════════════════════════════════════════╗"
    printf  "║  %-62s║\n" "$*"
    echo "╚══════════════════════════════════════════════════════════════╝"
    echo ""
    _pause 1
}
_note() { echo "  ▶ $*"; _pause 1; }

STEPS_EOF

# Inject shell variables into the steps file (not inside single-quoted heredoc)
cat >> "$DEMO_STEPS" << STEPS_VARS
DEMO_OUTDIR="$DEMO_OUTDIR"
STEPS_VARS

cat >> "$DEMO_STEPS" << 'STEPS_BODY'
# ── Scene 1: Implausible NTP artifact ─────────────────────────────────────────
_banner "Protocol SIFT NTP Enrichment Demo"
_note "Three scenes. Each shows the agent reading the skill and running the pipeline."
_pause 2

_banner "Scene 1 of 3 — Implausible NTP artifact"
_note "Case artifact (EID 35) records a 1500 s offset — 25 minutes."
_note "Agent detects, triggers self-correction loop, halts with a clear report."
_pause 2

cd "$DEMO_OUTDIR/scene1"
claude --print \
  "Normalize and enrich the Plaso timeline for case demo_implausible. \
The timeline is at exports/demo_implausible_timeline.csv. \
Resolve the NTP source from case artifacts."
_pause 3

# ── Scene 2: Analyst-supplied NTP source, clean run ───────────────────────────
_banner "Scene 2 of 3 — Analyst-supplied NTP source"
_note "Analyst has confirmed the NTP source. Agent enriches cleanly:"
_note "NIST query → enrichment → accuracy report."
_pause 2

cd "$DEMO_OUTDIR/scene2"
claude --print \
  "Normalize and enrich the Plaso timeline for case demo_enriched. \
The timeline is at exports/demo_enriched_timeline.csv. \
The analyst has confirmed the NTP source is time.windows.com."
_pause 3

# ── Scene 3: --skip-ntp bypass ────────────────────────────────────────────────
_banner "Scene 3 of 3 — Chain-of-custody bypass"
_note "Analyst requests NTP enrichment be skipped."
_note "Agent emits the ISC2 chain-of-custody warning before proceeding."
_pause 2

cd "$DEMO_OUTDIR/scene3"
claude --print \
  "Normalize the Plaso timeline for case demo_skip. \
The timeline is at exports/demo_skip_timeline.csv. \
Skip NTP enrichment — I understand the output will not be NIST-anchored."
_pause 3

# ── Wrap-up ───────────────────────────────────────────────────────────────────
_banner "Demo complete"
echo "  Scene 1 (implausible) : $DEMO_OUTDIR/scene1/analysis/"
echo "  Scene 2 (enriched)    : $DEMO_OUTDIR/scene2/exports/demo_enriched_correlated.csv"
echo "  Scene 3 (skip-ntp)    : $DEMO_OUTDIR/scene3/exports/demo_skip_correlated.csv"
_pause 2
STEPS_BODY

chmod +x "$DEMO_STEPS"

# ── Dry-run: just print the steps ─────────────────────────────────────────────
if $DRY_RUN; then
    echo "=== DRY RUN — demo steps (would be recorded to $CAST_FILE) ==="
    echo ""
    cat "$DEMO_STEPS"
    echo ""
    echo "Case directories that would be created:"
    echo "  $DEMO_OUTDIR/scene{1,2,3}/"
    exit 0
fi

# ── Record ────────────────────────────────────────────────────────────────────
echo "Recording to: $CAST_FILE"
echo "Scenes: implausible-offset  →  analyst-supplied source  →  skip-ntp bypass"
echo ""

asciinema rec \
    --title "Protocol SIFT NTP Enrichment" \
    --idle-time-limit 3 \
    --command "bash $DEMO_STEPS" \
    "$CAST_FILE"

echo ""
echo "Recorded : $CAST_FILE"
echo "Replay   : asciinema play $CAST_FILE"
echo "To GIF   : agg $CAST_FILE demo.gif   (brew install agg)"
