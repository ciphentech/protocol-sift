# Contributing to Protocol SIFT

Protocol SIFT is a DFIR orchestrator built on Claude Code for the SANS SIFT Workstation. Contributions follow a **skill-first, test-gated** workflow: the agent's reasoning instructions (`SKILL.md`) and specs come before implementation, and every change must pass the smoke test before merging.

---

## Table of Contents

- [Repository layout](#repository-layout)
- [Development setup](#development-setup)
- [Running the tests](#running-the-tests)
- [Change workflow](#change-workflow)
- [Branch naming](#branch-naming)
- [PR checklist](#pr-checklist)
- [Evidence integrity rules](#evidence-integrity-rules)
- [Key files](#key-files)

---

## Repository layout

```
protocol-sift/
├── analysis-scripts/       # Python tools the agent invokes via Bash()
│   ├── ntp_enricher.py     # Main NTP enrichment pipeline
│   ├── ntp_nist_client.py  # NIST time server queries
│   ├── ntp_resolver.py     # NTP source resolution (6-level confidence tree)
│   ├── ntp_manifest.py     # Accuracy report writer
│   ├── sift_logger.py      # JSONL audit logging for every skill run
│   ├── sift_s3_sync.py     # Cron-driven S3 sync for audit logs
│   ├── tlcorr_pipeline.sh  # Pipeline orchestrator (ingest → enrich → verify → report)
│   └── tests/              # Smoke test, unit tests, acceptance suite, fixtures
├── global/
│   ├── CLAUDE.md           # Global agent config (DFIR role, tool routing)
│   ├── settings.json       # Permissions, hooks (PreToolUse, PostToolUse, Stop)
│   └── hooks/              # log_agent_trace.py, capture_session.py
├── skills/                 # Agent reasoning instructions (SKILL.md per domain)
│   ├── ntp-enrichment/
│   ├── plaso-timeline/
│   ├── memory-analysis/
│   ├── sleuthkit/
│   ├── windows-artifacts/
│   └── yara-hunting/
├── docs/                   # Project documentation (you are here)
├── install.sh              # SIFT workstation installer
├── sift.env.template       # S3 env var template (copy to ~/.claude/sift.env)
└── requirements.txt        # Python dependencies
```

---

## Development setup

### Requirements

- Ubuntu 22.04+ or macOS (for local testing)
- Python 3.10+
- `pip3 install -r requirements.txt`
- Claude Code CLI (`claude`) with a valid `ANTHROPIC_API_KEY`

### Install locally

```bash
git clone https://github.com/ciphentech/protocol-sift.git
cd protocol-sift
pip3 install -r requirements.txt
```

For a full SIFT workstation install (deploys to `~/.claude/`):

```bash
bash install.sh
```

### Environment variables for testing

The test suite uses env vars to redirect output away from production paths:

| Variable | Default | Purpose |
|----------|---------|---------|
| `SIFT_LOGS_DIR` | `~/.protocol-sift` | JSONL audit log directory |
| `SIFT_PROJECTS_DIR` | `~/.claude/projects` | Claude session source for token capture |
| `SIFT_ANALYSIS_DIR` | `./analysis` | Token usage report output |
| `PLASO_FIXTURE` | `/cases/rd01/analysis/rd01-system-evtx.plaso` | Plaso file for Scene 8 on SIFT |
| `PLASO_SLICE` | `2018-05-04T22:14:29` | `--slice` timestamp for Scene 8 |

---

## Running the tests

### Smoke test (full end-to-end, all platforms)

```bash
bash analysis-scripts/tests/smoke_protocol_sift.sh
```

Covers 9 scenes: install completeness, NIST reachability, sift_logger JSONL, token usage, NTP enrichment (offline + live), evidence integrity, Plaso tool availability, and S3 sync dry-run. Plaso scenes skip gracefully in CI.

### Python unit tests

```bash
pytest analysis-scripts/tests/ -v
```

### Acceptance suite

```bash
bash analysis-scripts/tests/run_acceptance.sh
```

Runs the 3-scene acceptance test against synthetic fixtures plus the install-completeness and NTP dependency checks.

### All tests must pass before opening a PR.

---

## Change workflow

### 1. Skill changes (`SKILL.md`)

The `SKILL.md` files are the agent's **executable reasoning instructions** — not documentation. Before changing one:

- Open [docs/SPEC.md](SPEC.md) and confirm the change is in scope.
- Update `SKILL.md` first. The Python tools implement what the skill instructs.
- If the change affects agent behaviour (new phase, new output field, new guard), update the spec section first.

### 2. Python tool changes (`analysis-scripts/`)

- Add or update a unit test in `analysis-scripts/tests/` before touching the tool.
- Run `pytest` to confirm the test fails (red), then implement and make it pass (green).
- Run the smoke test to confirm no regressions across the full pipeline.

### 3. Hook and settings changes (`global/`)

- Changes to `settings.json` (permissions, hooks) affect every Claude Code session on the SIFT workstation. Test locally before opening a PR.
- Hook scripts (`log_agent_trace.py`, `capture_session.py`) must never crash the session — all exceptions must be caught and printed to stderr.

### 4. Installer changes (`install.sh`)

- Test on a fresh Ubuntu 22.04 VM or a clean `~/.claude/` directory.
- Confirm `install.sh` is idempotent — running it twice must not break anything.

---

## Branch naming

| Type | Pattern | Example |
|------|---------|---------|
| Bug fix | `fix/<short-description>` | `fix/capture-session-import-os` |
| Feature | `feat/<short-description>` | `feat/s3-sync-cron` |
| Documentation | `docs/<short-description>` | `docs/add-contributing` |
| Test | `tests/<short-description>` | `tests/smoke-plaso-scene8` |
| Chore | `chore/<short-description>` | `chore/remove-demo-scripts` |

---

## PR checklist

Before requesting review, confirm:

- [ ] `bash analysis-scripts/tests/smoke_protocol_sift.sh` passes (all scenes, or skipped gracefully)
- [ ] `pytest analysis-scripts/tests/ -v` passes
- [ ] `bash analysis-scripts/tests/run_acceptance.sh` passes
- [ ] No writes to `/cases/`, `/mnt/`, or `/media/` — evidence paths are read-only
- [ ] New or changed Python scripts have at least one unit test
- [ ] Hook scripts catch all exceptions and never exit non-zero (non-fatal errors only)
- [ ] `sift.env` and `*.env` files are not committed (gitignored — put credentials in `~/.claude/sift.env`)
- [ ] PR description explains the root cause (for fixes) or the use case (for features)

---

## Evidence integrity rules

These are non-negotiable and enforced at multiple levels:

1. **Never write to evidence paths** — `/cases/`, `/mnt/`, `/media/`, or any `evidence/` directory. The `settings.json` `deny` list enforces this at the permission layer; `ntp_enricher.py` raises `ValueError("protected evidence")` at the code layer.
2. **Output routing** — all scripts, CSVs, JSON, and reports go to `./analysis/`, `./exports/`, or `./reports/` relative to the case working directory.
3. **Timestamps** — always UTC. Use `datetime.now(timezone.utc).isoformat()`.
4. **SHA-256 integrity** — `tlcorr_pipeline.sh` re-hashes the input CSV after enrichment and aborts if it changed. Do not break this check.
5. **Audit logging** — every skill run must produce a JSONL audit log via `SiftSession` from `sift_logger.py`. Do not remove or bypass this.

---

## Key files

| File | What to know |
|------|-------------|
| `skills/ntp-enrichment/SKILL.md` | The NTP enrichment agent instructions — the most important file in this repo |
| `global/CLAUDE.md` | Agent role, forensic constraints, tool routing table |
| `global/settings.json` | All permissions and hooks — changes here affect every session |
| `analysis-scripts/ntp_enricher.py` | Core enrichment pipeline — evidence integrity guard lives here |
| `analysis-scripts/sift_logger.py` | Audit logging — `SIFT_LOGS_DIR` env var for test isolation |
| `scripts/hooks/capture_session.py` | Stop hook — reads `~/.claude/projects/` for token usage; `SIFT_PROJECTS_DIR` / `SIFT_ANALYSIS_DIR` for test isolation |
| `install.sh` | SIFT workstation installer — must be idempotent and tested on a clean system |
| `sift.env.template` | S3 env var template — copy to `~/.claude/sift.env`, never commit the populated version |

---

## Questions

Open an issue on [GitHub](https://github.com/ciphentech/protocol-sift/issues) or reach the team via the SANS FindEvil Hackathon submission page.
