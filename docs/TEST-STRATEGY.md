# Test Strategy — where tests run and how they stay current

This is the living strategy for the NTP-enrichment test suite. The suite itself
lives in the sibling `protocol-sift` checkout (`../protocol-sift`); this repo
carries no tests of its own. For the original gap-closure plan that built the
suite, see [TEST-PLAN.md](TEST-PLAN.md) (historical).

## The three tiers

| Tier | Where it runs | What | When |
|---|---|---|---|
| **1 — CI (primary gate)** | GitHub Actions, ubuntu-latest | `bash analysis-scripts/tests/run_acceptance.sh` → `ACCEPTANCE: all checks passed` | Every push/PR touching `analysis-scripts/**`, `skills/**`, `scripts/hooks/**`, `requirements.txt`, or the workflows |
| **2 — Repo suite (on demand)** | Any checkout — laptop or the workstation's `protocol-sift` checkout | Same command; add `python3 tests/smoke_test.py` *without* `--offline` for live-NTP proof | Pre-PR, debugging, demo prep |
| **3 — Workstation (post-deploy)** | SIFT box, from the repo checkout, after `bash install.sh` | `bash analysis-scripts/tests/verify_deploy.sh` → `OK: 5/5 deploy checks passed` — reads `~/.claude` only (8 scripts, 6 skills, 3 hooks, config, sync cron) | After every deploy |

`run_acceptance.sh` aggregates: pytest (unit suite), `smoke_ntp_agent.sh`
(3 end-to-end scenes), `verify_cloned_repos.sh` (build/file-presence),
`smoke_protocol_sift.sh`, and the tlcorr pipeline suite
(`smoke_test.py --offline`, T-01…T-08).

## The two verifiers — naming

- **`verify_cloned_repos.sh`** — *build* verification: asserts the repo
  checkout contains what the prompt series builds (modules present, ntplib
  pinned). Runs everywhere, including CI; part of the acceptance gate.
- **`verify_deploy.sh`** — *deploy* verification: asserts `bash install.sh`
  actually landed everything under `~/.claude`. Workstation-only by nature
  (CI has no deployed tree), so it is deliberately **not** in
  `run_acceptance.sh`. It only reads `~/.claude` and is never copied there.

## Maintenance rules

1. **`run_acceptance.sh` is the single registry.** A test not reachable from it
   is not a gate (pytest collects `test_*.py` automatically; shell or
   standalone suites need an explicit line). The one exception —
   `verify_deploy.sh` — is documented inline in the gate script itself.
2. **Tests ride in the same PR as the code they cover**, with the CI
   path-triggers as backstop.
3. **`/ntp-prompt-sync` covers tests too.** Direct protocol-sift changes —
   tests included — get a sync follow-up, with green-count milestones
   recomputed (never hand-edited). protocol-sift's post-commit reminder hook
   (`bash scripts/install-git-hooks.sh`, once per checkout) prints a loud
   banner when prompt-owned paths change.
4. **Anchor docs on the command, not raw counts.** Cite
   `run_acceptance.sh` → `ACCEPTANCE: all checks passed` as the expectation;
   counts are secondary detail.
5. **Nothing test-related ever enters `install.sh`'s copy list.** The
   `~/.claude` tree stays runtime-only — other skills share that machine.
