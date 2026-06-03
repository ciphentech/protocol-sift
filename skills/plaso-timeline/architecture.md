# Architecture

## Overview

This repository contains the Protocol:SIFT skill set and supporting scripts for the Claude Code DFIR agent. Skills are installed to `~/.claude/` on any SIFT workstation and loaded automatically by Claude Code at session start.

## Protocol:SIFT Autonomous DFIR Agent Architecture

```mermaid
flowchart TD
    subgraph "Claude Autonomous Agent"
        Agent[Claude Agent<br/>Autonomous Loop]
        Reasoning[Reasoning Loop]
        SelfCorrect[Self-Correction]
        Narration[Senior Analyst Narration]
        Orchestrator[Tool Orchestrator]
    end

    subgraph "Protocol:SIFT Skills"
        Plaso[plaso-timeline Skill]
        NTP[ntp-enrichment Skill]
        Attck[attck-correlation Skill]:::highlight
        subgraph Attck
            Enrich[Timeline Enricher]
            Mapper[High-Confidence Mapper]
            Navigator[Navigator Layer Generator]
        end
    end

    subgraph "Data & Knowledge"
        CaseData[Case Evidence<br/>Plaso, Memory, Logs, Disk etc.<br/>Read-Only]:::data
        MCP[MITRE ATT&CK MCP Server<br/>Online]
        STIX[Local STIX Bundles<br/>Offline]:::offline
    end

    subgraph "Outputs"
        Enriched[Enriched Timeline<br/>CSV / JSONL]
        NavigatorLayer[ATT&CK Navigator Layers<br/>JSON + Interactive HTML]
        Reports[Analysis Reports +<br/>Educational Explanations]
        Gaps[Detection Gap Analysis]
    end

    %% Main Flows
    Agent --> Reasoning
    Agent --> SelfCorrect
    Agent --> Narration
    Agent --> Orchestrator

    Orchestrator --> Plaso
    Plaso --> NTP
    NTP --> Attck
    Attck --> Enrich
    Enrich --> Mapper
    Mapper --> Navigator

    %% Data Flow
    CaseData -->|Read-Only| Plaso
    CaseData -->|Read-Only| Attck
    CaseData -.->|Online| MCP
    MCP --> Attck
    STIX --> Attck

    %% Output Flow
    Attck --> Enriched
    Navigator --> NavigatorLayer
    Attck --> Reports
    Attck --> Gaps

    %% Styling
    classDef highlight fill:#98fb98,stroke:#2e8b57,stroke-width:3px
    classDef data fill:#add8e6,stroke:#4682b4
    classDef offline fill:#90ee90,stroke:#228b22

    click Attck href "#" "New dedicated skill"
```
