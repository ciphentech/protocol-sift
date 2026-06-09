"""Structured forensic audit logging for Protocol SIFT agent sessions.

Writes JSONL events (one object per line) to ./logs/<session_id>.jsonl and,
if SIFT_S3_BUCKET is set, streams the accumulated log to S3 on each event.
At session end, writes a human-readable audit summary to
./analysis/<session_id>_forensic_audit.log.

Timestamps use datetime.now(timezone.utc).isoformat() — the same format as
the log_agent_trace.py hook — providing microsecond precision:
  2026-06-09T14:16:07.043821+00:00

Every log entry includes os_user (from getpass.getuser()) for chain-of-custody.

Environment variables:
  SIFT_S3_BUCKET   — S3 bucket name (if unset, logs are written locally only)
  SIFT_S3_REGION   — AWS region     (default: us-west-2)
  SIFT_S3_PREFIX   — S3 key prefix  (default: sift-logs)
  SIFT_AGENT_MODEL — model name recorded in session_init (default: claude-sonnet-4-6)

S3 key structure (when SIFT_S3_BUCKET is set):
  <SIFT_S3_PREFIX>/<YYYY-MM-DD>/<session_id>/events.jsonl
"""

from __future__ import annotations

import getpass
import json
import os
import sys
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path

SIFT_S3_BUCKET = os.environ.get("SIFT_S3_BUCKET", "")
SIFT_S3_REGION = os.environ.get("SIFT_S3_REGION", "us-west-2")
SIFT_S3_PREFIX = os.environ.get("SIFT_S3_PREFIX", "sift-logs")
SIFT_AGENT_MODEL = os.environ.get("SIFT_AGENT_MODEL", "claude-sonnet-4-6")

LOGS_DIR = Path("./logs")

try:
    _OS_USER = getpass.getuser()
except Exception:
    _OS_USER = os.environ.get("USER", "unknown")


def _make_session_id() -> str:
    date_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    return f"SIFT-{date_str}-{uuid.uuid4().hex[:8]}"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def log_event(session_id: str, event_type: str, **fields) -> dict:
    """Append one JSONL entry to the local session log and optionally ship to S3."""
    entry = {
        "type": event_type,
        "session_id": session_id,
        "timestamp": _now(),
        "os_user": _OS_USER,
        **fields,
    }
    log_path = LOGS_DIR / f"{session_id}.jsonl"
    LOGS_DIR.mkdir(parents=True, exist_ok=True)
    with open(log_path, "a", encoding="utf-8") as f:
        f.write(json.dumps(entry) + "\n")
    if SIFT_S3_BUCKET:
        _ship_to_s3(session_id, log_path)
    return entry


def _ship_to_s3(session_id: str, log_path: Path) -> None:
    """Upload the current JSONL to S3. Fails silently — never blocks forensic workflows."""
    try:
        import boto3
        s3 = boto3.client("s3", region_name=SIFT_S3_REGION)
        date_str = session_id[5:15]  # SIFT-YYYY-MM-DD-xxxxxxxx → YYYY-MM-DD
        key = f"{SIFT_S3_PREFIX}/{date_str}/{session_id}/events.jsonl"
        s3.put_object(
            Bucket=SIFT_S3_BUCKET,
            Key=key,
            Body=log_path.read_bytes(),
            ContentType="application/x-ndjson",
        )
    except Exception as exc:
        print(f"[sift-logger] S3 upload failed (non-fatal): {exc}", file=sys.stderr)


