#!/usr/bin/env python3
"""PostToolUse hook — structured agent execution log (hackathon submission item #8).

Emits one structured JSON line per tool execution (timestamp, tool name, a summary of
the tool input, and token usage when the harness provides it) to
~/.protocol-sift/agent_trace.jsonl, so any finding can be traced back to the tool call
that produced it. On the AWS workstation this file is shipped to CloudWatch
(/ec2/hackasans-prod/sift) by the CloudWatch agent.

Per hackasans-correlator/CLAUDE.md the hook never crashes a session: it catches every
exception, logs best-effort, and always emits ``{"continue": true}``.

Security: append-only local log; no shell, eval, or deserialization beyond json.load of
the harness payload; truncates oversized fields to bound log growth.
"""

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

TRACE_PATH = Path.home() / ".protocol-sift" / "agent_trace.jsonl"
HOOK_LOG = Path.home() / ".protocol-sift" / "hooks.log"
_MAX = 2000  # cap per-field length to bound log size


def _safe_hook_log(message: str) -> None:
    try:
        HOOK_LOG.parent.mkdir(parents=True, exist_ok=True)
        with open(HOOK_LOG, "a") as f:
            f.write(f"{datetime.now(timezone.utc).isoformat()} log_agent_trace {message}\n")
    except Exception:
        pass


def _truncate(value) -> str:
    s = json.dumps(value, default=str)
    return s if len(s) <= _MAX else s[:_MAX] + "...[truncated]"


def main() -> None:
    try:
        payload = json.load(sys.stdin)
        record = {
            "ts": datetime.now(timezone.utc).isoformat(),
            "session_id": payload.get("session_id", ""),
            "tool_name": payload.get("tool_name", ""),
            "tool_input": _truncate(payload.get("tool_input", {})),
            "usage": payload.get("usage") or payload.get("token_usage") or {},
        }
        TRACE_PATH.parent.mkdir(parents=True, exist_ok=True)
        with open(TRACE_PATH, "a") as f:
            f.write(json.dumps(record) + "\n")
    except Exception as exc:
        _safe_hook_log(f"error {exc!r}")
    finally:
        json.dump({"continue": True}, sys.stdout)


if __name__ == "__main__":
    main()
