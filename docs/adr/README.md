# Architecture Decision Records

Numbered records of the significant, hard-to-reverse decisions behind Protocol SIFT.
Each captures the context, the decision, its consequences, and the alternatives rejected.
Narrative rationale lives in [ARCHITECTURE.md](../ARCHITECTURE.md); these ADRs own the
decisions it refers to. The individual ADR records are maintained privately and are not
published in this repository.

| ADR | Decision | Status |
|-----|----------|--------|
| 0001 | Bounded self-correction loop, not unbounded retry | Accepted |
| 0002 | The NTP skill is a project skill, not part of the global template | Accepted |
| 0003 | The agent is the system; Python scripts are tools, not the application | Accepted |
| 0004 | Direct Agent Extension: no separate orchestrator, no MCP servers | Accepted |
| 0005 | Two-layer guardrails: architectural enforcement for evidence integrity | Accepted |

## Convention

- One file per decision, named `NNNN-kebab-title.md`, numbered sequentially.
- Header block: **Status**, **Date**, **Scope**, **Related**.
- Sections: **Context**, **Decision**, **Consequences** (positive / negative-accepted),
  **Alternatives considered**.
- Status is one of `Proposed` · `Accepted` · `Superseded by ADR NNNN` · `Deprecated`.
  Don't rewrite history — supersede a decision with a new ADR and update the old one's status.