def _emit_forensic_audit(
    session_id: str, events: list[dict], duration_s: float, exit_code: int
) -> None:
    """Write a per-session human-readable audit summary to ./analysis/<session_id>_forensic_audit.log."""
    try:
        audit_path = Path("./analysis") / f"{session_id}_forensic_audit.log"
        audit_path.parent.mkdir(parents=True, exist_ok=True)

        init_event = next((e for e in events if e["type"] == "session_init"), {})

        local_log = str(LOGS_DIR / f"{session_id}.jsonl")
        s3_path = ""
        if SIFT_S3_BUCKET:
            date_str = session_id[5:15]
            s3_path = (
                f"s3://{SIFT_S3_BUCKET}/{SIFT_S3_PREFIX}"
                f"/{date_str}/{session_id}/events.jsonl"
            )

        files_read: list[str] = []
        output_paths: list[str] = []
        for e in events:
            for f in e.get("files_accessed") or []:
                if f and f not in files_read:
                    files_read.append(f)
            if e.get("output_path"):
                p = e["output_path"]
                if p and p not in output_paths:
                    output_paths.append(p)

        sep = "=" * 80
        lines = [
            sep,
            "PROTOCOL SIFT — FORENSIC AUDIT LOG",
            f"Session:   {session_id}",
            f"OS User:   {_OS_USER}",
            f"Skill:     {init_event.get('skill', 'unknown')}",
            f"Model:     {init_event.get('model', SIFT_AGENT_MODEL)}",
            f"Harness:   protocol-sift",
            f"Platform:  {init_event.get('platform', sys.platform)}",
            f"WorkDir:   {init_event.get('project_directory', os.getcwd())}",
            f"Start:     {events[0]['timestamp'] if events else 'unknown'}",
            f"End:       {events[-1]['timestamp'] if events else 'unknown'}",
            f"Duration:  {duration_s:.2f}s",
            f"Outcome:   {'session_complete' if exit_code == 0 else 'session_error/halt'} "
            f"(exit_code={exit_code})",
            sep,
            "",
            "ACTIONS TAKEN:",
        ]

        for e in events:
            ts = e.get("timestamp", "")
            etype = e["type"]
            parts = []
            if e.get("tool_name"):
                parts.append(f"tool={e['tool_name']}")
            if e.get("ntp_source"):
                parts.append(f"source={e['ntp_source']}")
            if e.get("server"):
                parts.append(f"server={e['server']}")
                if e.get("offset_s") is not None:
                    parts.append(f"offset={e['offset_s']:+.4f}s")
            if e.get("rows_processed"):
                parts.append(f"rows={e['rows_processed']}")
            if e.get("ok") is not None:
                parts.append(f"integrity_ok={e['ok']}")
            if e.get("duration_s") is not None and etype in ("session_complete", "session_error"):
                parts.append(f"duration={e['duration_s']}s")
            if e.get("exit_code") is not None:
                parts.append(f"exit_code={e['exit_code']}")
            if e.get("is_error"):
                parts.append("IS_ERROR")
            summary = " | ".join(parts)
            lines.append(f"  [{ts}] {etype:<26} {summary}")
            if e.get("reasoning"):
                lines.append(f"    reasoning: {e['reasoning']}")

        lines += ["", "EVIDENCE:"]
        if files_read:
            lines.append("  Files accessed (read-only):")
            for f in files_read:
                lines.append(f"    - {f}")
        else:
            lines.append("  (none recorded)")
        if output_paths:
            lines += ["  Files written:"]
            for p in output_paths:
                lines.append(f"    - {p}")

        lines += ["", "SOURCE CITATIONS:"]
        lines.append(f"  JSONL log (local): {local_log}")
        if s3_path:
            lines.append(f"  JSONL log (S3):    {s3_path}")
        lines += ["", ""]

        with open(audit_path, "w", encoding="utf-8") as f:
            f.write("\n".join(lines))
    except Exception as exc:
        print(
            f"[sift-logger] forensic_audit write failed (non-fatal): {exc}",
            file=sys.stderr,
        )


class SiftSession:
    """Context manager wrapping a DFIR skill run with structured forensic audit logging.

    Usage (any skill's Python script):

        from sift_logger import SiftSession

        with SiftSession("ntp-enrichment", case_dir=args.case_dir) as sess:
            sess.log("tool_called", tool_name="ntp_enricher.py",
                     tool_input=vars(args),
                     reasoning="Parsing CLI arguments.")
            ...
            sess.set_exit_code(0)

    Emits session_init on enter and session_complete / session_error on exit.
    All events are written to ./logs/<session_id>.jsonl and, if SIFT_S3_BUCKET
    is set, streamed to S3 on every write.
    """

    def __init__(self, skill: str, **extra):
        self.session_id = _make_session_id()
        self.skill = skill
        self.extra = extra
        self._start_time: float | None = None
        self._exit_code: int = 0
        self._events: list[dict] = []

    def __enter__(self) -> "SiftSession":
        self._start_time = time.monotonic()
        event = log_event(
            self.session_id,
            "session_init",
            skill=self.skill,
            model=SIFT_AGENT_MODEL,
            platform=sys.platform,
            project_directory=os.getcwd(),
            **self.extra,
        )
        self._events.append(event)
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> bool:
        duration_s = round(time.monotonic() - (self._start_time or 0), 2)
        if exc_type is not None:
            event = log_event(
                self.session_id,
                "session_error",
                error=exc_type.__name__,
                message=str(exc_val),
                duration_s=duration_s,
                is_error=True,
            )
            self._events.append(event)
            _emit_forensic_audit(self.session_id, self._events, duration_s, exit_code=1)
        else:
            event = log_event(
                self.session_id,
                "session_complete",
                exit_code=self._exit_code,
                duration_s=duration_s,
                s3_path=(
                    f"s3://{SIFT_S3_BUCKET}/{SIFT_S3_PREFIX}"
                    f"/{self.session_id[5:15]}/{self.session_id}/events.jsonl"
                ) if SIFT_S3_BUCKET else "",
            )
            self._events.append(event)
            _emit_forensic_audit(self.session_id, self._events, duration_s, self._exit_code)
        return False  # do not suppress exceptions

    def log(self, event_type: str, **fields) -> dict:
        """Emit a skill-level event.

        Common fields:
          reasoning (str)        — why this action was taken
          files_accessed (list)  — evidence paths read during this phase
          is_error (bool)        — True for failure/halt events
          tool_name (str)        — CLI tool invoked
          tool_input (dict)      — exact args passed to the tool
          output_path (str)      — path of any file written
        """
        event = log_event(self.session_id, event_type, **fields)
        self._events.append(event)
        return event

    def set_exit_code(self, code: int) -> None:
        self._exit_code = code
