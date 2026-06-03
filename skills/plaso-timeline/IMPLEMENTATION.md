# Claude Code Implementation Guide — v3
## NTP Enrichment — Plaso Super-Timeline

**Companion files:** `prompts/*.md` — contains every paste-ready prompt body
and acceptance check for P-00 through P-10. Each prompt has a separate file for ease of testing, execution and tracking. Use them side by side with this guide.

**What changed from v1:** v1 produced static Python scripts a human runs
manually. That is wrong for this project. Protocol-SIFT is an *autonomous
agent*. The Python scripts are tools the agent uses — they are not the agent
itself. This guide builds the full agentic loop: the Claude Code session IS
the agent. It reasons, decides, runs tools, reads their output, self-corrects,
and surfaces findings. The Python code is the agent's hands, not its brain.

**Features:** three refinements baked in from
later review:

- **P-00** sets up the Python runtime explicitly — venv, pinned
  versions of `pytest`, `pandas`, `ntplib`, import verification — so the
  rest of the sequence has guaranteed prerequisites instead of relying on
  whatever happens to be on the SIFT workstation.
- **P-02's `NTPContext`** uses a standard Python library to implement the dataclass instead of Pydantic, which would introduce an additional code dependency:
  `@dataclass(frozen=True, slots=True)`, a `__post_init__` that rejects
  non-numeric / NaN / inf offsets and other categorical bad input, a
  `ConfidenceRank(IntEnum)` for the 1–6 ranks, and a `to_dict()` for
  manifest serialization. No external dependency on pydantic. The
  plausibility bound (±1000 s) deliberately stays in `validate_context`
  in P-05 so the self-correction loop can recover from implausible
  offsets rather than crashing at construction.
- **P-03's `resolve_ntp_source`** returns `ConfidenceRank.X` enumerated values
  instead of bare integers. Existing tests (`assert ctx.confidence_rank == 1`)
  still pass because `IntEnum` compares cleanly with `int`.

---

## Repository layout

All skill instructions, Python tools, tests, and install machinery live in **`ciphentech/protocol-sift`**. This is the single repo that lands at `~/.claude/` on the SIFT workstation — the one Claude Code reads at runtime.

Every prompt in the `prompts/` directory opens with "Work inside `protocol-sift/`". The file map at the end of this guide shows the complete layout after all 11 prompts have run.

---

## The architecture in one sentence

**Claude Code (the forensic agent) reads `SKILL.md` files as its reasoning
instructions, runs Python scripts as tools via `Bash()`, reads the manifest
JSON those scripts emit, and decides autonomously whether to accept the
result or loop back with corrections — up to 3 iterations, then escalates.**

That loop implements the capability described by `SPEC.md`.

---

## Two things being built simultaneously

| Layer | What it is | Who authors it |
|-------|-----------|----------------|
| **Agent instructions** | `SKILL.md` files that tell Claude Code *how to reason* through NTP enrichment — what to check, what to decide, when to loop | You write these in the prompts |
| **Agent tools** | Python scripts (`ntp_resolver.py`, `ntp_enricher.py`) the agent invokes via `Bash()` | Claude Code writes these when instructed |

The `SKILL.md` is not documentation. It is the agent's decision procedure.
Claude Code agent reads it at the start of every case session. The Python scripts
do the heavy lifting, and are designed to be deterministic, testable and audit-safe.

---

## How Claude Code operates in the SIFT Workstation protocol:sift tool

On the SIFT workstation, you'll navigate to a case directly and start `claude`.  Claude Code:

1. Auto-loads `~/.claude/global/CLAUDE.md` — the principal DFIR Orchestrator
   role, forensic constraints, tool routing table
2. Auto-loads the case `CLAUDE.md` — case-specific evidence paths and IOCs
3. Reads skill files via `@~/.claude/skills/<skill>/SKILL.md` when a domain
   comes up
4. Runs `Bash(...)` tool calls — the allowed set is in `settings.json`
5. At session end, fires the `Stop` hook — writes `forensic_audit.log` and
   captures the session transcript

