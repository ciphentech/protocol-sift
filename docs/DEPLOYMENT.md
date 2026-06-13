# Deployment Guide

**Protocol:SIFT — NTP Enrichment**

How the generated code gets from the `protocol-sift` repo onto a SANS SIFT
workstation. Development setup lives in [CONTRIBUTING.md](../CONTRIBUTING.md);
the build sequence in [PROMPTS.md](PROMPTS.md); architecture and design
rationale in [ARCHITECTURE.md](ARCHITECTURE.md).

Two repos cooperate:

- **`protocol-sift`** ([ciphentech/protocol-sift](https://github.com/ciphentech/protocol-sift))
  — the code repo. The skill, the Python tools, the hooks, and `install.sh`
  all live here (generated from this repo's prompt series). This is what
  lands on the SIFT workstation.
- **`hackasans-correlator`** (this repo) — the authoring and infrastructure
  repo. Owns the AWS Terraform (`infra/terraform/`) and the optional deploy
  wrapper `scripts/deploy-to-workstation.sh`. Hosts no agent code and is
  never deployed.

---

## 1. How `deploy-to-workstation.sh` relates to `install.sh`

They are two layers, not two alternatives doing the same job:

- **`install.sh`** (in protocol-sift, authored by prompt P-10) is the **only
  deploy entry point**. Run *on* the workstation, it copies the six skills
  and seven analysis scripts into `~/.claude/`, ships the three
  `global/hooks/` scripts, installs Plaso (GIFT PPA) and the Python
  dependencies, stages `sift.env`, and installs the S3-sync cron job. It is
  idempotent — safe to re-run after every `git pull`.
- **`scripts/deploy-to-workstation.sh`** (in this repo) is an **optional
  remote-delivery wrapper around `install.sh`**. It never replaces the
  install logic; it only transports the repo to a machine you are not
  sitting at and runs `install.sh` there — over rsync/SSH for a lab VM, or
  over S3 + `aws ssm send-command` for the AWS workstation (which is
  SSM-only, no SSH). Its value is the **audit trail**: a deterministic
  deployment bundle staged to S3, SSM command IDs, and CloudWatch logs of
  the run — plus `--dry-run` to print every command without executing.

Rule of thumb: on the box → `install.sh` directly. Pushing to a box from
your laptop and you want the deploy recorded → the wrapper.

---

## 2. Primary workflow — SSM session + git + install.sh

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

## 3. Audited alternative — `deploy-to-workstation.sh`

All three modes are driven by
[`scripts/deploy-to-workstation.sh`](../scripts/deploy-to-workstation.sh).
The script is idempotent, supports `--dry-run`, and tolerates missing
artifacts (clear `WARN:` lines, then continues).

```bash
# Local (you are on the SIFT box or the same host)
bash scripts/deploy-to-workstation.sh --target local

# Remote SSH-reachable SIFT VM
bash scripts/deploy-to-workstation.sh --target local --host analyst@sift.lab

# AWS workstation (reads instance id + region from terraform output)
bash scripts/deploy-to-workstation.sh --target aws

# Always available — print every command without executing
bash scripts/deploy-to-workstation.sh --target aws --dry-run
```

The AWS path uploads a deployment bundle to the staging S3 bucket, runs
`install.sh` via `aws ssm send-command`, and tails CloudWatch Logs until the
command finishes. Always `--dry-run` before the first real AWS deploy of a
session to confirm the bucket, instance id, and region resolve as expected.

---

## 4. What lands on the workstation

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

## 5. Post-deploy checklist

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

Expect either an enriched timeline or a self-correction iteration — see the
demo storyboard in [docs/demo/ntp-enrichment-self-correction.md](demo/ntp-enrichment-self-correction.md)
(staged with `scripts/stage_self_correct_case.sh`, both in this repo).

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
- **Policy-sync pre-commit hook (planned, nice-to-have — not yet built).**
  The idea: keep the secure-coding policy in
  [`hackasans-correlator/CLAUDE.md`](../CLAUDE.md) byte-for-byte in sync
  with an overlay in `protocol-sift/global/CLAUDE.md`, enforced by a
  `scripts/check_security_policy_sync.py` pre-commit hook installed via
  `bash scripts/install-git-hooks.sh`. None of the three pieces exists yet
  (no overlay section in the global CLAUDE.md, no checker, no installer) —
  until they do, keep the two policies aligned manually when editing either
  file.
