# Protocol SIFT — NTP Enrichment Prompts

This file is a derived view of [`IMPLEMENTATION.md`](IMPLEMENTATION.md). Each entry has the
prompt body in a fenced block (paste into Claude Code) followed by the
acceptance check (run yourself after Claude Code completes the step).

- **P-00 through P-05** build the testable Python tool layer (foundation).
- **P-06 through P-10** build the agent layer — `SKILL.md` reasoning instructions, manifest interface, settings wiring, smoke tests, and install verification.

`IMPLEMENTATION.md` is the source of truth for architecture context, the full agent trace walkthrough, the file map, and test-coverage tables. None of that is copied here — only the prompts and their acceptance checks.

| Step | What gets built |
|------|----------------|
| P-00 | Python environment + pinned dependencies |
| P-01 | Test fixtures + pytest scaffold |
| P-02 | `NTPContext` dataclass + EID extraction |
| P-03 | Full NTP resolution decision tree |
| P-04 | `ntp_enricher.py` — field computation + safe writer |
| P-05 | Self-correction loop (`validate_and_correct`) |
| P-06 | `SKILL.md` as agent reasoning instructions |
| P-07 | Manifest JSON + rubric evaluator |
| P-08 | `SKILL.md` self-correction + `global/CLAUDE.md` routing + `settings.json` |
| P-09 | Agent trace test (full reasoning loop) |
| P-10 | `install.sh` patch + final verification |

For ease of execution and testing, these have been split into separate files. 






