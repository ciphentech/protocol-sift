# Deployment Guide

**Protocol:SIFT — NTP Enrichment**

How the generated code gets from the `protocol-sift` repo onto a SANS SIFT
workstation. Development setup lives in [CONTRIBUTING.md](../CONTRIBUTING.md);
the build sequence in [PROMPTS.md](PROMPTS.md); architecture and design
rationale in [ARCHITECTURE.md](ARCHITECTURE.md).

Two repos cooperate:

- **`protocol-sift`** ([ciphentech/protocol-sift](https://github.com/ciphentech/protocol-sift))
  (this repo) — the skill, the Python tools, the hooks, and `install.sh`
  all live here. This is what lands on the SIFT workstation.
- **`hackasans-correlator`** — the authoring and infrastructure repo. Owns
  the AWS Terraform (`infra/terraform/`) and deploy tooling. Hosts no agent
  code and is never deployed.

---

## 1. Primary workflow — SSM session + git + install.sh

This is the team's day-to-day path for the AWS workstation:

```bash
# From your laptop — open a shell on the workstation (SSM only, no SSH)
aws ssm start-session --region $AWS_REGION --target <i-...>

# On the workstation — first time
git clone https://github.com/ciphentech/protocol-sift.git
cd protocol-sift && bash install.sh

# On the workstation — every redeploy after that
cd protocol-sift && git pull && bash install.sh
```

The same two commands (`git pull && bash install.sh`) are the whole story on
a local SIFT VM or any SSH-reachable box. This is also the judges' path:
clone protocol-sift, run `install.sh`.

Audit note: SSM Session Manager logs the interactive session itself, and the
deployed Stop hook (`capture_session.py`) records every Claude Code session
on the box — but the *deploy* is only recorded as your shell history. When
you want a deploy that leaves a verifiable record, use the wrapper below.

---

## 2. What lands on the workstation

After `install.sh` (run directly or via the wrapper):

| Path | Purpose |
|---|---|
| `~/.claude/CLAUDE.md`, `~/.claude/settings.json` | DFIR Orchestrator role, tool routing, evidence-write denies, PreToolUse/PostToolUse/Stop hooks (from `global/`) |
| `~/.claude/skills/<skill>/SKILL.md` | Six skills: the five upstream SIFT skills + `ntp-enrichment` |
| `~/.claude/analysis-scripts/` | Eight files: `generate_pdf_report.py`, `ntp_resolver.py`, `ntp_enricher.py`, `ntp_nist_client.py`, `ntp_manifest.py`, `sift_logger.py`, `sift_s3_sync.py`, `tlcorr_pipeline.sh` (the orchestrator the ntp-enrichment skill names as Primary) |
| `~/.claude/hooks/` | `pretool_block_cases.py` (evidence-write guard), `log_agent_trace.py` (execution trace), `capture_session.py` (session transcript + token usage) |
| `~/.claude/sift.env` | S3 sync variables (edit `SIFT_S3_BUCKET` / credentials before use) |
| crontab entry | `sift_s3_sync.py` every 15 minutes → ships `~/.protocol-sift/` JSONL logs to S3 |
| Plaso (`log2timeline.py`, `psort.py`, `pinfo.py`) | Installed from the GIFT PPA if missing (Ubuntu/SIFT only) |

Evidence paths (`/cases`, `/mnt`, `/media`) are never written to by the
install or by any tool. The guarantee is enforced at three layers: the
enricher's forbidden-path checks, the PreToolUse hook, and the
`settings.json` deny list.

---

## 3. Post-deploy checklist

- [ ] Ubuntu 22.04+ (the SANS-downloadable SIFT image satisfies this)
- [ ] `python3 --version` ≥ 3.10
- [ ] Claude Code CLI installed and `ANTHROPIC_API_KEY` set
- [ ] `bash install.sh` exited 0
- [ ] From the repo checkout: `bash analysis-scripts/tests/verify_deploy.sh`
      prints `OK: 5/5 deploy checks passed` — it reads `~/.claude` only
      (8 analysis scripts, 6 skills, 3 hooks, config, the sync cron entry)
      and is never deployed itself
- [ ] From the repo checkout: `bash analysis-scripts/tests/smoke_ntp_agent.sh`
      prints `OK: 3/3 scenes passed` — or run the full gate with
      `bash analysis-scripts/tests/run_acceptance.sh` →
      `ACCEPTANCE: all checks passed`. The entire test suite lives in the
      repo checkout only; `install.sh` never copies tests or fixtures to
      `~/.claude`, keeping the workstation runtime lean for the other skills
      that share it

Then start a session:

```bash
cd ~/cases/<case-id> && claude
# Ask: "Normalize and enrich this Plaso timeline with NIST-anchored timestamps."
```

Expect either an enriched timeline or a self-correction iteration.

---

## 6. Best practices

- **Never write inside `/cases`, `/mnt`, `/media` from any helper.** All
  outputs land under `./analysis/`, `./exports/`, `./reports/` in the case
  directory.
- **Treat `forensic_audit.log` as append-only.** Do not rotate or truncate
  mid-case; copy it into the case's eventual evidence archive.
- **Always `--dry-run` before the first AWS deploy of a session.** Confirm
  the SSM commands look right before paying for execution.
- **Run the acceptance gate on every PR.** From `protocol-sift/`:
  `bash analysis-scripts/tests/run_acceptance.sh` →
  `ACCEPTANCE: all checks passed` (it aggregates pytest, both smoke suites,
  the install verifier, and the tlcorr pipeline tests). CI runs the same
  command on every push. See [CONTRIBUTING.md](../CONTRIBUTING.md) for the
  full PR checklist and where each test tier runs.
- **Run the acceptance gate on every PR.** From the repo root:
  `bash analysis-scripts/tests/run_acceptance.sh` — CI runs the same command
  on every push. See [CONTRIBUTING.md](../CONTRIBUTING.md) for the full PR
  checklist.
