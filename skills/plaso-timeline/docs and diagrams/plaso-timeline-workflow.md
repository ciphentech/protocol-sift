# Plaso Timeline Workflow

```mermaid
flowchart TD
    %% ── Entry Point ───────────────────────────────────────────────
    User(["Analyst"])
    SIFT["SIFT Workstation\nClaude Code CLI + SIFT tools"]

    User -->|"starts Claude Code session\non SIFT workstation"| SIFT

    %% ── Agent Startup ─────────────────────────────────────────────
    subgraph AgentBoot["Claude Code Agent — Session Init"]
        GlobalMD["Load global/CLAUDE.md\n(DFIR Orchestrator role +\ntool routing table)"]
        CaseMD["Load case CLAUDE.md\n(evidence paths + IOCs)"]
    end

    SIFT --> GlobalMD
    GlobalMD --> CaseMD

    %% ── Plaso Timeline Skill ──────────────────────────────────────
    subgraph PlasoSkill["Skill: plaso-timeline  (SKILL.md)"]
        direction TB
        P1["§1 Verify Evidence\npinfo.py / file command\n(read-only)"]
        P2a["§2a Full Ingest\nlog2timeline.py\n--parsers win10 / linux\n--timezone UTC"]
        P2b["§2b One-Step\npsteal.py\n(no .plaso file)"]
        P2c["§2c Targeted Ingest\nspecific paths / parsers"]
        P3["§3 Inspect Storage\npinfo.py -v\n(verify parser hits)"]
        P4["§4 Filter & Export\npsort.py → l2tcsv / JSON\ndate + keyword filters"]
        P5["§5 Merge (optional)\npsort.py multi-.plaso input"]
        P4b["§4b NTP Time Enrichment\n→ hand off to NTP skill"]

        P1 --> P2a & P2b & P2c
        P2a & P2b & P2c --> P3
        P3 --> P4
        P4 --> P5
        P4 --> P4b
    end

    CaseMD --> P1

    %% ── NTP Enrichment Skill ──────────────────────────────────────
    subgraph NTPSkill["Skill: ntp-enrichment  (SKILL.md — P-06)"]
        direction TB
        N1["Step 1 — Locate psort export\nls ./exports/CASE_timeline.csv"]
        N2["Step 2 — Probe for NTP logs\ngrep EID 259 / 260 / 37\n(ALWAYS run first)"]
        N3["Step 3 — NTP Source Resolution\n(only if no NTP logs found)\nask analyst once or assume default"]
        N4["Step 4 — Run Enrichment\nntp_enricher.py\n--input ... --output ..."]
        N5["Step 5 — Read Manifest JSON\ncat analysis/CASE_ntp_manifest.json"]
        N6{"rubric_pass?"}
        N7["Step 7 — Verify & Summarise\nprint NTP source, offset,\nntp_assumption, nist_time range"]

        N1 --> N2
        N2 -->|"EID logs found\nskip to Step 4"| N4
        N2 -->|"no NTP logs"| N3
        N3 --> N4
        N4 --> N5
        N5 --> N6
        N6 -->|"true"| N7
    end

    P4b --> N1

    %% ── Self-Correction Loop ──────────────────────────────────────
    subgraph SelfCorrect["Self-Correction Loop (Step 6) — max 3 iterations"]
        direction TB
        SC1{"suggested_corrective\n_action"}
        SC_relax["relax-assumption\nRe-run Step 2 grep\nRe-run Step 4 without\n--ntp-source flag"]
        SC_recheck["recheck-offset\ngrep 'Phase Offset'\nConfirm value in artifact\nDocument in caveats.txt"]
        SC_escalate["escalate-to-operator\nWrite CASE_ntp_caveats.txt\nDo NOT loop further"]
        IterCap["Iteration cap (3)\n→ escalate-to-operator\nregardless of action"]

        SC1 -->|"relax-assumption"| SC_relax
        SC1 -->|"recheck-offset"| SC_recheck
        SC1 -->|"escalate-to-operator\nor iter ≥ 3"| SC_escalate
        SC_relax -->|"re-run iter N+1"| N4
        SC_recheck -->|"re-run iter N+1"| N4
        IterCap --> SC_escalate
    end

    N6 -->|"false"| SC1

    %% ── Python Tool Layer ─────────────────────────────────────────
    subgraph PythonTools["Python Tools (deterministic, testable)"]
        Resolver["ntp_resolver.py\nNTPContext dataclass\nConfidenceRank (1–6)\nEID 35/260 extraction\nresolve_ntp_source()"]
        Enricher["ntp_enricher.py\nenrich() — 5 new fields\nvalidate_and_correct()\nwrite_manifest()\nsafe writer (no /cases/ writes)"]
        ManifestJSON["analysis/CASE_ntp_manifest.json\nrubric_pass · rubric_failures\nsuggested_corrective_action\niteration number"]
        AuditLog["analysis/forensic_audit.log\n(Stop hook writes on session end)"]
    end

    N3 --> Resolver
    N4 --> Enricher
    Enricher --> ManifestJSON
    ManifestJSON --> N5
    SC_relax & SC_recheck --> AuditLog

    %% ── Outputs ───────────────────────────────────────────────────
    subgraph Outputs["Case Outputs"]
        EnrichedCSV["exports/CASE_timeline_enriched.csv\nsorted on nist_time\n+5 NTP fields appended"]
        CaveatsFile["analysis/CASE_ntp_caveats.txt\n(assumption flags for legal review)"]
        IterManifests["analysis/CASE_ntp_manifest.iterN.json\n(prior iterations preserved)"]
    end

    N7 --> EnrichedCSV
    SC_escalate --> CaveatsFile
    N4 --> IterManifests

    %% ── Evidence Integrity ────────────────────────────────────────
    CaseEvidence[("Case Evidence\n(disk image, logs, memory)\nread-only source")]
    CaseEvidence -->|"read-only"| P1
    CaseEvidence -->|"read-only"| Enricher

    %% ── Styling ───────────────────────────────────────────────────
    classDef agent fill:#dce8ff,stroke:#3a6bc7,stroke-width:2px
    classDef skill fill:#e8f5e9,stroke:#388e3c,stroke-width:2px
    classDef tool fill:#fff3e0,stroke:#f57c00,stroke-width:2px
    classDef output fill:#fce4ec,stroke:#c2185b,stroke-width:2px
    classDef infra fill:#ede7f6,stroke:#7b1fa2,stroke-width:2px
    classDef decision fill:#fff9c4,stroke:#f9a825,stroke-width:2px

    class GlobalMD,CaseMD agent
    class P1,P2a,P2b,P2c,P3,P4,P4b,P5 skill
    class N1,N2,N3,N4,N5,N7 skill
    class SC_relax,SC_recheck,SC_escalate,IterCap agent
    class Resolver,Enricher,ManifestJSON,AuditLog tool
    class EnrichedCSV,CaveatsFile,IterManifests output
    class SIFT,CaseEvidence infra
    class N6,SC1 decision
```

## Legend

| Color | Layer |
|-------|-------|
| Blue | Claude Code Agent (reasoning, routing, self-correction) |
| Green | Skill instructions (SKILL.md — agent decision procedures) |
| Orange | Python tools (deterministic, testable — the agent's hands) |
| Pink | Case outputs |
| Purple | SIFT workstation & evidence store |
| Yellow | Decision points |

## Key Design Points

- **Claude Code IS the agent.** The Python scripts are tools it calls via `Bash()` — not the agent itself.
- **SKILL.md files are the decision procedure.** The agent reads them and executes step-by-step with no human intervention between steps.
- **Self-correction is capped at 3 iterations** to prevent infinite loops; iteration 4 always escalates.
- **Evidence integrity is architectural**, not prompt-based: source evidence is never written to; the enricher's safe writer rejects writes to source paths.
- **`ntp_assumption=true` rows must be disclosed** in any legal or regulatory submission (ISC2 requirement).
