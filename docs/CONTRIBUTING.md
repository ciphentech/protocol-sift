# Contributing to Hackasans Correlator

This repository supports both local laptop development and AWS-hosted SIFT workstation deployment. The codebase is Python 3.11+, and the project is organized so the same source tree can be used for both local development and cloud infrastructure.

This is the **authoring repo**: it holds the design docs, the build-prompt series, and the AWS infrastructure. The generated NTP-enrichment code, its tests, and the deployable `install.sh` live in the sibling **`protocol-sift`** checkout (`../protocol-sift`, the ciphentech fork of teamdfir/protocol-sift) — never as a subdirectory or submodule of this repo.

## Prerequisites

- Python 3.11+
- Git
- AWS CLI configured for AWS deployment
- Terraform 1.6+ for AWS infrastructure
- `.env` configured from `.env.example`

## Local development

1. Clone the repository:
   ```bash
   git clone https://github.com/ciphentech/hackasans-correlator.git
   cd hackasans-correlator
   ```

2. Create and activate a virtual environment:
   ```bash
   bash scripts/setup-macos.sh
   source .venv/bin/activate
   ```

3. If needed, install dependencies manually:
   ```bash
   python3 -m pip install -r requirements.txt
   cp .env.example .env
   ```

4. Update `.env` with your Anthropic API key and any local configuration values.

## AWS-hosted SIFT workstation

1. Deploy the AWS infrastructure:
   ```bash
   cd infra/terraform
   cp terraform.tfvars.example terraform.tfvars
   ```

2. Edit `terraform.tfvars` to set your operator IP CIDR, SSH public key, and other required values.

3. Run Terraform:
   ```bash
   terraform init
   terraform plan
   terraform apply
   ```

4. Upload evidence to the evidence bucket using the upload utility.

## Testing

The NTP-enrichment test suite lives in the sibling `protocol-sift` repo:

```bash
cd ../protocol-sift/analysis-scripts
python3 -m pytest tests/ -v            # expect 69 passed
bash tests/smoke_ntp_agent.sh          # expect "OK: 3/3 scenes passed"
```

The tlcorr pipeline smoke suite (`tests/smoke_test.py`, T-01…T-08) lives
there too and runs in protocol-sift's CI via `tests/run_acceptance.sh`;
this repo carries no tests of its own.

### Where tests run

Three tiers, in order of authority — full detail and maintenance rules in
[docs/TEST-STRATEGY.md](docs/TEST-STRATEGY.md):

1. **CI is the primary gate.** protocol-sift's GitHub Actions workflow runs
   `bash analysis-scripts/tests/run_acceptance.sh` on every push/PR touching
   `analysis-scripts/**`, `skills/**`, or `global/hooks/**`. Expect
   `ACCEPTANCE: all checks passed`.
2. **The repo suite runs on demand from any checkout** — laptop or the SIFT
   workstation's `protocol-sift` checkout. Same command; add
   `python3 tests/smoke_test.py` *without* `--offline` when you want live-NTP
   proof.
3. **Nothing test-related deploys to the workstation.** `install.sh` copies
   runtime files only — no test files or fixtures ever land in `~/.claude`.
   After each deploy, run `bash analysis-scripts/tests/verify_deploy.sh` from
   the checkout (it only *reads* `~/.claude`; expect
   `OK: 5/5 deploy checks passed`).

Key rules: `run_acceptance.sh` is the single test registry; tests ride in the
same PR as the code they cover; direct protocol-sift changes — tests included —
get a `/ntp-prompt-sync` follow-up with green counts recomputed. protocol-sift
ships a post-commit reminder for that last rule: run
`bash scripts/install-git-hooks.sh` once per checkout there.

### Before opening a PR

1. **Smoke test passes** — run from `protocol-sift/`:
   ```bash
   bash analysis-scripts/tests/smoke_ntp_agent.sh   # expect "OK: 3/3 scenes passed", exit 0
   ```
2. **Unit tests pass** — run from `protocol-sift/analysis-scripts/`:
   ```bash
   python3 -m pytest tests/ -v   # expect 69 passed
   ```
3. **No secrets in diff** — SOPS-encrypted files in `infra/` are the source of truth; never commit plaintext keys or tokens.

### Manual spot-checks

These checks exercise code paths that the automated suite doesn't reach (interactive
stdin, no-network scenarios). Run them from the `protocol-sift` directory on a
developer MacBook — they require a TTY and outbound internet.

**Interactive resolver prompt (no EID 35/260 in timeline)**

When `ntp_resolver.py` finds no EID 35 or 260 rows it falls back to asking the
analyst for the NTP source interactively. To see this path:

```bash
# 1. Create a CSV with no EID 35/260 markers (EventID 37 plain text):
cat > /tmp/ntp_no_eid.csv << 'EOF'
date,time,timezone,MACB,source,sourcetype,type,user,host,short,desc,version,filename,inode,notes,format,extra
05/04/2018,22:14:29,UTC,.....,EVT,WinEvtx,Content Modification Time,N/A,rd01,NTP sync event,EventID: 37 The time service is now synchronizing the system time with the time source.,2,C:\Windows\System32\winevt\Logs\System.evtx,N/A,,WinEvtx,
EOF

# 2. Run the enricher directly (must be a real TTY — not a subprocess):
.venv/bin/python3 analysis-scripts/ntp_enricher.py \
  --input /tmp/ntp_no_eid.csv \
  --output /tmp/ntp_no_eid_out.csv \
  --case-dir /tmp
```

