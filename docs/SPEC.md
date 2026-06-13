# Protocol SIFT — Time Sync Normalization Feature
## Hackathon Submission Spec

**Submission Deadline:** June 15, 2026  
**Team Size:** 2 (Backend Developer + Network/Security Automation Engineer)  
**Architecture Pattern:** Direct Agent Extension (Claude Code / OpenClaw)  
**Project:** `hackasans-correlator` — `ciphentech/hackasans-correlator`  
**Runtime:** Python on AWS (`us-west-2`)  
**Budget:** $150 through June 15, 2026  
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

### 2.3 Accuracy Report

Alongside the enriched timeline the agent emits an accuracy report covering the run as a whole. This is the persistent record analysts attach to a submission package per §6.4. At minimum it contains:

- Total number of events processed
- Number of events with `ntp_assumption = true`
- Distribution of confidence ranks observed (per the §4 Phase 2 Detail table)
- The basis on which each assumed `ntp_source` was selected, so every assumption is reproducible
- Any case-level caveats from §6 that apply to this run

A condensed version of the same summary is also printed at the end of every run.

---

## 3. NIST Time Source

Generating a Plaso timeline with an authoritative UTC reference requires a query to a public time server. The agent queries it directly to validate the NTP source and derive a clock offset; the response is the current time service state, not a direct historical timestamp for past events.

### 3.1 How the Query Works

The agent queries a public time server over the NTP protocol (UDP/TCP port 123). **No API key, registration, or credential is required** — public NIST and NTP-pool servers answer anonymous time requests.

- **Default (regional):** the NIST server closest to the deployment region (`time-a-wwv.nist.gov` / `time-b-wwv.nist.gov` for the `us-west-2` proof of concept). Regional selection reduces query latency and is the convention for US-based forensic work.
- **Fallback (global):** `time.nist.gov` (anycast) and `pool.ntp.org` if the regional server is unreachable.
- The query requires only outbound UDP/123 from the SIFT workstation (provided by the NAT Gateway; see §5).
- No secret needs to be stored, rotated, or injected at runtime.
- See caveat §6.6 for the transport-security limitations of unencrypted NTP.

### 3.2 What Happens If the Time Server Is Unreachable

If neither the regional nor the global time server can be reached when a Plaso timeline is requested, the agent will:
1. Halt before any timestamp computation begins
2. Display an error indicating the time service could not be reached, and direct the analyst to verify outbound UDP/123 connectivity from the SIFT workstation
3. Warn the analyst that proceeding without a successful time-server query means timestamps will not be anchored to an authoritative time source. Per ISC2 guidance on digital forensics and chain of custody, timeline evidence may be challenged or excluded in legal proceedings if time sync differences between the source system and other provided log sources are not documented and submitted alongside the evidence. The analyst may continue, but must document this limitation in any evidence package.

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
                                      │   └─ Azure (Linux or Windows)
                                      │         ntp_source = "time.windows.com"
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
| 4 | Cloud provider default (derived from hosting environment) | `true` |
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

The loop is bounded by a small fixed maximum iteration count. If the agent still cannot produce a plausible offset within that bound, it halts and surfaces a summary listing the rows that remained unresolved and the basis on which each was rejected. This bound prevents infinite loops on pathological inputs and ensures every run completes in a predictable amount of time.

---

## 5. Infrastructure Architecture

### AWS Components (Terraform — `hackasans-correlator`, `us-west-2`)

The infrastructure is fully defined in `infra/terraform/` and deployed via GitHub Actions OIDC (no long-lived credentials).

```
┌──────────────────────────────────────────────────────────────────┐
│                     VPC: 10.2.0.0/16 (prod)                      │
│                                                                  │
│  Public Subnets (.1, .2, .3)      Private Subnets (.10, .11, .12)│
│  ┌─────────────────────┐          ┌───────────────────────────┐  │
│  │  Bastion Host       │  SSM     │  SIFT Workstation         │  │
│  │  Amazon Linux 2023  │─────────►│  Ubuntu 22.04 (t3.xlarge) │  │
│  │  t2.micro           │  double  │  100 GB gp3 root          │  │
│  │  SSM + EC2 Connect  │  hop     │  1 TB gp3 data volume     │  │
│  └─────────────────────┘          │                           │  │
│           │                       │  Installed:               │  │
│           │                       │  • CAST + SIFT toolchain  │  │
│           │                       │  • Claude Code CLI        │  │
│           │                       │  • Node.js 22             │  │
│           │                       │  • CloudWatch agent       │  │
│           │                       └───────────────────────────┘  │
│           │                                    │                 │
│  NAT Gateway (EIP) ◄───────────────────────────┘                 │
└──────────────────────────────────────────────────────────────────┘
         │
         ▼
┌─────────────────────────────────────────────┐
│  AWS Services                               │
│  • Cognito (User Pool + Identity Pool)      │
│    - MFA enforced (TOTP)                    │
│    - Admin-only user creation               │
│  • CloudWatch Logs (90-day retention)       │
│    - /ec2/hackasans-prod/sift               │
│    - /ec2/hackasans-prod/bastion            │
│    - /vpc/hackasans-prod/flow-logs          │
│  • S3 (output bucket)                       │
│  • GitHub Actions OIDC (no static keys)     │
└─────────────────────────────────────────────┘
```

