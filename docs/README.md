# Protocol SIFT — NTP Enrichment

> Clock-skew normalization for forensic timelines, with autonomous self-correction and per-row admissibility disclosure.

**SANS FindEvil Hackathon submission · June 15, 2026 · MIT License**

![Status](https://img.shields.io/badge/status-hackathon%20submission-blue)
![License](https://img.shields.io/badge/license-MIT-green)
![Python](https://img.shields.io/badge/python-3.10+-blue)
![AWS](https://img.shields.io/badge/AWS-us--west--2-orange)

---

## ▶ Demo (90 seconds)

**[Watch the demo →](https://example.com/demo-link)**  *(replace with your video URL before submission)*

The agent probes a real artifact, hits a plausibility check, self-corrects, and produces a NIST-anchored timeline — start to finish in ninety seconds.

---

## The problem

When DFIR analysts correlate events across Windows hosts, Linux servers, and network devices, undocumented clock skew is routinely the difference between *"this happened first"* and *"we don't know."* Per ISC2 guidance on digital forensics and chain of custody, **time-source differences between log sources must be documented and submitted alongside evidence**, or the timeline may be inadmissible.

## What this delivers

**Evidence integrity.** Source case files are read-only. All enrichment output goes to a separate directory. Any attempt to write back to the evidence area — including attempts driven by crafted input — is blocked at the architectural level and logged. (FEATURES §1, SPEC §8)

**Time anchor pipeline.**
- *Artifact scan* — inspects every case for Windows Time Service events (EIDs 35/37/259/260), `w32tm /query /status` output, `chronyc tracking`, and syslog NTP entries. Recovered records are the highest-confidence input for clock-offset computation. (FEATURES §2)
- *NIST query* — contacts the regional NIST time server (`time-a-wwv.nist.gov` for `us-west-2`), falls back to `time.nist.gov` / `pool.ntp.org` on failure, and halts before any timestamp computation if every server is unreachable — printing a chain-of-custody warning per ISC2 guidance. (FEATURES §3, SPEC §3)
- *NTP source resolution* — resolves which NTP server the originating workstation used, following a six-level confidence ranking from recovered artifact logs (rank 1) down to OS-default fallback (rank 6). (FEATURES §4, SPEC §4 Phase 2)
- *Enriched timeline* — appends five columns to every Plaso row: `ntp_source`, `ntp_offset_s`, `nist_delta_s`, `nist_time`, `ntp_assumption`. Re-sorts on `nist_time` (NIST UTC). (FEATURES §5)
- *Accuracy report* — lists every assumption made, the confidence rank of each, and the basis for each `nist_time` computation. Required for ISC2-compliant chain-of-custody submissions. (FEATURES §8, SPEC §2.3)

**Operator controls.**
- `--ntp-source <value>` skips the interactive prompt and uses the supplied value directly. (FEATURES §6, SPEC §4)
- `--skip-ntp` bypasses enrichment entirely and outputs a standard Plaso timeline; prints a legal warning that the result is not NIST-anchored. (FEATURES §6, SPEC §4)
- *Self-correction loop* — after the initial pass the agent checks every computed offset against a ±1000 s plausibility bound. Implausible offsets trigger re-resolution and re-enrichment, up to three iterations, then escalation with a per-row summary. (FEATURES §7, SPEC §4 Phase 3)
- *Smoke test suite* — stdlib-only Python runner covering all nine features against synthetic fixtures; all cases must pass before a PR or demo. (FEATURES §9)

## How it works

Three phases run for every enrichment request (see SPEC §4 for the full flow):

```
   Plaso l2tcsv  ──►  Agent reads SKILL.md
                            │
           ┌────────────────┼────────────────┐
           ▼                ▼                ▼
       Phase 1          Phase 2          Phase 3
       Enrich         NTP Resolve      Self-Correct
       timeline       (artifact logs   (±1000 s bound;
       (5 new cols,    → analyst ask    ≤ 3 iter, then
        re-sort on     → OS default)    escalate)
        nist_time)          │
                            ▼
                   6-level confidence rank
                   ntp_assumption flag set
                            │
                            ▼
                    Read manifest JSON
                            │
                ┌───────────┴───────────┐
                ▼                       ▼
       rubric_pass: true       rubric_pass: false
                │                       │
                ▼                       ▼
       Enriched timeline       Re-run (Phase 2→3)
       + accuracy report       or escalate
```

Phase 2 can be overridden with `--ntp-source <value>` (skips the interactive prompt) or `--skip-ntp` (bypasses enrichment entirely, outputs a plain Plaso timeline with a legal warning). The full NTP resolution decision tree is in SPEC §4 Phase 2 Detail.

The runtime is **Claude Code** on a SIFT EC2 workstation in private subnet. The Python tools (`ntp_resolver.py`, `ntp_enricher.py`) are deterministic and unit-tested. The `SKILL.md` is the agent's decision procedure — not documentation; *executable reasoning instructions* Claude Code reads at every session start.

![Protocol SIFT Architecture](docs/component-diagram.jpg)

*Two guardrail types are in play. **Architectural guardrails** (primary, unconditionally enforced): read-only EBS mount, `ValueError("protected evidence")` raised by the enricher on any `/cases/` write attempt, SHA-256 integrity check after every run, encrypted EBS volumes, CloudWatch session logging. **Prompt-based guardrails** (secondary, instructed): the agent reads `SKILL.md` and is instructed not to write to source paths — but if it ignored that instruction, the architectural controls above would still refuse the write and log the attempt. See [ARCHITECTURE.md](docs/ARCHITECTURE.md) and [SPEC.md §5 Security Boundary Summary](docs/SPEC.md) for the full table.*

## Try it

**Option 1 — Local SIFT workstation (primary judge path, no AWS credentials needed):**

Any Ubuntu 22.04+ SIFT workstation or VM. Python 3.10+, Claude Code CLI, and
`ANTHROPIC_API_KEY` are the only prerequisites.

```bash
# Clone the skill repo and install onto the SIFT box
git clone https://github.com/ciphentech/protocol-sift.git
cd protocol-sift && bash install.sh

# Navigate to your case directory and start the agent
cd /cases/<your-case> && claude

# In the agent session, request enrichment
> Enrich the timeline for case RD01.

# Provide NTP source directly (skips the interactive prompt)
> Enrich the timeline for case RD01 --ntp-source time.windows.com

# Skip NTP enrichment entirely (outputs standard Plaso timeline only)
> Enrich the timeline for case RD01 --skip-ntp
```

**Option 2 — AWS-hosted SIFT workstation (available on request):**

Contact the team for Cognito credentials. Access is via MFA-enforced Cognito →
SSM double-hop (no inbound ports on the SIFT instance). See
[docs/DEPLOYMENT.md](docs/DEPLOYMENT.md) for the full access path.

The agent does the rest. Outputs land in:
- `./exports/<CASE>_timeline_enriched.csv` — Plaso timeline + five new columns
- `./analysis/<CASE>_ntp_manifest.json` — accuracy report — per-run assumption disclosure, confidence ranks, event counts; attach to every evidence package
- `./analysis/<CASE>_ntp_manifest.iterN.json` — every self-correction iteration, preserved
- `./analysis/forensic_audit.log` — per-iteration trace

To run the smoke test suite (all nine features against synthetic fixtures):

```bash
# From the protocol-sift repo on the workstation
python3 analysis-scripts/tests/smoke_test.py

# Or inside any Claude Code session in this repo
/tlcorr-smoke
```

## Repository layout

This repo (`hackasans-correlator`) hosts the **design and infrastructure.** The agent skill itself deploys to a separate repo so it can be installed onto any SIFT workstation independently of this AWS environment.

| Repo | What's in it |
|------|--------------|
| **`ciphentech/hackasans-correlator`** (here) | `SPEC.md`, `ARCHITECTURE.md`, `docs/prompts/`, Terraform under `infra/terraform/`, design notes |
| **[`ciphentech/protocol-sift`](https://github.com/ciphentech/protocol-sift)** | `skills/ntp-enrichment/SKILL.md`, `analysis-scripts/ntp_*.py`, tests, `install.sh` |

## Documentation

| Doc | What it is |
|-----|-----------|
| [`SPEC.md`](./docs/SPEC.md) | Forensic requirement, output schema, agent processing flow, evidence integrity |
| [`ARCHITECTURE.md`](./docs/ARCHITECTURE.md) | Narrative architecture and design rationale — agent vs tools, two-repo layout, AWS infrastructure |
| [`ACCURACY-REPORT.md`](./docs/ACCURACY-REPORT.md) | Submission-level self-assessment: false positives, missed artifacts, spoliation testing results, known limitations |
| [`dataset.md`](./docs/dataset.md) | SRL-2018 dataset, NTP artifacts recovered, enrichment findings, reproducibility instructions |
| [`SECURITY-REVIEW.md`](./docs/SECURITY-REVIEW.md) | Prompt and code security review: 7 findings (2 HIGH, 3 MEDIUM, 2 LOW) with file/line citations and remediation recommendations |
| [`docs/prompts/`](./docs/prompts/) | The 11-prompt Claude Code build sequence (P-00 → P-10) with TDD acceptance gates |
| [`infra/terraform/`](./infra/terraform/) | AWS deployment — VPC, SIFT workstation, IAM/OIDC, CloudWatch, Cognito |

## Contributing

See [CONTRIBUTING.md](./CONTRIBUTING.md) — contributor onboarding, the
prompts-and-design-docs-first change workflow, test gates, and the PR
checklist all live there.

## Team

Two-person team — Backend Developer + Network/Security Automation Engineer — built this in 15 days for the SANS FindEvil Hackathon. Lessons learned, including where the agent's autonomous reasoning broke down and how we caught it, are written up in the [Devpost submission](https://example.com/devpost).

## License

MIT. See [`LICENSE`](./LICENSE).

## Evidence Download Script

[`scripts/download_sr018.sh`](./scripts/download_sr018.sh) downloads the SRL-2018 SANS disk images and memory dumps from the SANS evidence repository to the SIFT workstation's `/evidence/srl-2018` directory (configurable via `OUTPUT_DIR`).

**Contributed by Kismat Kunwar.**

Usage (run once on the SIFT workstation EBS volume):

```bash
# Download only the disk images you need for the current investigation step
./scripts/download_sr018.sh step1   # wkstn-01 — initial alert host (~17 GB)
./scripts/download_sr018.sh step2   # rd-01 — lateral movement pivot (~17 GB)
./scripts/download_sr018.sh step3   # dc — domain controller (~12 GB)
./scripts/download_sr018.sh step4   # wkstn-05 — DLL hijack host (~14 GB)
./scripts/download_sr018.sh step5   # rd-02 (~17 GB)
./scripts/download_sr018.sh step6   # file server (~16 GB)
./scripts/download_sr018.sh step7   # dmz-ftp (~12 GB)

# Or download everything at once
./scripts/download_sr018.sh all

# HEAD check only — no download, shows file sizes
./scripts/download_sr018.sh test
```

## Acknowledgments

[SANS FindEvil Hackathon](https://www.sans.org/) · [Plaso (log2timeline)](https://plaso.readthedocs.io/) · the [SIFT Workstation](https://www.sans.org/tools/sift-workstation/) · [NIST Internet Time Service](https://www.nist.gov/pml/time-and-frequency-division/time-services/internet-time-service-its) · ISC2 digital-forensics guidance · [Claude Code](https://docs.claude.com/en/docs/claude-code/overview).