The agent loop for NTP enrichment fits into steps 3–4: the agent reads the
NTP skill, runs the Python tools, reads the manifest JSON they emit, and
decides what to do next — **all inside a single Claude Code session with no
human intervention between steps**.

---

## Prompt sequence

| Step | What it builds | Acceptance gate |
|------|----------------|-----------------|
| P-00 | Python env + pinned dependencies | `import pytest, pandas, ntplib` OK |
| P-01 | Test fixtures + pytest scaffold | 31 stubs collected |
| P-02 | Hardened `NTPContext` + EID extraction | 13 resolver/validation tests green |
| P-03 | `resolve_ntp_source` decision tree (`ConfidenceRank`-driven) | All 18 resolver tests green |
| P-04 | `ntp_enricher.py` field computation + safe writer | 10 enricher tests green |
| P-05 | `validate_and_correct()` + self-correction loop | 32 unit tests green |
| P-06 | **`SKILL.md` as agent reasoning instructions** | Structural lint |
| P-07 | **Manifest JSON + rubric evaluator** | 36 tests green (32 + 4 manifest) |
| P-08 | **`settings.json` permissions + `plaso-timeline` handoff** | Settings schema check |
| P-09 | **Agent trace smoke test** | 7-scene end-to-end gate |
| P-10 | `install.sh` patch + verify_install.sh | 8-assertion install check |

Each step builds on the previous one. Acceptance gates are hard — do not
proceed to the next step until the current step's acceptance check passes.

The bolded steps (P-06 through P-09) are the *agent layer* — what
distinguishes this build from v1's static-script approach.

---

## P-00 through P-05 — Foundation and tool layer

These six prompts build the testable Python tool layer. They are TDD: every
prompt creates tests before or alongside the implementation, and the
acceptance check is a hard gate. If TDD is new to you, read the **TDD
primer** near the top of `prompts.md` before starting P-01 — it explains
the red → green cycle that every prompt below assumes.

**P-00 establishes the runtime.** Python ≥ 3.10 (PEP 604 union syntax and
PEP 585 generics in the codebase require it), a virtualenv at `./venv/`,
and a `requirements.txt` with pinned ranges (`pytest>=7.4,<9.0`,
`pandas>=2.0,<3.0`, `ntplib>=0.4.0`). Without this step, P-01's acceptance
check runs `pytest --collect-only` against an environment that may not have
pytest installed.

**P-01 lays the test scaffold.** Stubs for 17 resolver tests and 14
enricher tests, a 14-row synthetic l2tcsv fixture (`ntp_mini.csv`),
ground-truth JSON, and `conftest.py`. No production code yet — the TDD
contract starts here.

**P-02 implements `NTPContext` and the EID extraction helpers.** This is
where the hardening lives:

- `@dataclass(frozen=True, slots=True)` — immutable instances, smaller
  memory footprint, and typo-catching (`ctx.ntp_sorce = "..."` raises
  `AttributeError` instead of silently creating a junk attribute).
- `ConfidenceRank(IntEnum)` — replaces magic numbers 1–6 with named ranks
  (`ARTIFACT_LOG`, `ANALYST_VERIFIED`, `ANALYST_STATED`, `CLOUD_DEFAULT`,
  `WINDOWS_DOMAIN`, `DISTRO_DEFAULT`). `IntEnum` compares with `int`, so
  existing tests stay green.
- `__post_init__` validation — rejects non-numeric offsets, NaN/inf,
  invalid EIDs, out-of-range ranks, and the "ntp_assumption=False with
  empty source" inconsistency. Specific error types: `TypeError` for type
  problems, `ValueError` for semantic ones.
- `to_dict()` — serializes to plain dict (with `confidence_rank` coerced
  to `int`) so the manifest JSON writer in P-07 can dump it cleanly.

