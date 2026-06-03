# Protocol SIFT — Time Sync Normalization Feature

**Architecture Pattern:** Direct Agent Extension (Claude Code)  
**Runtime:** Python on SANS SIFT Workstation (Ubuntu 22.04+)  
**License:** MIT

---

## 1. What This Feature Does

This module extends Protocol SIFT's autonomous incident response agent with accurate, NIST-anchored timestamp normalization across all log sources. When correlating evidence from multiple systems — Windows Event Logs, syslog, network captures, endpoint telemetry — clock skew between log sources and true UTC is a common source of analytic error and, if undocumented, a potential chain-of-custody problem.

This feature teaches the agent to:
 - Identify the time source for each parsed log
 - Determine the NTP configuration of the originating workstation (by asking the analyst or making a reasoned assumption)
 - Infer the host clock offset from recovered NTP/time-sync evidence and validate the assumed NTP source against NIST
 - Normalize all log timestamps to UTC using that inferred offset
 - Re-sort the enriched timeline and self-correct if assumptions were wrong

The output is a Plaso-compatible enriched timeline ready for accurate cross-source correlation and forensic reporting.

---

## 2. Output Fields

NIST is treated as the authoritative reference for UTC in this design, but `nist_time` is a derived estimate: it is computed from the original event timestamp plus an inferred clock offset, not directly observed from the event.

The enriched timeline preserves all existing Plaso column names and appends new columns. Existing fields are never renamed or removed.

### 2.1 Existing Plaso Fields (preserved as-is)

| Plaso Field | Type | Notes |
|---|---|---|
| `date` | date | Event date — used as the source for `nist_time` computation |
| `time` | time | Event time — used as the source for `nist_time` computation |
| `timezone` | string | Timezone of the original log (e.g., `UTC`) |
| `MACB` | string | Modified / Accessed / Changed / Born flags |
| `source` | string | Log source category (e.g., `EVT`) |
| `sourcetype` | string | Specific log format (e.g., `WinEVTX`) |
| `type` | string | Timestamp type description |
| `user` | string | User associated with the event |
| `host` | string | Hostname of the originating system |
| `short` | string | Short event description |
| `desc` | string | Full event description |
| `version` | string | Plaso format version |
| `filename` | string | Source log file path — used as the NTP log search target |
| `inode` | string | Filesystem inode |
| `notes` | string | Analyst notes |
| `format` | string | Parser format used |
| `extra` | string | Additional parser-extracted fields |

### 2.2 New Fields Added by This Feature

| Field | Type | Description |
|---|---|---|
| `ntp_source` | string | NTP server used by the originating workstation |
| `nist_time` | datetime (UTC) | Derived UTC timestamp for the event, computed from the original `date` + `time` using an inferred NTP clock offset (`ntp_offset_s`) |
| `ntp_offset_s` | float (seconds) | Local clock offset from the NTP peer in seconds (from EID 35 strings[1] ÷ 10,000,000; or EID 260 offset string) — positive means the source clock was ahead of NIST, negative means behind |
| `ntp_assumption` | bool | `true` if `ntp_source` was assumed rather than confirmed from logs or analyst input |
| `nist_delta_s` | float (seconds) | Ground truth delta available from the artifact — computable as the `ntp_offset_s` value |

> **Sorting and correlation must be done on `nist_time`, not on the original `date`/`time` columns.** `nist_time` is the field that represents what the agent believes actually happened relative to ground truth.
> **Plausibility bounds:** Clock offsets are expected to be bounded. Offsets beyond ±1000 seconds are considered implausible and trigger self-correction (see §4 Phase 3 and the implementation sequence `PROMPTS.md` §P-05 for details).
---

## 3. Prerequisites — NIST API Key

Generating a Plaso timeline with an authoritative UTC reference requires a **NIST API key**. This key is used to query the NIST time service to validate the NTP source and derive a clock offset; it is not a direct historical timestamp for past events.

### 3.1 How to Obtain an API Key