Expected: the resolver prints its Phase 1/2 question and waits for input. Type an
NTP hostname (e.g. `pool.ntp.org`) and press Enter — enrichment completes and the
output CSV is written. This path is not exercised by `pytest` or the smoke suite
because both run the enricher as a subprocess without a TTY.

## Code style

- Format code with `black`
- Lint with `flake8`
- Keep pull requests small and focused
- Add tests for new features and bug fixes

Follow [docs/CLAUDE.md](docs/CLAUDE.md) (general LLM-coding rules) and
[CLAUDE.md](CLAUDE.md) (secure coding requirements and project guardrails).
Key points:

- Surgical changes only — touch what the task requires, nothing else.
- Evidence paths (`/cases`, `/mnt`, `/media`) are read-only; writes go to `./analysis/`, `./exports/`, `./reports/` only.
- IAM additions in `infra/terraform/` must be least-privilege — no `*` wildcards.
- Hook scripts must never crash a Claude Code session — always emit `{"continue": true}`.

## Workflow

- Branch from `main`
- Open pull requests against `main`
- Include a summary of changes and test results in PR descriptions
- Branch naming:

| Work type | Pattern |
|-----------|---------|
| New feature | `feature/<short-description>` |
| Bug fix | `fix/<short-description>` |
| Docs only | `docs/<short-description>` |
| Infrastructure | `infra/<short-description>` |

**Prompts and design docs first.** The prompt series in
[docs/prompts/](docs/prompts/) and the design docs (`SPEC.md`, `FEATURES.md`,
`ARCHITECTURE.md`) are the source of truth for the ntp-enrichment feature;
the code in the sibling `protocol-sift` repo is generated from them. Prefer
making changes by editing the relevant prompt or design doc here, then
regenerating/applying the change in `protocol-sift` via the
`/ntp-enrichment-generator` skill (or by executing the edited prompt's step) —
this keeps the build recipe reproducible by construction. If you must change
code directly in
`protocol-sift` (hotfix, test gap, upstream merge), propagate it back into the
prompt series with the **`/ntp-prompt-sync`** skill
([.claude/skills/ntp-prompt-sync/SKILL.md](.claude/skills/ntp-prompt-sync/SKILL.md)).
It carries the file→prompt ownership map, regenerates verbatim listings from
the actual files, and recomputes the hard green-count milestones with pytest.
Run `/ntp-prompt-sync audit` first for a read-only drift table.

A code change that never lands back in the prompts is a defect: a fresh build
no longer reproduces the real code, and `/ntp-enrichment-generator status`
reports false FAILs.

## Repository structure

- `docs/` — design docs (`SPEC.md`, `FEATURES.md`, `ARCHITECTURE.md`), deployment, and contributor documentation
- `docs/prompts/` — the build-prompt series (P-Scaffold, P-00 … P-10), indexed by `docs/PROMPTS.md` — source of truth for the ntp-enrichment feature
- `.claude/` — project settings and skills (`ntp-enrichment-generator`, `ntp-prompt-sync`)
- `infra/` — Terraform for the AWS-hosted SIFT workstation (Cognito, EC2, IAM, monitoring) and S3 configuration
- `terraform/bootstrap/` — Terraform remote-state and GitHub OIDC bootstrap
- `scripts/` — local environment bootstrap (`setup-macos.sh`), workstation deploy (`deploy-to-workstation.sh`), demo recording, dataset download
- `.github/workflows/` — CI pipelines
- `../protocol-sift` (sibling checkout) — generated NTP code, the `tlcorr_pipeline.sh` orchestrator, tests, skills, hooks, and `install.sh`

## PR checklist

- [ ] Smoke test passes (`smoke_ntp_agent.sh`, 3/3 scenes)
- [ ] Unit tests pass (`pytest tests/`, 69 passed)
- [ ] Prompt series synced if `protocol-sift` code changed (`/ntp-prompt-sync`)
- [ ] No new plaintext secrets
- [ ] Deployment doc updated if install paths or script names changed
- [ ] `--dry-run` verified if the PR touches `scripts/deploy-to-workstation.sh`

## Notes

- `README.md` is the primary user-facing quick start.
- `CONTRIBUTING.md` (this file) is the canonical contributor onboarding entrypoint.
- Setup and deployment details live in [docs/DEPLOYMENT.md](docs/DEPLOYMENT.md).

## Nice to have (deferred)

- **Policy-sync pre-commit hook** — keep the secure-coding policy in
  [CLAUDE.md](CLAUDE.md) byte-for-byte in sync with an overlay in
  `protocol-sift/global/CLAUDE.md` (the file the deployed workstation agent
  actually reads). Requires three pieces, none built yet: the overlay section
  in the global CLAUDE.md (P-08's file — sync the prompt too),
  `scripts/check_security_policy_sync.py`, and `scripts/install-git-hooks.sh`.
  Until then, mirror policy edits between the two files manually.