The plausibility bound (`abs(offset) > 1000 s`) is **not** in
`__post_init__`. It lives in P-05's `validate_context` so the self-
correction loop can recover from implausible offsets — if construction
crashed on a wild offset, the loop would never run.

**P-03 implements `resolve_ntp_source`** — the full Phase 2 decision tree
from `spec.md §4`. Six paths: artifact EID logs (rank 1), CLI flag
(rank 2), interactive prompt (rank 3), cloud default (rank 4), Windows
domain default (rank 5), distro default (rank 6). All paths return typed
`ConfidenceRank.X` values rather than bare integers.

**P-04 implements `enrich()`.** Reads the source CSV (read-only), computes
the five new fields per row, enforces forbidden-output-path checks
(`/cases/`, `/mnt/`, `/media/` are rejected), writes the enriched CSV
sorted on `nist_time`, and verifies the source file SHA-256 is unchanged.

**P-05 implements the self-correction loop.** `validate_context()` checks
the plausibility bound. `validate_and_correct()` runs the enricher, and
on failure emits a structured correction log and returns a corrected
context for re-run. Iteration cap is 3, then escalate.

After P-05, `pytest tests/` shows **32 passed**. The tool layer is correct
and tested.

---

## P-06 — `SKILL.md` as agent reasoning instructions

**The most important step in the sequence.** Up to this point everything
is Python and tests. P-06 is what makes Claude Code *act as an agent*
rather than as a code generator.

The `SKILL.md` file is the agent's decision procedure. When the analyst
asks "generate the NTP-enriched timeline", Claude Code reads
`skills/ntp-enrichment/SKILL.md` and executes its Workflow section
step-by-step:

| Step | What the agent does |
|------|---------------------|
| 1 | Locate the psort export |
| 2 | Probe the artifact for NTP logs (grep EID 35/259/260) **before** asking the analyst anything |
| 3 | NTP source resolution — interactive prompt only if no logs found |
| 4 | Run the enricher |
| 5 | Read the manifest JSON |
| 6 | Self-correct if `rubric_pass=false`, mapped to one of three actions: `relax-assumption`, `recheck-offset`, `escalate-to-operator` |
| 7 | Verify and summarise findings |

Every branching decision in `spec.md §4 Phase 2` appears here as an
explicit instruction. The agent does not improvise — it follows the
procedure.

The acceptance gate is structural: `grep "rubric_pass"` returns at least
three lines (manifest read, branching on true/false, self-correct
section), `grep "escalate-to-operator"` returns exactly two (the
corrective action and the iteration cap), and the skill directory
contains *only* `SKILL.md` — no Python or shell scripts.

---

## P-07 — Manifest JSON + rubric evaluator

The manifest is the interface between the Python tools (deterministic,
testable) and the agent's reasoning loop (read-evaluate-decide). Without
the manifest, the agent has no way to decide whether to accept the
enrichment result or self-correct.

`write_manifest()` produces JSON containing:

- The enrichment summary (rows processed, integrity hashes, source, offset)
- The rubric thresholds applied (loadable from `analysis/ntp_rubric.json`
  per-case, defaults otherwise)
- `rubric_pass` (bool), `rubric_failures` (list of strings), and
  `suggested_corrective_action` (the next action the agent should take)
- The iteration number — iter0 / iter1 / iter2 all coexist; manifests are
  never overwritten

The rubric is intentionally configurable per case. The defaults work for most investigations. For a legal submission, set
`require_assumption_false=True` and `require_eid_source=True` to enforce
artifact-derived sources only.

Four unit tests cover the manifest layer (`test_ntp_manifest.py`),
bringing the suite total to **36 passed**.

---

## P-08 — `settings.json` permissions + `plaso-timeline` handoff

The wiring step. Four small changes that nothing depends on individually
but which together connect the agent layer to the rest of Protocol-SIFT:

1. **`global/CLAUDE.md` routing.** A new row in the Tool Routing table
   pointing at `@~/.claude/skills/ntp-enrichment/SKILL.md`. Without this,
   the orchestrator doesn't know the skill exists.
