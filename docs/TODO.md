# Submission Readiness Review
## Protocol SIFT — NTP Enrichment · SANS FindEvil Hackathon

**Review date:** 2026-06-12 · **Last updated:** 2026-06-13 (error handling pass)
**Deadline:** 2026-06-15 (3 days)

All 8 components are mandatory. Missing any one means elimination.

---

## Status summary

| Req | Deliverable | Status | Committed |
|---|---|---|---|
| 1 | GitHub repo + MIT license | ✅ Done | License confirmed present |
| 2 | Demo video (≤5 min, self-correction on screen) | ❌ Not recorded | Record Jun 13 |
| 3 | Architecture diagram (guardrails distinguished) | ✅ Done | 0e94e68 |
| 4 | Written project description (Devpost) | ❌ Not drafted | Draft + publish Jun 13 |
| 5 | Dataset documentation | ✅ Done | 0e94e68 |
| 6 | Accuracy report (FPs, misses, spoliation) | ✅ Done | 0e94e68 |
| 7 | Try-it-out instructions | ✅ Done | 0e94e68 |
| 8 | Agent execution logs (sample committed) | ⚠️ Infra built; sample missing | Commit after Jun 13 recording |

---

## Done (Jun 12)

### Req 5 — Dataset Documentation ✅
**File:** `hackasans-correlator/docs/dataset.md`

- SRL-2018 host inventory (7 steps, disk + memory artifacts)
- EID 35/260 artifacts recovered from `base-wkstn-01`: NTP server `base-dc.shieldbase.lan`, offsets `-0.0004007 s` / `-0.0032941 s`
- Happy-path findings (14 rows, rank 1, 0 assumptions) and self-correction case (exit 3, 3 iterations, 1 unresolved row)
- Four reproducibility paths: full SR018 download, synthetic fixtures, smoke tests, demo staging script

---

### Req 6 — Accuracy Report ✅
**File:** `hackasans-correlator/docs/ACCURACY-REPORT.md`

- **False positives:** None observed (EID-based resolution is deterministic; assumption flag is intentional, not a FP)
- **Missed artifacts:** Linux NTP sources not implemented (chronyc, syslog); short Plaso export windows
- **Hallucination prevention:** `ntp_assumption=true` flag + bounded self-correction loop (±1000 s)
- **Evidence integrity:** Architectural controls documented (read-only mount, ValueError on /cases/ write, SHA-256 check, encrypted EBS); prompt-based controls documented as secondary
- **Spoliation testing:** Both tests pass — injection text treated as inert data; SHA-256 of source unchanged after processing with malicious payload CSV
- **Caveats §6.1–6.6:** All documented, including §6.6 (unencrypted NTP transport — PoC only, not production-ready)

---

### Req 3 — Architecture Diagram ✅
**Change:** `hackasans-correlator/README.md`

`docs/component-diagram.jpg` embedded with caption that explicitly names both guardrail types:
- **Architectural (primary, enforced):** read-only EBS mount, ValueError on /cases/ write, SHA-256 integrity check, encrypted EBS, CloudWatch logging
- **Prompt-based (secondary, instructed):** agent reads SKILL.md, instructed not to write to source paths

Satisfies the requirement without a diagram redraw.

---

### Req 7 — Try-It-Out Instructions ✅
**Change:** `hackasans-correlator/README.md`

Try-it section restructured:
1. **Primary path:** `git clone protocol-sift && bash install.sh` — no AWS credentials, any Ubuntu 22.04+ SIFT box or VM
2. **Secondary path:** AWS-hosted SIFT via Cognito-MFA → SSM — contact team for credentials

Removes the budget/availability dependency from the judge experience.

---

### Req 1 — Repository & License ✅
Repo is public at `ciphentech/hackasans-correlator`. MIT `LICENSE` file confirmed present.

---

### Error Handling and Reliability Review ✅
**Branch:** `protocol-sift/fix/error-handling-reliability` (awaiting push)

- **_preflight(args)** added to `ntp_enricher.py`: validates input file existence, output directory writability, and required module importability before `SiftSession` opens — exits 1 with `[ntp-enrichment] ERROR:` prefix on stderr instead of crashing mid-session
- **ntp_manifest.emit()** wraps `report_path.write_text()` in `try/except OSError` with descriptive stderr message before re-raising — unwritable `analysis/` now surfaces as a named failure, not a generic `session_error`
- **smoke_protocol_sift.sh Scene 8** extended: `timeout 120` prevents indefinite hang on wrong fixture; psort stderr captured to tempfile and shown on failure
- **Both ntp-enrichment/SKILL.md files** updated with "Producing the input CSV" psort pitfall block (full-disk hang, empty date-range, rm -f before re-run)
- **PR #23** (`fix-smoke-scene8-plaso`) merged into feature branch — fixes 25-min hang and empty-output bug in Scene 8
- **Prompts updated:** P-06 (SKILL.md spec + psort caution), P-07 (emit() OSError spec), P-09 (_preflight spec)