### Access Path

Analysts access the SIFT workstation via a **double-hop SSM session** — no inbound ports are open on either instance:

```
Analyst browser
    │  Cognito auth (MFA required)
    ▼
AWS SSM → Bastion (t2.micro, public subnet)
    │  ssm start-session → SIFT instance ID
    ▼
SIFT Workstation (t3.xlarge, private subnet)
    └── Claude Code + SIFT tools execute here
```

### Security Boundary Summary

| Boundary | Type | Enforcement |
|---|---|---|
| No inbound ports on SIFT | Architectural | Security group: zero ingress rules |
| No inbound ports on Bastion (except EC2 Instance Connect IPs) | Architectural | Security group: ingress scoped to AWS EC2 Connect CIDR only |
| Source logs read-only | Architectural | EBS volume mounted read-only to enrichment process; source path never written to |
| Enriched output never overwrites source | Architectural | Enriched CSV written to `exports/<case>_correlated.csv`; source at `exports/<case>_timeline.csv` — distinct filenames; reports go to `analysis/` |
| IMDS v2 enforced | Architectural | `http_tokens = required` on both instances |
| EBS volumes encrypted | Architectural | `encrypted = true` on all volumes |
| Prompt restriction on log modification | Prompt-based | Secondary control only — architectural controls above are primary |
| MFA on all analyst access | Architectural | Cognito: `mfa_configuration = "ON"`, TOTP required |

---

## 6. Caveats — Time Sync Limitations

Per ISC2, the Plaso timeline will include the difference in time from NIST. NIST is assumed to be the time source of truth in the US. For this proof of concept, we selected NIST. The next iteration or improvement would be to select other time sources of truth for those outside the US.

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

### 6.6 NIST Transport Security (Proof of Concept Limitation)

This proof of concept queries public NTP servers using the unencrypted NTP protocol (UDP/TCP port 123). This means:
 - The time response is not authenticated and could theoretically be tampered with in transit.
 - The response reflects the current time service state, not the historic time state at the moment each event was generated.
 - This transport is acceptable only for a hackathon proof of concept in a controlled environment.
 - **This is not acceptable for production forensic use or legal submissions.**

**For production deployments:** an authenticated time transport (e.g., NTS — Network Time Security, RFC 8915, or an internal Stratum-1 appliance) is required for any timeline submitted as legal evidence. Selecting and configuring that transport is out of scope for this proof of concept.

---

## 7. Hackathon Submission Checklist

| # | Requirement | Status | Notes |
|---|---|---|---|
| 1 | GitHub repo — `ciphentech/hackasans-correlator`, MIT license | ☑ | LICENSE file confirmed present |
| 2 | Demo video (≤5 min, live terminal on SIFT workstation, audio, self-correction shown) | ☐ | Storyboard complete; record Jun 13; update README link |
| 3 | Architecture diagram — identifies the architectural pattern (Direct Agent Extension via Claude Code / OpenClaw) and shows how components connect: agent, SIFT tools, data sources, output pipeline, SSM access path, trust boundaries; prompt-based vs. architectural guardrails clearly distinguished | ☑ | `docs/component-diagram.jpg` embedded in README with caption distinguishing architectural vs. prompt-based guardrails (commit 0e94e68) |
| 4 | Written project description (Devpost: what/how/challenges/learned/next) | ☐ | Draft Jun 13; publish; replace example.com/devpost in README |
| 5 | Dataset documentation (logs tested against, source, findings) | ☑ | `docs/dataset.md` — SRL-2018 host inventory, EID 35/260 artifacts, findings summaries, reproducibility paths (commit 0e94e68) |
| 6 | Accuracy report (FPs, misses, hallucinations, evidence integrity, spoliation testing, `ntp_assumption` failure modes) | ☑ | `docs/ACCURACY-REPORT.md` complete; `docs/SECURITY-REVIEW.md` adds 7 agent-layer security findings; error-handling pass (branch `fix/error-handling-reliability`): preflight validation, emit() OSError guard, Scene 8 timeout + stderr capture |
| 7 | Try-it-out instructions — judges access the hosted SIFT workstation as the live deployment path (Cognito-MFA → SSM double-hop into the SIFT EC2); dependencies are pre-installed on the workstation | ☑ | README try-it restructured: local SIFT install is primary path (no AWS credentials), AWS access documented as available on request (commit 0e94e68) |
| 8 | Agent execution logs (tool calls, timestamps, token usage, iteration traces per self-correction loop) | ☐ | Infrastructure built (agent_trace.jsonl, token_usage.json, forensic_audit.log); commit sample logs from demo run into docs/demo/sample-logs/ after Jun 13 recording |

