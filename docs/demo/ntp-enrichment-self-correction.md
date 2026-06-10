# Demo Video — `ntp-enrichment` Self-Correction (2–4 min)

A shot-by-shot storyboard and narration script for a live Claude Code recording that
proves the `ntp-enrichment` skill **catches its own implausible output and halts
fail-closed** rather than shipping a corrupted forensic timeline.

- **Story:** detect → retry → **halt fail-closed** (the behavior the code exhibits today).
- **Format:** live Claude Code session screen capture.
- **Runtime target:** ~3:50, comfortably inside the 2–4 min window.

---

## Before you hit record

Stage the scene with the one-command runner (deterministic, offline, reuses the
existing implausible fixture):

```bash
cd analysis-scripts
bash demo/stage_self_correct_case.sh          # or: PAUSE=1 bash demo/stage_self_correct_case.sh
```

This builds a throwaway case at `/tmp/ntp_demo/DEMO-NTP-2026-001/` with a psort
export already in `exports/`. For the **live take**, open Claude Code in that case
directory and use the scripted prompt in Shot 3.

Rehearsal checklist (run once, off-camera):
1. `bash analysis-scripts/demo/stage_self_correct_case.sh` → prints a HALT, exit code 3,
   and an `unresolved_rows` entry whose basis cites the ±1000 s bound.
2. `bash analysis-scripts/tests/smoke_ntp_agent.sh` → `OK: 3/3 scenes passed`
   (we changed no enrichment logic — this is the correctness baseline).
3. Open Claude Code in the staged case, paste the Shot 3 prompt, confirm Claude reaches
   the same halt + report. Then record.

---

## Storyboard

| # | Time | Shot | On-screen | Narration (voiceover) |
|---|------|------|-----------|------------------------|
| 1 | 0:00–0:25 | **Title + problem** | Title card: "When clocks drift, timelines lie." Quick cut to two log sources with mismatched timestamps. | "In an incident, you correlate events across many log sources. But each host's clock can be wrong. If a skewed clock slips through, your timeline — the thing you take to court — is silently corrupted." |
| 2 | 0:25–0:55 | **The skill** | Terminal in the staged case. `cat ~/.claude/skills/ntp-enrichment/SKILL.md` scrolled to the Phase 3 section. | "Protocol SIFT gives Claude a DFIR skill that anchors every timestamp to NIST UTC. Claude reads the skill — it doesn't hard-code the steps — and runs the flat Python tools. Watch what happens when the evidence itself is implausible." |
| 3 | 0:55–1:50 | **Live agent run** | Claude Code session. Paste the prompt (below). Claude reads `SKILL.md`, resolves the NTP source from the Windows event log, and invokes `ntp_enricher.py`. | "I ask Claude to enrich this timeline. It recovers the NTP sync source from a Windows Time-Service event, then computes the clock offset — and starts validating it against the ±1000-second plausibility bound." |
| 4 | 1:50–2:50 | **The self-correction beat** ⭐ | Highlight the halt: `HALT after 3 iteration(s): N unresolved row(s)`, exit code `3`, and the `unresolved_rows[].rejection_basis` JSON. | "Here it is. The offset is about 2000 seconds — over the bound. Instead of writing it out, the loop **re-resolves the source and retries, three times**. Same evidence, same implausible answer — so it **halts**. It caught its *own* bad output and refused to ship it, naming the exact row and the reason." |
| 5 | 2:50–3:20 | **Integrity proof** | Show `sha256` of the source CSV before == after; show that no NIST-anchored bad timeline was emitted. | "Two guarantees hold throughout: the original evidence CSV is byte-for-byte unchanged — chain of custody intact — and no corrupted enriched timeline ever lands on disk." |
| 6 | 3:20–3:50 | **Wrap** | Accuracy report `spec_caveats_applicable` + the rejection basis on screen. | "Bounded. Auditable. Honest. A naïve retry-until-it-passes loop would have *hidden* this error. This one surfaces it, documents it, and hands it back to the analyst. That's self-correction you can put in a forensic report." |

⭐ Shot 4 is the centerpiece — let it breathe; hold on the halt message and the JSON.

---

## The exact prompt to paste into Claude (Shot 3)

```
Using the ntp-enrichment skill, enrich exports/DEMO-NTP-2026-001_timeline.csv
to NIST UTC. Work offline (skip the live NIST query) and run non-interactively.
Tell me the result and, if anything can't be resolved, exactly why.
```

If you prefer to show the tool directly instead of via the agent, the equivalent
command (what Claude ends up running) is:

```bash
python3 ntp_enricher.py \
  --input  exports/DEMO-NTP-2026-001_timeline.csv \
  --output exports/DEMO-NTP-2026-001_timeline_enriched.csv \
  --case-dir /tmp/ntp_demo/DEMO-NTP-2026-001 \
  --skip-nist-check --non-interactive
# exit code 3 = Phase 3 self-correction halt, by design
```

---

## Why no "Ralph Wiggum" loop

A naïve unbounded `while true: re-run until it passes` loop is the wrong pattern here:

1. **The skill already self-corrects** — `validate_and_correct()` is a *bounded* loop
   (`MAX_ITERATIONS = 3`) that re-resolves and, on exhaustion, lists unresolved rows.
   It never silently zeroes the offset.
2. **Unbounded retry violates fail-closed forensics.** The resolver is deterministic on
   the same input; "retry until something passes" is exactly the chain-of-custody
   anti-pattern this code refuses — it halts with exit code 3 instead.
3. **The recording needs no loop** — one skill invocation runs the whole
   resolve → NIST → enrich → self-correct → report pipeline.

A *bounded, reasoned* agent-in-the-loop **recovery** (Claude observes the halt, supplies
new evidence such as `--ntp-source`, and re-runs) is a legitimate follow-up — but that's
deliberate analyst correction, a separate "recover" video, not a Ralph loop.

---

## Source references
- Self-correction loop: `analysis-scripts/ntp_enricher.py` — `validate_and_correct()` (≈ lines 271–300), halt path (≈ lines 411–466).
- Proven baseline: `analysis-scripts/tests/smoke_ntp_agent.sh` Scene 2.
- Fixture (reused, unmodified): `analysis-scripts/tests/fixtures/ntp_mini_implausible.csv`.
