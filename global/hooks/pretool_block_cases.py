#!/usr/bin/env python3
"""PreToolUse hook — evidence integrity runtime arm (FEATURE 1, SPEC §8).

Blocks Write/Edit tool calls that target a read-only evidence root (``/cases/``,
``/mnt/``, ``/media/``). This is a *secondary* control; the primary control is the
read-only EBS mount. Per hackasans-correlator/CLAUDE.md a hook must never crash a
session: it catches every exception, logs best-effort to ~/.protocol-sift/hooks.log,
and always emits a JSON decision (defaulting to ``{"continue": true}``) so a bug here
can never wedge Claude Code.

Security: read-only on stdin; no shell, eval, or deserialization beyond json.load of the
harness-provided payload; fails *open for the session* (never crashes) but *closed for
the write* (blocks the forbidden path).
"""

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

FORBIDDEN_PREFIXES = ("/cases/", "/mnt/", "/media/")
LOG_PATH = Path.home() / ".protocol-sift" / "hooks.log"


def _safe_log(message: str) -> None:
    try:
        LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
        with open(LOG_PATH, "a") as f:
            f.write(f"{datetime.now(timezone.utc).isoformat()} pretool_block_cases {message}\n")
    except Exception:
        pass  # logging is best-effort; never raise from a hook


def _target_path(payload: dict) -> str:
    tool_input = payload.get("tool_input") or {}
    return str(tool_input.get("file_path") or tool_input.get("path") or "")


def main() -> None:
    decision = {"continue": True}
    try:
        payload = json.load(sys.stdin)
        tool = str(payload.get("tool_name", ""))
        path = _target_path(payload)
        if tool in ("Write", "Edit", "MultiEdit") and path:
            if any(path.startswith(p) for p in FORBIDDEN_PREFIXES):
                reason = f"Write to read-only evidence path blocked: {path} (SPEC §8)"
                _safe_log(f"BLOCK {reason}")
                decision = {"continue": False, "stopReason": reason}
    except Exception as exc:
        _safe_log(f"error {exc!r}")
    finally:
        json.dump(decision, sys.stdout)


if __name__ == "__main__":
    main()
