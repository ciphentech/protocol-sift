# Development and Deployment Guide

**Protocol:SIFT Timeline Correlator (v2)**

**Version:** 2.0
**Last Updated:** May 2026

## Overview

How to develop the v2 Timeline Correlator on macOS and deploy it to a SANS SIFT Workstation — either a local Ubuntu VM (downloadable from SANS) or a remote SSH-reachable VM.

**v2 architecture is intentionally minimal:** a documentation-only Claude Code skill plus a handful of Python stdlib helpers and a vanilla-JS air-gap-safe viewer. No MCP server. No Python package. No container runtime on the workstation. The full design lives at [`docs/MVP_PLAN.md`](MVP_PLAN.md) and the build sequence at [`docs/prompts/`](prompts/README.md).

The **`protocol-sift`** repo ([ciphentech/protocol-sift](https://github.com/ciphentech/protocol-sift)) is the Claude Code configuration repo. It contains all skills, analysis scripts, and global config. This is what lives on the SIFT workstation — cloned and installed via `bash install.sh`.

---

## Architecture

- **Development machines:** Any machine with `git`, `python3`, and a terminal.
- **Target runtime:** SANS SIFT Workstation (Ubuntu 22.04+), in one of two modes:
  1. Local VM (downloadable OVA from SANS).
  2. Remote SSH-reachable VM.
- **Strategy:** develop in `protocol-sift` → smoke-test → deploy with `install.sh`.

**Hard constraints (from `global/CLAUDE.md`):**
- Python 3 stdlib only by default. `stix2` is opt-in.
- Air-gap safe — vendored STIX bundle, viewer with zero CDN imports.
- Evidence is read-only. Helpers write only under `./analysis/`, `./exports/`, `./reports/`.

---

## 1. Development setup

Install once:

```bash
# Core
brew install git gh        # macOS
# or: sudo apt-get install git gh   # Ubuntu/Debian
```

Clone the repo:

```bash
git clone https://github.com/ciphentech/protocol-sift.git
cd protocol-sift
```

Install Python dependencies (NTP enrichment feature):

```bash
pip3 install -r requirements.txt
```

Install [Claude Code](https://docs.claude.com/claude-code) and set `ANTHROPIC_API_KEY` if you intend to run the agent locally against the smoke fixture.

---

## 2. Local testing

Each pipeline stage is a standalone Python script. Run them directly against the synthetic fixture:

```bash
cd protocol-sift
python3 analysis-scripts/tlcorr_attck_lookup.py \
    --bundle analysis-scripts/tests/fixtures/mini_attck_bundle.json \
    --rules  analysis-scripts/tlcorr_rules/attck_rules.json \
    --query  "powershell -enc JABz..." --parser winevtx
```

End-to-end smoke test:

```bash
bash analysis-scripts/tests/smoke_tlcorr.sh
# expect 10 PASS lines, exit 0, wall time < 30s
```

**Ubuntu-equivalent smoke without provisioning a VM** (catches Ubuntu-only issues before deployment):

```bash
podman run --rm -v "$(pwd):/workspace" -w /workspace ubuntu:22.04 bash -lc "
  apt-get update -qq && apt-get install -y -qq python3 git curl &&
  bash analysis-scripts/tests/smoke_tlcorr.sh
"
```

Podman is optional and used only here — it is **not** required on the SIFT workstation.

---

## 3. Deployment

### 3a. Local SIFT VM (in-place)

You are sitting at the SIFT VM (or a shell on the same host):

```bash
cd /path/to/protocol-sift
bash install.sh
```

This copies skills and analysis scripts to `~/.claude/`, installs Python dependencies, and writes `~/.protocol-sift.env`.

### 3b. Remote SSH-reachable SIFT

You have a SIFT VM elsewhere and SSH key trust is set up:

```bash
# Copy the repo to the remote workstation and run install
rsync -a --delete /path/to/protocol-sift/ analyst@sift.lab:/opt/protocol-sift/
ssh analyst@sift.lab "cd /opt/protocol-sift && bash install.sh"
```

### After a successful install

```bash
source ~/.protocol-sift.env && cd ~/cases/<case-id> && claude
```

In the `claude` session, ask:

> Map this Plaso timeline to MITRE ATT&CK techniques.

Expect narrated `[tlcorr] stage X/5 ...` banners, a manifest with `rubric_pass`, and either a viewer launch or a self-correction iteration.

---

## 4. What lands on the SIFT workstation

After `bash install.sh`:

| Path | Purpose |
|---|---|
| `~/.claude/skills/timeline-correlator/SKILL.md` | v2 skill (documentation only — no .py / .sh inside) |
| `~/.claude/skills/{memory-analysis,ntp-enrichment,plaso-timeline,sleuthkit,windows-artifacts,yara-hunting}/` | All skills |
| `~/.claude/analysis-scripts/tlcorr_*.py` | Stdlib helpers: filter, annotate-source, dedupe, attck-lookup, map, export, capture-session |
| `~/.claude/analysis-scripts/tlcorr_pipeline.sh` | One-command orchestrator |
| `~/.claude/analysis-scripts/tlcorr_viewer/` | Air-gap-safe vanilla-JS viewer + launch.sh |
| `~/.claude/analysis-scripts/tlcorr_rules/` | Editable noise patterns, source categories, ATT&CK rules, coverage rubric |
| `~/.claude/analysis-scripts/ntp_resolver.py` | NTP source resolution tool |
| `~/.claude/analysis-scripts/ntp_enricher.py` | NTP field computation + safe writer |
| `~/.claude/knowledge-bases/attck/enterprise-attack.json` | Vendored MITRE STIX 2.1 bundle (if `--with-attck-bundle` succeeded; install still completes on no-internet hosts) |
| `~/.claude/global/CLAUDE.md` | Principal DFIR Orchestrator + Tool Routing table |
| `~/.claude/global/settings.json` | Permissions + extended `Stop` hook (writes session JSONL + `token_usage.json`) |
| `~/.protocol-sift.env` | Sourced by interactive shells; sets `CORRELATOR_RUNTIME`, `ATTACK_MCP_MODE=local`, `PYTHONPATH` |

Evidence paths (`/cases`, `/mnt`, `/media`) are never written to by the install or by any pipeline stage. The architectural guarantee is enforced by both the helpers (refuse to write outside `./analysis/`, `./exports/`, `./reports/`) and by `global/settings.json`'s permission deny list at the Claude Code layer.

---

## 5. Per-case directory layout

Cases live in `~/cases/<case-id>` (or `/cases/<case-id>` per SIFT convention). After running the pipeline:

```
~/cases/<case-id>/
├── exports/
│   ├── <case>_timeline.csv               # Your psort -o l2tcsv output (input)
│   ├── <case>_timeline_enriched.csv      # NTP-enriched timeline
│   ├── <case>_correlated.csv             # ATT&CK-correlated output
│   └── correlated/correlated.json        # Viewer reads this
├── analysis/
│   ├── <case>_ntp_manifest.json          # NTP enrichment manifest (rubric_pass)
│   ├── <case>_ntp_manifest.iterN.json    # Self-correction iterations (preserved)
│   ├── <case>_ntp_caveats.txt            # Assumption flags for legal review
│   ├── <case>_tlcorr_manifest.iter1.json # ATT&CK correlation manifest
│   ├── <case>_tlcorr_manifest.iter2.json # Present only if iter1 failed rubric
│   ├── <case>_session_<id>.jsonl         # Full agent transcript
│   ├── <case>_token_usage.json           # Per-model usage + USD estimate
│   └── forensic_audit.log               # UTC-stamped append-only audit
└── reports/                              # PDF reports when generated
```

---

## 6. Checklist

### SIFT workstation

- [ ] Ubuntu 22.04+ (the SANS-downloadable SIFT image satisfies this)
- [ ] `python3` (3.10+; built into SIFT — verify with `python3 --version`)
- [ ] Claude Code CLI + `ANTHROPIC_API_KEY`
- [ ] `bash install.sh` exited 0
- [ ] `bash ~/.claude/analysis-scripts/tests/smoke_tlcorr.sh` exits 0 with 10 PASS lines
- [ ] `~/.claude/skills/timeline-correlator/SKILL.md` exists
- [ ] `~/.claude/knowledge-bases/attck/enterprise-attack.json` exists (if install had network)

---

## 7. Useful one-liners

```bash
# Verify what's deployed
ls -la ~/.claude/skills/ ~/.claude/analysis-scripts/

# Refresh the STIX bundle (e.g., quarterly)
mkdir -p ~/.claude/knowledge-bases/attck && \
curl -fsSL --max-time 30 \
  https://raw.githubusercontent.com/mitre/cti/master/enterprise-attack/enterprise-attack.json \
  -o ~/.claude/knowledge-bases/attck/enterprise-attack.json

# Run the viewer for a finished case
bash ~/.claude/analysis-scripts/tlcorr_viewer/launch.sh \
  --port 8765 --dir ~/cases/<case-id>/exports/correlated

# Tail the forensic audit
tail -F ~/cases/<case-id>/analysis/forensic_audit.log

# Run NTP enrichment smoke test
bash ~/.claude/analysis-scripts/tests/smoke_ntp_agent.sh

# Verify install
bash ~/.claude/analysis-scripts/tests/verify_install.sh
```

---

## 8. Best practices

- **Never write inside `/cases`, `/mnt`, `/media` from any helper.** All outputs land under `./analysis/`, `./exports/`, `./reports/` in the case directory. The smoke harness asserts a sha256 spoliation check before/after every run.
- **Keep `tlcorr_rules/*.json` under version control.** They are the operator-tunable knobs — noise patterns, source categories, ATT&CK rules, coverage rubric — and any change should be code-reviewed like a Python diff.
- **Treat `forensic_audit.log` as append-only.** Do not rotate or truncate mid-case; copy it into the case's eventual evidence archive.
- **The vendored STIX bundle is the source of truth.** It is not a live API. Refresh quarterly via `install.sh --with-attck-bundle`.
- **Run the smoke harness on every PR to `feature/timeline-correlator`.** A passing smoke is the v2 equivalent of a green CI build. See `MVP_PLAN.md` §4 Definition of Done.

---

## 9. What changed from v1

This v2 document replaces the v1 deployment guide (preserved in git history). The substantive changes:

| v1 | v2 | Why |
|---|---|---|
| Podman / containers required on the SIFT workstation to host an ATT&CK MCP server | No container runtime needed on the workstation | v1's MCP server is replaced by a vendored STIX 2.1 JSON bundle + a stdlib query module. Simpler, air-gap-native. |
| No Python dependencies | `requirements.txt` with `pytest`, `pandas`, `ntplib` | NTP enrichment feature requires these packages |
| `install.sh --offline` flag | `install.sh --with-attck-bundle` (opposite default — air-gap is the default; the flag *fetches* the bundle when internet is available) | Aligns with SIFT's air-gap-first posture |
| `just` / justfile + Black + Ruff | None | Never adopted; v2 is stdlib + bash |
| MCP server health-check loop | n/a | No MCP server |

See [`docs/MVP_PLAN.md`](MVP_PLAN.md) for the 4-week build plan and [`docs/prompts/README.md`](prompts/README.md) for the 12-prompt build sequence.