2. **`global/settings.json` allow list.** Permits the agent to run
   `python analysis-scripts/ntp_resolver.py` and `ntp_enricher.py` via
   `Bash()`, and to write `./analysis/*_ntp_manifest*.json` and
   `*_ntp_caveats.txt`. The existing deny list (`rm -rf`, etc.) is
   preserved verbatim — the acceptance check explicitly verifies it
   wasn't corrupted.
3. **`Stop` hook extension.** When the session ends, the hook captures
   the NTP manifest path in `forensic_audit.log` if a manifest exists.
   Wrapped in `|| true` so a missing manifest never breaks session
   shutdown.
4. **`plaso-timeline/SKILL.md` handoff.** A new "§4b. NTP Time
   Enrichment" section pointing the orchestrator at the NTP skill after
   the psort export step.

Nothing new is *built* in this step, but without it the agent layer is
isolated from the rest of the system.

---

## P-09 — Agent trace test: simulate the full reasoning loop

This is the canonical demo-video scene, written as shell so it runs
deterministically without burning Claude API tokens. The script *is*
the agent's Step 2–6 decision logic from `SKILL.md`, expressed as Bash
assertions.

Five scenes, seven assertions:

| Scene | What it proves |
|-------|----------------|
| 1 — happy path | EID logs present → enricher auto-detects → `rubric_pass=true` on iter0, no correction needed |
| 2 — self-correction | No EID logs + forced bad offset → `rubric_pass=false` on iter0 → re-run → `rubric_pass=true` on iter1. Both manifest files exist; iter0 is not overwritten. |
| 3 — iteration cap | Three failing iterations → `suggested_corrective_action="escalate-to-operator"` |
| 4 — spoliation | Fixture SHA-256 unchanged before/after run |
| 5 — forbidden path | `--output /cases/test.csv` exits non-zero |

A `--force-offset` testing flag is added to `ntp_enricher.py` in this step.
It prints a stderr warning on use (`--force-offset active — for testing
only, do not use in production`) so it cannot be silently abused.

Running `bash smoke_ntp_agent.sh` twice in a row both pass (idempotent),
in under 30 seconds.

---

## P-10 — `install.sh` patch + final verification

Installation closure:

- `requirements.txt` already has `ntplib>=0.4.0` from P-00; P-10
  re-confirms it (idempotent append).
- `install.sh` gets a copy block for the new skill and the two analysis
  scripts.
- `verify_install.sh` runs 8 assertions confirming every artifact is in
  place: skill file, both Python tools, the `ntplib` line in
  requirements.txt, the `ntp-enrichment` block in install.sh, the
  routing row in CLAUDE.md, the allow entries in settings.json, and the
  `rubric_pass` keyword in SKILL.md (proves the agent loop wiring is
  present, not just the file).

Final regression after P-10:

```
pytest tests/ -v                                    # 36 passed
bash analysis-scripts/tests/smoke_ntp_agent.sh      # 7 PASS
bash analysis-scripts/tests/verify_install.sh       # 8 PASS
```

Total: **36 + 7 + 8 = 51 assertions** across three layers, all green.

---

## End-to-end agent trace — what the full loop looks like

The `smoke_ntp_agent.sh` Scene 2 is the canonical demo sequence. In a live
Claude Code session it looks like this:

