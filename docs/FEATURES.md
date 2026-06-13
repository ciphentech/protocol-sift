# Features — Time Sync Normalization

Product-level view of what this feature does for the analyst. Each entry
describes what the analyst experiences, not how it is built. Forensic and
legal requirements live in `SPEC.md`; this file is the user-facing view of
those requirements.

Every feature below is drawn directly from `SPEC.md`. No invented features.

Features are listed in **recommended implementation order** — foundations
first, then the two independent input sources, then the consumers that
combine them, then the audit layer that wraps everything.

---

## 1. Evidence Integrity Guarantee

**Description.** Original case files are never modified. All enrichment
output is written to a separate location, and multiple layers of protection
prevent accidental or malicious overwriting — including attempts driven by
crafted input.

**User flow.**
1. Analyst places case data in the designated evidence area on the workstation.
2. Agent reads from that area but cannot write to it.
3. All output goes to a separate output area.
4. Any attempt to write back to the evidence area — by the agent or by anything driving the agent — is refused and recorded.

**UI overview.** Mostly invisible — by design, the analyst sees nothing
about what doesn't happen. When a write attempt is blocked, the analyst
sees a clear refusal message in the terminal and a corresponding entry in
the agent's activity log, so spoliation attempts are visible after the
fact.

---

## 2. Artifact-Based Time Evidence Recovery

**Description.** Scans the collected case data for NTP and time-sync
records — Windows Event Log entries, `w32tm` query output, `chronyc`
tracking output, and syslog `ntpd` lines — and uses them as the
highest-confidence source for the clock offset.

**User flow.**
1. Agent automatically inspects the case data at the start of every run.
2. When matching records are found, the agent extracts the NTP peer, the stratum, and the recorded offset from each one.
3. These records become the authoritative inputs for clock-offset computation; nothing about them is invented.

**UI overview.** No direct interaction — this happens silently in the
background as the first step of the resolution flow. What the analyst sees
later is in the accuracy report (Feature 8): which records were found,
what was recovered from each, and which event rows depend on them.

---

## 3. NIST Time Reference Query

**Description.** Queries a public NIST time server to validate the assumed
NTP source and derive a live clock offset. The query is anonymous and
requires no API key, registration, or credential.

**User flow.**
1. Agent reaches out over the network to a regional NIST server appropriate to the deployment.
2. If the regional server is unreachable, the agent falls back to global NIST and public NTP-pool servers.
3. If every server is unreachable, the agent halts before any timestamp computation begins, explains the failure to the analyst, and points them at the connectivity to verify.

**UI overview.** A short status line in the terminal during the run — which
server responded, the measured offset, and the server's stratum. On total
failure, the analyst sees a halt message with a chain-of-custody warning
explaining the legal-evidence implications of proceeding without an
authoritative time anchor.

---

## 4. NTP Source Resolution

**Description.** Identifies which NTP server the originating workstation
was synchronized to. The agent uses recovered artifact evidence first, then
asks the analyst, then falls back to reasoned defaults — always recording
the confidence level.

**User flow.**
1. Analyst starts the enrichment.
2. Agent inspects the case data for any NTP-related records.
3. If records are found, the agent uses them directly and proceeds.
4. If not, the agent asks the analyst: *"Do you know the NTP source for the system being analyzed?"*
5. If the analyst doesn't know, the agent asks one follow-up: *"Was the system cloud-hosted or on-prem?"* and narrows to the cloud provider or operating system as needed.
6. The agent records the resolved source and how confident it is in that source.

**UI overview.** One or two short prompts in the analyst's terminal per case
— never more. The agent always tells the analyst which source it used, why
it picked that source, and a confidence rank from 1 (recovered from the
artifact) to 6 (operating-system default fallback). Two override controls
(see Feature 6) let the analyst skip the prompts entirely.

---

## 5. NIST-Anchored Timeline Enrichment

**Description.** Adds a single authoritative UTC timestamp to every event
in a Plaso timeline so events from different log sources can be correlated
on a common time reference. This enriched timeline is the analyst's primary
deliverable.

**User flow.**
1. Analyst points the agent at a Plaso timeline in their case directory.
2. Agent processes every event, computing a UTC-normalized timestamp anchored to NIST.
3. Agent re-orders the timeline by the new authoritative timestamp.
4. Analyst opens the enriched timeline for cross-source correlation and reporting.

**UI overview.** The analyst issues a single request inside a Claude Code
session on the SIFT workstation. The agent writes a new timeline alongside
the original. The original log files are left untouched. The new timeline
adds several columns to each row: the NTP source the workstation was
synchronized to, the NIST-anchored timestamp, the inferred clock offset,
an assumption flag, and a ground-truth delta drawn from the artifact.

---

## 6. Bypass and Override Controls

**Description.** Lets the analyst skip the interactive prompts when they
already know the NTP source, or skip the enrichment entirely when they need
the original timeline output without NIST anchoring. Both modes come with
explicit legal warnings.

**User flow.**
1. Analyst chooses a mode at the start of the run — provide the NTP source directly, or skip the enrichment.
2. Agent confirms the choice and shows any applicable warning.
3. If the enrichment is skipped, the agent prints a chain-of-custody notice explaining that the resulting timeline is not NIST-anchored and must be documented as such if submitted as legal evidence.
4. The run proceeds without further prompts.

**UI overview.** Each mode is selected via a flag on the run command. The
chosen mode and any warning are echoed at the top of the run so the analyst
is aware throughout what was bypassed.

---

## 7. Self-Correction Loop

**Description.** After the first enrichment pass, the agent checks whether
its assumptions produced plausible results. If a clock offset is
implausibly large, or the analyst supplies a correction mid-run, the agent
re-resolves the NTP source and re-runs the enrichment.

**User flow.**
1. Agent completes the initial enrichment pass.
2. Agent inspects every row's computed offset against a plausibility bound.
3. If any row exceeds the bound, or the analyst corrects an earlier answer, the agent re-resolves the NTP source with the updated information and re-runs.
4. The loop is bounded — a small fixed number of attempts. If still unresolved, the agent halts with a clear summary of which events look suspect and why.

**UI overview.** An iteration banner in the terminal showing which pass is
running and what triggered the re-run (e.g., implausible offset detected,
analyst correction supplied). A final summary lists the total number of
iterations and any rows that remained unresolved.

---

## 8. Assumption Transparency and Accuracy Report

**Description.** Every event whose NTP source was assumed rather than
confirmed from evidence is flagged in the timeline and listed in a separate
accuracy report. This is required for the timeline to be admissible as
legal evidence per chain-of-custody guidance.

**User flow.**
1. Agent finishes the enrichment.
2. Agent produces an accuracy report alongside the enriched timeline.
3. Analyst reviews which events are assumption-based, which artifacts were recovered, what confidence rank each event has, and the basis on which each timestamp was computed.
4. Before submitting the timeline as evidence, the analyst includes the report so reviewers can see what was inferred versus what was measured.

**UI overview.** A summary at the end of every run — total events
processed, events whose NTP source was assumed, the confidence ranks
observed, and any caveats that apply to this case. A persistent report
the analyst can attach to a submission package. Every assumption is
recoverable — the report shows the basis of each one so the timeline is
reproducible and auditable.