---

## 8. Evidence Integrity Approach

Original log files are **never modified**. All enrichment is additive.

**Architectural controls (primary):**
- Source evidence stored on the EBS data volume (1 TB, `gp3`, encrypted) under `/cases/` — mounted read-only to the enrichment process
- Enriched timeline written to the same `exports/` directory as the source evidence, but always as a new file with a distinct name (`<case>_correlated.csv`); the source file (`<case>_timeline.csv`) is never overwritten or deleted
- Analysis reports and audit logs written to a separate `analysis/` directory — never to the `exports/` path
- EBS volume is encrypted at rest; access is scoped to the SIFT instance only via IAM instance profile
- All access logged to CloudWatch (`/ec2/hackasans-prod/sift`, 90-day retention) and VPC flow logs

**Prompt-based controls (secondary):**
- Agent instructed not to write to source paths; any attempt is refused and logged
- `ntp_assumption = true` cases are surfaced explicitly so analysts can review before including in a legal submission

**Spoliation testing:**
The team will test what happens when the prompt restriction is bypassed (e.g., crafted input attempts to direct the agent to overwrite source files). Results — including any failure modes — will be documented in the accuracy report. Finding and documenting failure modes is a submission strength, not a weakness.

---

## 9. Constraints and Tradeoffs

| Constraint | Decision |
|---|---|
| AWS `us-west-2`, free-tier preferred | Bastion: `t2.micro`; SIFT: `t3.xlarge` (required for SIFT toolchain); NAT Gateway is the primary cost item — monitor usage |
| $150 budget through June 15 | Claude API calls batched (per-case, not per-event); NAT Gateway data transfer is the main variable cost risk |
| 2-person team, AI novices | Claude Code on SIFT as the primary agent runtime; OpenClaw extension pattern as on-ramp |
| Python only | All enrichment logic in Python; SIFT toolchain (already Python/Go-based) compatible |
| Portability / low friction | Everything runs on the SIFT EC2 via SSM — no local tool installs required for judges; `pip install -r requirements.txt` + Claude Code CLI already present |
| Evidence integrity | EBS source volume mounted read-only to enrichment process; no architectural dependency on prompt restrictions for data safety |

---

## 10. Open Questions

- [x] **Historical NTP drift data:** ~~Is there a `w32tm` or `chronyc` log on the test workstation?~~ **Resolved** — varies per case. The agent checks for NTP logs at runtime as the first step in Phase 2 resolution (§4). If present, `ntp_offset_s` is derived from them; if not, the assumption fallback applies (§6.1).
- [x] **NIST ITS API:** **Resolved** — proof of concept queries public NIST/NTP servers anonymously over UDP/TCP port 123 (unencrypted). No API key or credential is required. Production deployments need an authenticated time transport (e.g., NTS); see caveat §6.6.
- [x] **Analyst prompt mode:** ~~Interactive CLI prompt (blocking) vs. a `--ntp-source` flag for fully autonomous runs?~~ **Resolved** — see §4 Phase 2 Detail: CLI flags `--ntp-source` and `--skip-ntp` are supported; interactive prompt is the fallback when neither flag is provided.
- [x] **Plaso output field names:** ~~Confirm exact field names expected by the SIFT Plaso pipeline before finalizing schema.~~ **Resolved** — existing columns (`date`, `time`, `timezone`, `filename`, etc.) are preserved as-is; new fields (`ntp_source`, `nist_time`, `ntp_offset_s`, `ntp_assumption`, `nist_delta_s`) are appended. See §2.
- ] **NAT Gateway cost:** Deferred — not a concern for this proof of concept.

---

## 11. Build Sequence

This specification describes the forensic requirement and design (§1–§10).

The step-by-step implementation sequence that realizes this design is documented in `PROMPTS.md` (P-00 through P-10). Refer to that file to:
- Execute the 11-prompt Claude Code build sequence
- Understand the TDD test strategy and acceptance gates
- See the complete file map and agent-loop architecture
- Review the demo-video script

Link between spec and implementation:
- Spec §4 "Agent Processing Flow" (Phases 1–3) → PROMPTS.md §P-03 through P-06 (resolution tree, enrichment, SKILL.md)
- Spec §5 "Infrastructure Architecture" → PROMPTS.md §P-08 (settings.json wiring)
- Spec §8 "Evidence Integrity" → PROMPTS.md §P-04 (safe writer) and §P-09 (spoliation test)
- Spec §9 "Constraints and Tradeoffs" → PROMPTS.md cost tracking and contingency

See also `ARCHITECTURE.md` for the narrative architecture and design rationale.