1. Go to [https://nvd.nist.gov/developers/api-key-requested](https://nvd.nist.gov/developers/api-key-requested)
2. Fill out the request form with your name, organization, and intended use
3. NIST will email the API key to the address provided
4. Store the key in the environment variable `NIST_API_KEY` on the SIFT workstation — **never hardcode it in source files**

```bash
# On the SIFT workstation, add to ~/.bashrc or pass at runtime:
export NIST_API_KEY="your-api-key-here"
```

### 3.2 Key Storage Requirements

- The API key must **never** be written to disk in plaintext or committed to the repository
- On the SIFT workstation, store it as an environment variable set in the analyst's shell session
- For automated runs, inject via a secrets manager (e.g., environment variable set by a secure orchestration system) — not via a `.env` file

### 3.3 What Happens Without a Key

If `NIST_API_KEY` is not set when a Plaso timeline is requested, the agent will:
1. Halt before any timestamp computation begins
2. Display an error directing the analyst to obtain a key at [https://nvd.nist.gov/developers/api-key-requested](https://nvd.nist.gov/developers/api-key-requested)
3. Warn the analyst that proceeding without a NIST API key means timestamps will not be anchored to an authoritative time source. Per ISC2 guidance on digital forensics and chain of custody, timeline evidence may be challenged or excluded in legal proceedings if time sync differences between the source system and other provided log sources are not documented and submitted alongside the evidence. The analyst may continue, but must document this limitation in any evidence package.

---

## 4. Agent Processing Flow

### Phase 1 — Log Ingestion and Initial Enrichment

```
[Log is parsed]
      │
      ▼
[Determine log source file] ──► populate time_source
      │
      ▼
[AI determines initial time sync difference] ──► populate ntp_offset_s (initial estimate)
      │
      ▼
[Compute normalized `nist_time` for each event]
      │
      ▼
[Re-sort timeline on nist_time]
```

### Phase 2 — NTP Source Resolution (parallel to Phase 1)

```
[Ask analyst: "What is the NTP source for this workstation?"]
      ├─ Analyst provides answer ───────────────────────────┐
      └─ Analyst doesn't know → agent makes assumption ─────┤
                                                            ▼
                                           [ntp_source field resolved;
                                            ntp_assumption set accordingly]
                                                            │
                                                            ▼
                                 [AI computes normalized `nist_time`:
                                  derived UTC timestamp from the inferred offset]
                                                            │
                                                            ▼
                                 [AI computes ntp_offset_s:
                                  delta between ntp_source and nist_time]
                                                            │
                                                            ▼
                                 [Compute nist_delta_s per event
                                  (ground truth delta from artifact)]
                                                            │
                                                            ▼
                                 [Re-sort timeline on nist_time (UTC)]
```

The agent prompts the analyst once per case: *"What is the NTP source for the workstation under investigation?"*

- **Answer provided:** used directly; `ntp_assumption = false`
- **Unknown:** agent assumes a reasonable default (`time.windows.com` for Windows hosts, `pool.ntp.org` for Linux); `ntp_assumption = true`; assumption is logged and surfaced in the accuracy report

### Phase 2 Detail — NTP Source Resolution Decision Tree

When a Plaso timeline is requested, the agent opens the following resolution sequence **before** computing any timestamps. The goal is to populate `ntp_source` and `ntp_assumption` with the highest-confidence value available.

#### CLI Flags

Two flags control how Phase 2 runs:

| Flag | Behavior |
|---|---|
| `--ntp-source <value>` | Skips the interactive prompt and uses the provided value as `ntp_source` directly. Sets `ntp_assumption = false`. The agent still cross-checks the value against any NTP logs in the case. |
| `--skip-ntp` | Bypasses the entire NTP enhancement. No `ntp_source`, `ntp_offset_s`, `nist_time`, or `nist_delta_s` fields are computed. Output is a standard Plaso timeline with `time_utc` only. **Must be documented if submitted as legal evidence — the timeline will not be NIST-anchored.** |

If neither flag is provided, the agent falls through to the interactive prompt flow described below.

```
[Analyst requests Plaso timeline generation]
      │
      ▼
[Agent prompts analyst:
 "Do you know the NTP source for the system being analyzed?"]
      │
      ├─ YES ──► ntp_source = analyst answer
      │           ntp_assumption = false
      │                │
      │                ▼
      │          [Agent cross-checks stated source against any NTP
      │           event logs in the case (EID 35/260, chronyc, w32tm)]
      │                │
      │                ├─ Consistent ──► proceed with stated source
      │                └─ Inconsistent ──► flag to analyst; loop to Phase 3
      │
      └─ NO  ──► [Search case data for NTP logs]
                  │   (EID 35, EID 260, w32tm /query /status,
                  │    chronyc tracking, /var/log/syslog NTP entries)
                  │
                  ├─ NTP logs found ──► ntp_source = value from logs
                  │                    ntp_assumption = false
                  │                    (highest confidence — treat as ground truth)
                  │
                  └─ No NTP logs ──► [Agent prompts analyst:
                                      "Was the system cloud-hosted or on-prem?"]
                                      │
                                      ├─ Cloud provider
                                      │   ├─ AWS (Linux or Windows)
                                      │   │     ntp_source = "169.254.169.123"
                                      │   │     (Amazon Time Sync Service)
                                      │   │     ntp_assumption = true
                                      │   │
                                      │   ├─ Azure (Linux or Windows)
                                      │   │     ntp_source = "time.windows.com"
                                      │   │     ntp_assumption = true
                                      │   │
                                      │   └─ GCP (Linux or Windows)
                                      │         ntp_source = "metadata.google.internal"
                                      │         ntp_assumption = true
                                      │
                                      └─ On-prem
                                          ├─ Windows (domain-joined)
                                          │     ntp_source = "Domain Controller"
                                          │     ntp_assumption = true
                                          │
                                          ├─ Windows (standalone)
                                          │     ntp_source = "time.windows.com"
                                          │     ntp_assumption = true
                                          │
                                          └─ Linux (on-prem, no NTP logs)
                                              ├─ Ubuntu → "ntp.ubuntu.com"
                                              ├─ RHEL / CentOS → "rhel.pool.ntp.org"
                                              ├─ Debian → "debian.pool.ntp.org"
                                              └─ Other / unknown → "pool.ntp.org"
                                              (all: ntp_assumption = true)
```

**Confidence ranking (highest to lowest):**

| Rank | Source | `ntp_assumption` |
|---|---|---|
| 1 | NTP logs recovered from the case (EID 35/260, chronyc, w32tm) | `false` |
| 2 | Analyst-provided and consistent with log evidence | `false` |
| 3 | Analyst-provided but unverifiable (no NTP logs) | `false` |
| 4 | Cloud provider default — AWS (`169.254.169.123`), Azure (`time.windows.com`), GCP (`metadata.google.internal`) | `true` |
| 5 | On-prem Windows domain default (DC → time.windows.com) | `true` |
| 6 | Linux distro default NTP pool | `true` |

Any row with `ntp_assumption = true` is surfaced in the accuracy report and must be disclosed in legal or regulatory submissions (see §6.3).

### Phase 3 — Self-Correction Loop

```
[Was a mistake made in the source time, or was the time source figured out?]
      ├─ YES ──► Loop back to Phase 2 with corrected NTP source
      └─ NO  ──► Processing complete
```

After the initial pass, the agent evaluates whether the NTP assumption or provided value was incorrect (e.g., analyst provides a correction, or the computed delta is implausible given known NTP drift bounds). If so, Phase 2 re-runs with updated information.

---

## 5. Deployment Architecture

Protocol:SIFT runs on any SANS SIFT Workstation (Ubuntu 22.04+), local or remote. The agent layer is installed to `~/.claude/` via `bash install.sh` — see `DEPLOYMENT.md` for deployment options.

```
Analyst terminal
    │  start Claude Code session on SIFT workstation
    ▼
SIFT Workstation (Ubuntu 22.04+)
    ├── Claude Code CLI
    ├── SIFT toolchain (log2timeline, psort, volatility, etc.)
    ├── ~/.claude/global/CLAUDE.md       ← DFIR Orchestrator role
    ├── ~/.claude/skills/                ← skill SKILL.md files
    └── ~/.claude/analysis-scripts/      ← Python tools
```

### Security Boundary Summary

| Boundary | Type | Enforcement |
|---|---|---|
| Source logs read-only | Architectural | Source evidence path never written to; enrichment process has read-only access |
| Output written to separate directory | Architectural | Distinct `/cases/` (input) vs `./analysis/`, `./exports/` (output); never the same path |
| Forbidden output paths | Architectural | `ntp_enricher.py` safe writer rejects writes to `/cases/`, `/mnt/`, `/media/` |
| Prompt restriction on log modification | Prompt-based | Secondary control only — architectural controls above are primary |

---

## 6. Caveats — Time Sync Limitations

Per ISC2, the Plaso timeline will include the difference in time from NIST. NIST is assumed to be the time source of truth in the US. A future improvement would be to support other authoritative time sources for investigations outside the US.

### 6.1 NTP Source Assumptions When No Logs Are Available

When NTP logs (EID 35, EID 260, `w32tm`, `chronyc`, syslog NTP entries) are not present in the collected evidence, **the agent cannot determine the NTP source from the artifact**. In this case, the NTP source is assumed based on the environment type (cloud provider or on-prem) and operating system, as described in §3 Phase 2 Detail.

These assumptions introduce uncertainty and should be treated as analyst-supplied metadata, not as equivalent evidence:
 - `ntp_assumption` is set to `true` for every log entry where the source was assumed rather than confirmed from recovered artifact evidence
 - The assumed `ntp_source` value is recorded in each entry so the basis for `nist_time` is reproducible and auditable
 - All `ntp_assumption = true` entries are flagged in the accuracy report
 - Any submission to legal or regulatory proceedings must explicitly note which events rely on assumed NTP sources and what those assumptions were

**The absence of NTP logs does not mean the timeline is invalid** — it means the time anchor carries greater uncertainty. Analysts must weigh this uncertainty when interpreting events that are close together in time or that depend on precise ordering across log sources.

### 6.2 Historical NTP Drift Is Not Directly Observable (Even With Known Source)

`ntp_offset_s` represents the estimated clock offset between the workstation and its NTP source for the event, inferred from recovered evidence and known NTP behavior. For historical log data, live NTP drift readings are unavailable. The agent approximates this offset using:
- Known NTP stratum behavior and typical drift rates
- Any NTP logs or `w32tm` / `chronyc` records recovered from the workstation
- Analyst-provided information about the NTP environment

This means the actual clock skew at the time of an event may be **shorter or longer than the computed `ntp_offset_s`**. The agent will flag cases where the assumption is uncertain.

### 6.3 Variable Clock Drift Over Time

Clock drift is not constant. A workstation that was well-synchronized at boot may drift significantly over days or weeks, especially if:
- The NTP source was unreachable for a period
- The system was suspended or hibernated
- The hardware clock (RTC) had independent drift

Analysts must treat `nist_time` as a **best estimate**, not a certified timestamp. The uncertainty window should be considered when interpreting events that are close together in time across sources.

### 6.4 ISC2 / Legal Admissibility Requirement

Per ISC2 guidance on digital forensics and chain of custody: **time source differences between log sources must be documented and submitted alongside evidence**, or the timeline may be considered incomplete and potentially inadmissible in legal proceedings.

This feature satisfies that requirement by:
- Explicitly recording `ntp_source` and `ntp_offset_s` for every log entry
- Flagging assumed vs. confirmed NTP sources (`ntp_assumption`)
- Producing a reproducible audit trail of how `nist_time` was computed for each event

Failure to document time source discrepancies — even when they appear minor — risks having timeline evidence challenged or excluded. **Do not omit these fields from any evidence package submitted to legal or regulatory proceedings.**

### 6.5 NIST as Ground Truth

This implementation treats NIST (National Institute of Standards and Technology Internet Time Service) as the authoritative time reference. This is a standard forensic convention. However:
- NIST time is itself subject to network transmission delay (typically <1ms on a healthy connection, but potentially higher)
- For sub-millisecond precision requirements, this approach is insufficient; consult a forensic time specialist

For the vast majority of incident response timelines, NIST UTC is an appropriate and defensible reference.

### 6.6 NIST Transport Security

The default implementation queries NIST time using the unencrypted NTP protocol (`time.nist.gov`, UDP/TCP port 123). This means:
 - The time response is not authenticated and could theoretically be tampered with in transit.
 - The response reflects the current time service state, not the historic time state at the moment each event was generated.
 - **This transport is not acceptable for production forensic use or legal submissions.**

**For production use:** the analyst must configure the NIST HTTPS time API using an API key obtained from [https://nvd.nist.gov/developers/api-key-requested](https://nvd.nist.gov/developers/api-key-requested) (see §3). The HTTPS API provides an authenticated, encrypted channel and is the required transport for any timeline submitted as legal evidence.

---

## 7. Deployment Checklist

| # | Requirement | Status | Notes |
|---|---|---|---|
| 1 | GitHub repo — `ciphentech/protocol-sift`, MIT license | ☐ | Confirm LICENSE file present |
| 2 | Architecture diagram (components, trust boundaries, prompt vs. architectural guardrails) | ☐ | See `docs and diagrams/plaso-timeline-workflow.md` |
| 3 | Dataset documentation (logs tested against, source, findings) | ☐ | See `dataset.md`; document NTP assumption cases found |
| 4 | Accuracy report (FPs, misses, evidence integrity, spoliation testing, `ntp_assumption` failure modes) | ☐ | Include caveats from Section 6 |
| 5 | Installation instructions (`bash install.sh`; `pip install -r requirements.txt`) | ☐ | See `DEPLOYMENT.md` |
| 6 | Agent execution logs (tool calls, timestamps, iteration traces per self-correction loop) | ☐ | Written to `./analysis/forensic_audit.log` per case |
| 7 | Smoke test passing | ☐ | `bash analysis-scripts/tests/smoke_ntp_agent.sh` — 7 PASS |
| 8 | Install verification passing | ☐ | `bash analysis-scripts/tests/verify_install.sh` — 8 PASS |

---

## 8. Evidence Integrity Approach

Original log files are **never modified**. All enrichment is additive and written to a separate location.

**Architectural controls (primary):**
- Source evidence under `/cases/` (or equivalent) accessed read-only by the enrichment process — never written to
- Enriched output written exclusively to `./analysis/` and `./exports/` — never the same path as source evidence
- `ntp_enricher.py` safe writer rejects any output path under `/cases/`, `/mnt/`, or `/media/` at the code level
- SHA-256 of the source CSV verified before and after enrichment; mismatch halts the run and logs to `forensic_audit.log`

**Prompt-based controls (secondary):**
- Agent instructed not to write to source paths; any attempt is refused and logged
- `ntp_assumption = true` cases are surfaced explicitly so analysts can review before including in a legal submission

**Spoliation testing:**
The smoke test harness (`smoke_ntp_agent.sh` Scene 4) verifies the source fixture SHA-256 is unchanged before and after every run. Scene 5 verifies that `--output /cases/test.csv` exits non-zero. Results — including any failure modes — are documented in `dataset.md`.

---

## 9. Constraints and Tradeoffs

| Constraint | Decision |
|---|---|
| Python only | All enrichment logic in Python; SIFT toolchain (already Python/Go-based) compatible |
| No external Python dependencies beyond stdlib | `pytest`, `pandas`, `ntplib` only — no Pydantic, no heavy ML frameworks; keeps install friction low on air-gapped workstations |
| Portability | Runs on any SIFT workstation (local VM or remote); `pip install -r requirements.txt` + `bash install.sh` is the full setup |
| Evidence integrity | Source evidence accessed read-only; architectural controls (safe writer, forbidden path checks) are primary — no dependency on prompt restrictions for data safety |
| Claude API cost | API calls batched per-case, not per-event, to keep token usage proportional to case size |

---

## 10. Open Questions

- [x] **Historical NTP drift data:** ~~Is there a `w32tm` or `chronyc` log on the test workstation?~~ **Resolved** — varies per case. The agent checks for NTP logs at runtime as the first step in Phase 2 resolution (§4). If present, `ntp_offset_s` is derived from them; if not, the assumption fallback applies (§6.1).
- [x] **NIST ITS API:** **Resolved** — default uses `time.nist.gov` over UDP/TCP port 123 (unencrypted). Production deployments should use the NIST HTTPS API with the analyst's API key. See caveat §6.6.
- [x] **Analyst prompt mode:** ~~Interactive CLI prompt (blocking) vs. a `--ntp-source` flag for fully autonomous runs?~~ **Resolved** — see §4 Phase 2 Detail: CLI flags `--ntp-source` and `--skip-ntp` are supported; interactive prompt is the fallback when neither flag is provided.
- [x] **Plaso output field names:** ~~Confirm exact field names expected by the SIFT Plaso pipeline before finalizing schema.~~ **Resolved** — existing columns (`date`, `time`, `timezone`, `filename`, etc.) are preserved as-is; new fields (`ntp_source`, `nist_time`, `ntp_offset_s`, `ntp_assumption`, `nist_delta_s`) are appended. See §2.

---

## 11. Build Sequence

This specification describes the forensic requirement and design (§1–§10).

The step-by-step implementation sequence that realizes this design is documented in `PROMPTS.md` (P-00 through P-10). Refer to that file to:
- Execute the 11-prompt Claude Code build sequence
- Understand the TDD test strategy and acceptance gates
- See the complete file map and agent-loop architecture

Link between spec and implementation:
- Spec §4 "Agent Processing Flow" (Phases 1–3) → PROMPTS.md §P-03 through P-06 (resolution tree, enrichment, SKILL.md)
- Spec §5 "Deployment Architecture" → PROMPTS.md §P-08 (settings.json wiring)
- Spec §8 "Evidence Integrity" → PROMPTS.md §P-04 (safe writer) and §P-09 (spoliation test)
- Spec §9 "Constraints and Tradeoffs" → PROMPTS.md §P-00 (dependency pinning) and §P-10 (install verification)

See also `IMPLEMENTATION.md` for the narrative architecture and design rationale.