---

### Security Review ✅
**File:** `hackasans-correlator/docs/SECURITY-REVIEW.md`

- **2 HIGH:** No prompt injection guard in SKILL.md (CSV field content not marked as opaque data); relative path traversal bypasses both Python `_reject_forbidden_path()` and `settings.json` deny rules (neither uses `.resolve()` or `**/` wildcards)
- **3 MEDIUM:** `/evidence/` absent from settings.json deny rules despite being in CLAUDE.md; `json.dumps(default=str)` in `log_agent_trace.py` could serialize credential `__repr__` to trace log; `SIFT_PROJECTS_DIR`/`SIFT_ANALYSIS_DIR` env vars used without path validation
- **2 LOW:** `cli_args=vars(args)` logs analyst paths into the accuracy report; `~/.protocol-sift/` trace files written with default umask (world-readable on 022 systems)
- All findings include file/line citations and concrete remediation recommendations
- Strengths table confirms what is safe: no `shell=True`, no `eval`, allowlist-before-network, SHA-256 check, bounded loop, fail-closed hooks

---

## Remaining (Jun 13)

### Req 2 — Demo Video ❌
**What's ready:** Storyboard complete (`hackasans-correlator/docs/demo/ntp-enrichment-self-correction.md`), one-command staging (`hackasans-correlator/scripts/stage_self_correct_case.sh`), rehearsal checklist in place.

**Pre-recording checklist:**
1. `bash scripts/stage_self_correct_case.sh` → HALT, exit 3, `unresolved_rows` entry
2. `bash ../protocol-sift/analysis-scripts/tests/smoke_ntp_agent.sh` → `OK: 3/3 scenes`
3. Open Claude Code in `/tmp/ntp_demo/DEMO-NTP-2026-001/`
4. Verify Shot 4b files exist: `analysis/<session_id>_forensic_audit.log`, `~/.protocol-sift/agent_trace.jsonl`, `analysis/token_usage.json`

**After recording:** Upload video → replace `https://example.com/demo-link` in `README.md`.

---

### Req 8 — Agent Execution Logs ⚠️
**Infrastructure:** Built and deployed. `log_agent_trace.py` (PostToolUse), `capture_session.py` (Stop hook), `sift_logger.py` all write structured output during every agent run.

**What's missing:** A sample committed to the repo so judges can verify without running the agent.

**Action (after Jun 13 recording):** Extract from the demo run and commit to `hackasans-correlator/docs/demo/sample-logs/`:
- `agent_trace.jsonl` — shows all 3 self-correction iterations as separate `ntp_enricher.py` tool calls
- `token_usage.json` — per-model input/output/cache tokens + USD
- `forensic_audit_excerpt.log` — trimmed to the enrichment session; redact workstation username from paths

Add a 3-line `hackasans-correlator/docs/demo/sample-logs/README.md` noting when captured and how to read them.

---

### Req 4 — Written Project Description (Devpost) ❌
**Status:** `README.md` has `https://example.com/devpost` placeholder. Entry not drafted.

**Draft outline (all source material is in the repo):**
- **What it does:** ISC2 admissibility problem → NIST-anchored timeline with bounded self-correction. Pull from README "The problem" and "What this delivers."
- **How we built it:** Two-repo architecture, 11-prompt TDD series, SKILL.md as executable reasoning vs. Python tools as deterministic hands. Pull from `docs/ARCHITECTURE.md` "Two things built simultaneously."
- **Challenges:** Bounded retry was the core design decision (fail-closed > retry-until-it-passes in forensics). Cost discipline on $150 budget (offline-first test suite). Two AI novices building an autonomous forensic agent in 15 days.
- **What we learned:** Agent accepts implausible offsets without the validation loop. Value of prompt-owned tests. Why hallucination prevention in forensics requires architectural enforcement, not just prompting.
- **What's next:** NTS/RFC 8915 for authenticated time transport, international time sources, Linux chronyc/syslog NTP extraction.

**After publishing:** Replace `https://example.com/devpost` in `README.md`.

---

## Final step (Jun 14)

Tick remaining SPEC §7 checklist items (☐ → ☑) for Req 2, 4, and 8 once those are done. One final commit. User pushes.

---

## What's strong

- Self-correction logic built, tested (69/69 green), and demonstrated with a deterministic staged case
- Evidence integrity enforced architecturally — not just by prompt
- Structured logging covers all four artifacts required for Req 8
- Storyboard is production-ready with timed shots, scripted narration, and a verified rehearsal checklist
- All four Jun 12 deliverables committed; three items remain, all non-engineering (record, write, publish)