```
[analyst] Generate the NTP-enriched timeline for case RD01.

[agent]   Probing artifact for NTP logs...
          → grep -c "\[260 " ./exports/RD01_timeline.csv → 12 rows
          → EID 260 found. Auto-detecting NTP source and offset.

[agent]   Running enrichment...
          → python analysis-scripts/ntp_enricher.py --input ... --output ...
          → [ntp-enrichment] manifest: ./analysis/RD01_ntp_manifest.json

[agent]   Reading manifest...
          → rubric_pass: false
          → rubric_failures: ["ntp_offset_s abs value 0.0033 s exceeds threshold 0.001 s"]
          → suggested_corrective_action: recheck-offset

[agent]   Self-correction triggered (iter=1, reason=recheck-offset).
          Verifying offset in artifact...
          → grep "Phase Offset" ./exports/RD01_timeline.csv | sort -u
          → Phase Offset: -0.0004007s, Phase Offset: -0.0032941s
          Offset confirmed in artifact. Adjusting rubric threshold to 0.01 s
          and re-running.
          [ntp-enrichment.self-correct] iter=1 reason=recheck-offset
            action=relax-assumption

[agent]   Re-running enrichment (iter=1)...
          → manifest: ./analysis/RD01_ntp_manifest.iter1.json
          → rubric_pass: true

[agent]   NTP enrichment complete.
          Source: base-dc.shieldbase.lan (EID 260, ConfidenceRank.ARTIFACT_LOG)
          Offset: -0.0004007 s (≈ 400 µs behind NIST)
          ntp_assumption: false — confirmed from artifact logs
          Enriched timeline sorted on nist_time. 847,234 rows processed.
          Ready for cross-source correlation.
```

That sequence — probe → run → read manifest → self-correct → re-run →
accept — is the core agentic loop. The smoke test proves it works.
The `SKILL.md` is what makes the agent do it autonomously.

---

## Complete file map after all 11 prompts

```
protocol-sift/
├── analysis-scripts/
│   ├── ntp_resolver.py              [P-02 hardened NTPContext + ConfidenceRank]
│   │                                [P-03 decision tree]
│   ├── ntp_enricher.py              [P-04 enrich(); P-05 validate_and_correct();
│   │                                 P-07 write_manifest(); P-09 --force-offset]
│   └── tests/
│       ├── smoke_ntp_agent.sh       [P-09 — the demo video scene]
│       └── verify_install.sh        [P-10]
├── skills/
│   ├── ntp-enrichment/
│   │   └── SKILL.md                 [P-06 — the agent's decision procedure]
│   └── plaso-timeline/
│       └── SKILL.md                 [P-08 — §4b handoff added]
├── tests/
│   ├── conftest.py                  [P-01]
│   ├── test_ntp_resolver.py         [P-01 scaffold → P-02/03 implemented]
│   ├── test_ntp_enricher.py         [P-01 scaffold → P-04/05 implemented]
│   ├── test_ntp_manifest.py         [P-07 — rubric tests]
│   └── fixtures/
│       ├── ntp_mini.csv             [P-01 — real EID format from rd01]
│       ├── ntp_mini_no_eids.csv     [P-09 — forces assumption branch]
│       └── expected_ntp_ground_truth.json  [P-01]
├── global/
│   ├── CLAUDE.md                    [P-08 — routing row added]
│   └── settings.json                [P-08 — allow entries + Stop hook]
├── venv/                            [P-00 — gitignored]
├── .gitignore                       [P-00 — append-only]
├── .python-version                  [P-00]
├── requirements.txt                 [P-00 pinned; P-10 reconfirms ntplib]
└── install.sh                       [P-10 — ntp-enrichment block]
```

---

## Test coverage by layer

| Layer | File | Count | What it covers |
|-------|------|-------|----------------|
| Unit — resolver | `test_ntp_resolver.py` | 18 | EID regex (5), phase offset parsing, `NTPContext` validation: frozen, `__post_init__` checks for type/NaN/EID/rank/empty-source, `to_dict()` (8), decision-tree paths (5) |
| Unit — enricher | `test_ntp_enricher.py` | 14 | Field math, column preservation, forbidden paths, hash integrity, self-correction caps |
| Unit — manifest | `test_ntp_manifest.py` | 4 | Rubric pass/fail, iteration suffix, schema completeness |
| Agent smoke | `smoke_ntp_agent.sh` | 7 | Full loop: happy path, self-correction scene, iteration cap, spoliation, forbidden path |
| Install | `verify_install.sh` | 8 | All files in place, routing wired, agent loop detectable |
| **Total** | | **51** | |
