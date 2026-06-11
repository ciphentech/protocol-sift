#!/usr/bin/env python3
"""Stop hook helper — session transcript capture + token usage report.

Called by the Stop hook in settings.json. Finds the most recently modified
Claude Code session file in ~/.claude/projects/, parses token usage per model,
and writes two files to ./analysis/:

  <session_id>_session.jsonl  — full session transcript (copy)
  token_usage.json            — per-model token counts + USD cost estimate

Token data comes from the session transcript (each assistant turn includes a
usage object with input_tokens, output_tokens, cache_read_input_tokens, and
cache_creation_input_tokens). This is the correct source — the PostToolUse
hook payload does NOT carry token data from the Claude Code harness.

Never crashes the session: all exceptions are caught and printed to stderr.
"""

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

PROJECTS_DIR = Path.home() / ".claude" / "projects"
ANALYSIS_DIR = Path("./analysis")

# USD per 1M tokens — update when Anthropic publishes revised rates
_PRICING: dict[str, dict[str, float]] = {
    "claude-opus-4-8":   {"input": 5.00,  "output": 25.00, "cache_read": 0.50,  "cache_creation": 6.25},
    "claude-opus-4-7":   {"input": 5.00,  "output": 25.00, "cache_read": 0.50,  "cache_creation": 6.25},
    "claude-opus-4-6":   {"input": 5.00,  "output": 25.00, "cache_read": 0.50,  "cache_creation": 6.25},
    "claude-sonnet-4-6": {"input": 3.00,  "output": 15.00, "cache_read": 0.30,  "cache_creation": 3.75},
    "claude-haiku-4-5":  {"input": 1.00,  "output": 5.00,  "cache_read": 0.10,  "cache_creation": 1.25},
}
_DEFAULT_PRICING = {"input": 3.00, "output": 15.00, "cache_read": 0.30, "cache_creation": 3.75}


def _find_latest_session() -> Path | None:
    if not PROJECTS_DIR.is_dir():
        return None
    candidates = [p for p in PROJECTS_DIR.rglob("*.jsonl") if p.is_file()]
    return max(candidates, key=lambda p: p.stat().st_mtime) if candidates else None


def _parse(path: Path) -> tuple[str, list[dict], dict[str, dict[str, int]]]:
    """Return (session_id, events, {model: {token_field: count}})."""
    events: list[dict] = []
    session_id = "unknown"
    totals: dict[str, dict[str, int]] = {}

    with open(path, encoding="utf-8", errors="replace") as fh:
        for raw in fh:
            raw = raw.strip()
            if not raw:
                continue
            try:
                obj = json.loads(raw)
            except json.JSONDecodeError:
                continue
            events.append(obj)

            for key in ("sessionId", "session_id"):
                if sid := obj.get(key):
                    session_id = str(sid)
                    break

            usage = obj.get("usage") or {}
            if not (usage.get("input_tokens") or usage.get("output_tokens")):
                continue
            model = str(obj.get("model", "unknown"))
            if model not in totals:
                totals[model] = {
                    "input_tokens": 0,
                    "output_tokens": 0,
                    "cache_read_input_tokens": 0,
                    "cache_creation_input_tokens": 0,
                }
            totals[model]["input_tokens"]                  += usage.get("input_tokens", 0)
            totals[model]["output_tokens"]                 += usage.get("output_tokens", 0)
            totals[model]["cache_read_input_tokens"]       += usage.get("cache_read_input_tokens", 0)
            totals[model]["cache_creation_input_tokens"]   += usage.get("cache_creation_input_tokens", 0)

    return session_id, events, totals


def _cost(totals: dict[str, dict[str, int]]) -> dict:
    result: dict = {}
    grand = 0.0
    for model, counts in totals.items():
        p = _PRICING.get(model, _DEFAULT_PRICING)
        usd = (
            counts["input_tokens"]                 * p["input"]           / 1_000_000
            + counts["output_tokens"]              * p["output"]          / 1_000_000
            + counts["cache_read_input_tokens"]    * p["cache_read"]      / 1_000_000
            + counts["cache_creation_input_tokens"]* p["cache_creation"]  / 1_000_000
        )
        result[model] = {**counts, "estimated_usd": round(usd, 6)}
        grand += usd
    result["_total_estimated_usd"] = round(grand, 6)
    return result


def main() -> None:
    try:
        session_path = _find_latest_session()
        if session_path is None:
            print("[capture-session] No session files found in ~/.claude/projects/", file=sys.stderr)
            return

        session_id, events, totals = _parse(session_path)
        ANALYSIS_DIR.mkdir(parents=True, exist_ok=True)

        # Session transcript copy
        transcript_out = ANALYSIS_DIR / f"{session_id}_session.jsonl"
        with open(transcript_out, "w", encoding="utf-8") as fh:
            for ev in events:
                fh.write(json.dumps(ev) + "\n")

        # Token usage + cost report
        report = {
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "session_id": session_id,
            "source_file": str(session_path),
            "by_model": _cost(totals),
        }
        usage_out = ANALYSIS_DIR / "token_usage.json"
        with open(usage_out, "w", encoding="utf-8") as fh:
            json.dump(report, fh, indent=2)

        total_usd = report["by_model"].get("_total_estimated_usd", 0.0)
        ts = datetime.now(timezone.utc).isoformat()
        print(f"[capture-session] {ts}  token_usage.json written — estimated cost: ${total_usd:.4f}")

    except Exception as exc:
        print(f"[capture-session] error (non-fatal): {exc!r}", file=sys.stderr)


if __name__ == "__main__":
    main()
