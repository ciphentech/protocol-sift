# Protocol SIFT — NTP Enrichment Prompts
## hackasans-correlator · SANS FindEvil Hackathon

Index of the build-prompt series in [`docs/prompts/`](prompts/). Each prompt
file contains the prompt body in a fenced block (paste into Claude Code) plus
an acceptance check (run yourself after Claude Code completes the step).

The prompt files are the source of truth for the series. Every prompt has been
reconciled against the **actual code** in the sibling `protocol-sift` repo
(`../protocol-sift`, the `ciphentech` fork of `teamdfir/protocol-sift`), so
executing each prompt reproduces what is really there — see
[`prompts/RECONCILIATION-CHECKLIST.md`](prompts/RECONCILIATION-CHECKLIST.md)
for the per-prompt drift notes. `hackasans-correlator` is strictly the
authoring repo (design docs + prompts); all generated code lands in
`protocol-sift`, which is a **sibling checkout — never a subdirectory or
submodule**.

**Keeping prompts and code in sync:** the preferred way to change the feature is
to edit the relevant prompt (or design doc) here first and re-apply the step in
`protocol-sift`. If code is ever modified directly in `protocol-sift`, run the
`/ntp-prompt-sync` skill
([.claude/skills/ntp-prompt-sync/SKILL.md](../.claude/skills/ntp-prompt-sync/SKILL.md))
to propagate the change back into the prompt series — see the change-workflow
section in [CONTRIBUTING.md](../CONTRIBUTING.md) for the full policy.

## Running the series with the generator skill

The `ntp-enrichment-generator` skill
([.claude/skills/ntp-enrichment-generator/SKILL.md](../.claude/skills/ntp-enrichment-generator/SKILL.md),
mirrored to `~/.claude/skills/` for invocation) drives the whole series so you
don't paste prompts by hand. It is step-gated with auto-continue: each step
ends by running that prompt's own acceptance check — green gates continue
automatically, a red gate hard-halts. Every gate (pytest, smoke, verify)
executes **in the sibling `protocol-sift` repo**; the authoring repo is never
written to.

In a Claude Code session at the `hackasans-correlator` repo root:

| Command | What it does |
|---|---|
| `/ntp-enrichment-generator` | Full build: P-Scaffold → P-00 → … → P-10, auto-continuing through green gates |
| `/ntp-enrichment-generator from P-04` | Resume at a step (earlier gates are still pre-checked) |
| `/ntp-enrichment-generator step` | Single-step mode: pause after each green gate and wait for "continue" |
| `/ntp-enrichment-generator status` | Read-only audit: run all 12 acceptance checks, print a PASS/FAIL table, build nothing |

Re-runs are safe: each step pre-checks its gate first and skips
"already built" work, and per-step commits land in `protocol-sift` only —
the skill never pushes.

## Execution order

`P-Scaffold` runs **first** — it prepares and verifies the sibling repo and
binds the file map (which prompt owns which deliverable path). Then P-00
through P-10 in order.

| Step | File | What gets built |
|------|------|----------------|
| P-Scaffold | [P-Scaffold.md](prompts/P-Scaffold.md) | Sibling repo prepared/verified: guarded clone + `upstream` remote, 12-file upstream SIFT baseline check, binding file map. Creates no files. |
| P-00 | [P-00-Setup.md](prompts/P-00-Setup.md) | Python environment (venv, `.python-version`) + pinned dependencies merged into `requirements.txt` |
| P-01 | [P-01.md](prompts/P-01.md) | Test fixtures (4 CSVs + ground-truth JSON), conftest pair, 10 failing test scaffolds (69 stubs) |
| P-02 | [P-02.md](prompts/P-02.md) | `ntp_resolver.py` data model (`ConfidenceRank`, `NTPContext`) + EID 35/260 extraction — 13 tests green |
| P-03 | [P-03.md](prompts/P-03.md) | `ntp_resolver.py` Phase 2 resolution decision tree (incl. two-prompt interactive flow) — 30 green |
| P-04 | [P-04.md](prompts/P-04.md) | `ntp_nist_client.py` + `ntp_enricher.py` enrichment core and safe writer — 46 green |
| P-05 | [P-05.md](prompts/P-05.md) | `ntp_enricher.py` Phase 3 self-correction loop (`validate_and_correct`) — 53 green |
| P-06 | [P-06.md](prompts/P-06.md) | `skills/ntp-enrichment/SKILL.md` — agent reasoning instructions |
| P-07 | [P-07.md](prompts/P-07.md) | `ntp_manifest.py` accuracy report + `sift_logger.py` forensic session logger — 59 green |
| P-08 | [P-08.md](prompts/P-08.md) | Global template wiring: `global/skills/` variant, `global/CLAUDE.md` routing row, `global/settings.json` denies + hooks (incl. the Stop-hook capture chain), three `global/hooks/` scripts |
| P-09 | [P-09.md](prompts/P-09.md) | `ntp_enricher.py` CLI section + `test_logger`/`test_spoliation` + `smoke_ntp_agent.sh` agent-loop smoke test — 69/69 green |
| P-10 | [P-10.md](prompts/P-10.md) | `install.sh` deployment patch + `verify_cloned_repos.sh` + final suite (pytest 69, smoke 3/3, verify 5/5) |

All paths in the prompts are relative to the `protocol-sift` repo root; code
lives flat under `analysis-scripts/` (`ntp_*.py`, `sift_logger.py`), tests
under `analysis-scripts/tests/`, hooks under `global/hooks/`.
