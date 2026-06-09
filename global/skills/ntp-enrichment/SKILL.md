# Skill: NTP Time Enrichment

Anchor every Plaso event timestamp to NIST UTC by recovering NTP sync evidence from the
artifact and computing an inferred clock offset, so events from different log sources can
be correlated on one authoritative reference. This skill is documentation only: the agent
reads it and runs the tools in `analysis-scripts/`. Source evidence under
`/cases/`, `/mnt/`, `/media/` is read-only (SPEC §8); enriched output is written to
`./exports/`. The original Plaso CSV is never modified.

## When to use this skill
- A case includes a host whose clock offset matters for ordering events across sources.
- A timeline is destined for a forensic/legal package (the accuracy report documents the
  time anchor per ISC2 chain-of-custody guidance).
- Typically run **after the `plaso-timeline` skill's `psort.py` CSV export** — that
  skill can hand off to this one for NIST anchoring.

## Tools

| Tool | Purpose |
|------|---------|
| `bash ~/.claude/analysis-scripts/tlcorr_pipeline.sh` | **Primary** — orchestrated pipeline: sibling-repo check, stage banners, integrity verification, accuracy report |
| `python3 ~/.claude/analysis-scripts/ntp_enricher.py` | Direct enricher — resolve → NIST query → enrich → self-correct (called by the pipeline) |

Pipeline CLI flags (SPEC §4 CLI Flags):
```
--input  <csv>    Plaso l2tcsv export path (source, read-only)
--case   <id>     Case identifier (used in output filenames)
--outdir <path>   Output root; exports/, analysis/, reports/ created here
--ntp-source <v>  Skip Phase 2 prompt; cross-checked against artifact logs
--skip-ntp        Pass original columns through unchanged (NOT NIST-anchored;
                  a chain-of-custody warning is emitted and recorded)
```

## Workflow

### Phase 2 — NTP source resolution (SPEC §4 Phase 2 Detail)
Before computing timestamps, populate `ntp_source` and `ntp_assumption`. Walk the tree and
stop at the first match:
1. Artifact NTP logs (EID 35/260) → `confidence_rank = 1` (LOG_DERIVED), `ntp_assumption = false`
2. `--ntp-source` consistent with the artifact → rank 2, `ntp_assumption = false`
3. `--ntp-source`, no logs to cross-check → rank 3, `ntp_assumption = false`
4. Cloud default (AWS → 169.254.169.123, Azure → time.windows.com) → rank 4, assumption true
5. On-prem Windows (domain → "Domain Controller"; standalone → time.windows.com) → rank 5, assumption true
6. On-prem Linux distro default → rank 6, assumption true

### NIST query (SPEC §3)
Validate the source against a public NIST/NTP server (regional → global → pool). If every
server is unreachable, **halt** with a chain-of-custody warning (SPEC §3.2) — verify
outbound UDP/123.

### Phase 1 — enrichment (SPEC §2.2)
Append exactly five columns, in spec order:
`ntp_source, nist_time, ntp_offset_s, ntp_assumption, nist_delta_s`. Sort on `nist_time`.

### Phase 3 — self-correction loop (SPEC §4 Phase 3)
Check every offset against the **plausibility bound ±1000 s**. On an implausible value,
**re-resolve the NTP source** and retry, bounded to 3 iterations. If still implausible,
halt and list the **unresolved rows** with the basis for each.

## Outputs (SPEC §2 and §2.3)
| Output | Path |
|--------|------|
| Enriched Plaso CSV | `<outdir>/exports/<case>_correlated.csv` |
| Accuracy report (JSON) | `<outdir>/analysis/<case>_accuracy.json` |
| Forensic audit log | `<outdir>/analysis/forensic_audit.log` |

The accuracy report contains, per SPEC §2.3: `rows_total`, `rows_assumption_true`,
`confidence_rank_distribution`, `assumption_bases` (reproducible), `spec_caveats_applicable`,
and any `unresolved_rows` from the Phase 3 halt summary.

## When to halt and ask the analyst
- Cloud vs on-prem cannot be inferred and no `--ntp-source` was provided.
- No NIST/NTP server reachable (SPEC §3.2).
- Phase 3 iteration cap reached with unresolved rows — report the implausible offsets and
  ask the analyst for the correct NTP source or a corrected offset value.
- `--skip-ntp`: emit the chain-of-custody warning and pass the timeline through unenriched.

## Notes
- Sort cross-source correlation on `nist_time`, never on `date`/`time`.
- Every `ntp_assumption = true` row MUST be disclosed in legal/regulatory submissions (SPEC §6.4).
- `nist_delta_s == ntp_offset_s` by design (SPEC §2.2).
- NTP transport is unencrypted — proof-of-concept only (SPEC §6.6).
