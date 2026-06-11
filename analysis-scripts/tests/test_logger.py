"""Unit tests for the forensic execution-log schema (Hackathon #8, SPEC §7 #8).

Drives the real CLI (main()) so SiftSession emits exactly what a case run
emits. Each test chdirs into tmp_path (the audit log goes to ./analysis/
relative to the working directory) and repoints sift_logger.LOGS_DIR
(~/.protocol-sift in production) into tmp_path so runs stay isolated.
"""

import json
from datetime import datetime
from pathlib import Path

import sift_logger
from ntp_enricher import main


def _run(csv_path, tmp_path, monkeypatch, extra_args=()):
    """Run the CLI from tmp_path; return (rc, jsonl events, tmp_path)."""
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(sift_logger, "LOGS_DIR", tmp_path / "logs")
    out = tmp_path / "exports" / "out.csv"
    rc = main(["--input", str(csv_path), "--output", str(out),
               "--skip-nist-check", "--non-interactive", *extra_args])
    logs = sorted((tmp_path / "logs").glob("SIFT-*.jsonl"))
    assert len(logs) == 1, "exactly one session log expected per run"
    events = [json.loads(line) for line in logs[0].read_text().splitlines()]
    return rc, events, logs[0]


def test_jsonl_events_carry_required_schema(mini_csv_path, tmp_path, monkeypatch):
    rc, events, log_path = _run(mini_csv_path, tmp_path, monkeypatch)
    assert rc == 0
    session_id = log_path.stem
    for e in events:
        for field in ("type", "session_id", "timestamp", "os_user"):
            assert field in e, f"{e.get('type', '?')} event missing {field}"
        assert e["session_id"] == session_id
        # UTC ISO timestamp, microsecond precision — must round-trip.
        ts = datetime.fromisoformat(e["timestamp"])
        assert ts.utcoffset() is not None and ts.utcoffset().total_seconds() == 0

    by_type = {e["type"]: e for e in events}
    assert by_type["session_init"]["skill"] == "ntp-enrichment"
    assert by_type["tool_called"]["tool_name"] == "ntp_enricher.py"
    assert "tool_input" in by_type["tool_called"]
    assert by_type["ntp_resolution"]["ntp_source"] == "base-dc.shieldbase.lan"
    assert by_type["session_complete"]["exit_code"] == 0
    assert "duration_s" in by_type["session_complete"]


def test_self_correction_run_logs_iteration_traces(implausible_csv_path, tmp_path,
                                                   monkeypatch):
    rc, events, _ = _run(implausible_csv_path, tmp_path, monkeypatch)
    assert rc == 3  # Phase 3 halt
    traces = [e for e in events if e["type"] == "self_correction_iteration"]
    # Deliverable #8: per-iteration traces, one per failed loop iteration.
    assert len(traces) >= 1
    assert [t["iteration"] for t in traces] == list(range(1, len(traces) + 1))
    for t in traces:
        assert "1000" in t["rejection_basis"]
        assert t["unresolved_count"] >= 1
    halted = [e for e in events if e["type"] == "enrichment_halted"]
    assert len(halted) == 1 and halted[0]["is_error"] is True
    assert halted[0]["iterations"] == len(traces)


def test_forensic_audit_log_written(mini_csv_path, tmp_path, monkeypatch):
    rc, events, log_path = _run(mini_csv_path, tmp_path, monkeypatch)
    assert rc == 0
    session_id = log_path.stem
    audit_path = Path("analysis") / f"{session_id}_forensic_audit.log"
    assert audit_path.exists()
    audit = audit_path.read_text()
    assert "FORENSIC AUDIT LOG" in audit
    assert session_id in audit
    # A finding must be traceable back to the tool execution that produced it.
    assert "tool_called" in audit
    assert str(mini_csv_path) in audit
