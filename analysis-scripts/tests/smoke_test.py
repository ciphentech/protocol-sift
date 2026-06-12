#!/usr/bin/env python3
"""Smoke test runner for tlcorr_pipeline.sh — T-01 through T-08.

Usage: python3 analysis-scripts/tests/smoke_test.py
       python3 analysis-scripts/tests/smoke_test.py --offline   # skip NTP-live tests
"""

import csv
import hashlib
import json
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

# --- Paths ------------------------------------------------------------------
HERE = Path(__file__).resolve().parent
PIPELINE = HERE.parent / "tlcorr_pipeline.sh"
FIXTURES = HERE / "fixtures"
FIXTURE_NORMAL = FIXTURES / "test_timeline.csv"
FIXTURE_IMPLAUSIBLE = FIXTURES / "test_timeline_implausible.csv"
OFFLINE = "--offline" in sys.argv

# --- Harness ----------------------------------------------------------------
RESULTS: list[tuple[str, str, str]] = []


def run(label: str, fn, skip_if_offline: bool = False) -> None:
    if skip_if_offline and OFFLINE:
        RESULTS.append(("SKIP", label, "--offline"))
        print(f"  SKIP  {label} (--offline)")
        return
    try:
        fn()
        RESULTS.append(("PASS", label, ""))
        print(f"  PASS  {label}")
    except AssertionError as exc:
        RESULTS.append(("FAIL", label, str(exc)))
        print(f"  FAIL  {label}: {exc}")
    except Exception as exc:
        RESULTS.append(("ERROR", label, str(exc)))
        print(f"  ERROR {label}: {exc}")


def pipeline(*args, outdir: Path) -> subprocess.CompletedProcess:
    cmd = ["bash", str(PIPELINE)] + list(args) + ["--outdir", str(outdir)]
    return subprocess.run(cmd, capture_output=True, text=True, timeout=120)


def csv_row_count(path: Path) -> int:
    with open(path, newline="") as f:
        return sum(1 for _ in csv.DictReader(f))


# --- Test cases -------------------------------------------------------------

def t01_happy_path_skip_ntp(tmp: Path) -> None:
    """Pipeline plumbing works end-to-end without network dependency."""
    outdir = tmp / "t01"
    r = pipeline("--input", str(FIXTURE_NORMAL), "--case", "SMOKE01", "--skip-ntp", outdir=outdir)
    assert r.returncode == 0, f"exit {r.returncode}:\n{r.stderr[:400]}"

    corr = outdir / "exports" / "SMOKE01_correlated.csv"
    assert corr.exists(), "correlated CSV not written"
    assert csv_row_count(corr) == csv_row_count(FIXTURE_NORMAL), "row count changed"

    audit = outdir / "analysis" / "forensic_audit.log"
    assert audit.exists(), "audit log not written"
    assert "RUN END" in audit.read_text(), "audit log missing RUN END"

    combined = r.stdout + r.stderr
    assert any(kw in combined.lower() for kw in ("skip-ntp", "not nist-anchored")), \
        "--skip-ntp warning not emitted"


def t02_ntp_source_override(tmp: Path) -> None:
    """--ntp-source flag enriches all rows; five new columns written; accuracy report valid."""
    outdir = tmp / "t02"
    r = pipeline("--input", str(FIXTURE_NORMAL), "--case", "SMOKE02",
                 "--ntp-source", "time.windows.com", outdir=outdir)
    assert r.returncode == 0, f"exit {r.returncode}:\n{r.stderr[:400]}"

    corr = outdir / "exports" / "SMOKE02_correlated.csv"
    assert corr.exists(), "correlated CSV not written"

    with open(corr, newline="") as f:
        rows = list(csv.DictReader(f))
    assert rows, "correlated CSV is empty"

    required_cols = {"ntp_source", "nist_time", "ntp_offset_s", "ntp_assumption", "nist_delta_s"}
    missing_cols = required_cols - set(rows[0].keys())
    assert not missing_cols, f"output CSV missing columns: {missing_cols}"

    wrong_source = [row for row in rows if row["ntp_source"] != "time.windows.com"]
    assert not wrong_source, f"{len(wrong_source)} rows have wrong ntp_source"

    wrong_assumption = [row for row in rows if row["ntp_assumption"].strip().lower() != "false"]
    assert not wrong_assumption, \
        f"{len(wrong_assumption)} rows have ntp_assumption=true (should be false for analyst-provided)"

    acc = outdir / "analysis" / "SMOKE02_accuracy.json"
    assert acc.exists(), "accuracy report not written"
    d = json.loads(acc.read_text())
    src = d.get("ntp_context", {}).get("ntp_source", "")
    assert src == "time.windows.com", f"accuracy report ntp_context.ntp_source={src!r}"


def t03a_evidence_integrity_outdir_overlaps_input(tmp: Path) -> None:
    """Pipeline refuses outdir that is inside the input file's directory."""
    pre_existing = set(FIXTURES.iterdir())
    r = subprocess.run(
        ["bash", str(PIPELINE),
         "--input", str(FIXTURE_NORMAL),
         "--case", "SMOKE03A",
         "--outdir", str(FIXTURES),
         "--skip-ntp"],
        capture_output=True, text=True, timeout=30,
    )
    assert r.returncode == 1, f"expected exit 1, got {r.returncode}"
    assert any(kw in r.stderr.lower() for kw in ("evidence integrity", "overlap", "must not")), \
        f"no integrity error in stderr:\n{r.stderr[:300]}"

    unexpected = [p for p in FIXTURES.iterdir() if p not in pre_existing]
    assert not unexpected, f"files written into fixture dir: {unexpected}"


def t03b_evidence_integrity_guarded_paths(tmp: Path) -> None:
    """Pipeline refuses outdir under /cases, /mnt, /media."""
    for guarded in ("/cases/out", "/mnt/out", "/media/out"):
        r = subprocess.run(
            ["bash", str(PIPELINE),
             "--input", str(FIXTURE_NORMAL),
             "--case", "SMOKE03B",
             "--outdir", guarded,
             "--skip-ntp"],
            capture_output=True, text=True, timeout=30,
        )
        assert r.returncode == 1, \
            f"guarded path {guarded!r} was not rejected (exit {r.returncode})"


def t04_nist_unreachable(tmp: Path) -> None:
    """Pipeline halts with exit 2 when every NIST server is unreachable."""
    outdir = tmp / "t04"
    # --nist-server replaces the whole NIST fallback chain. The host matches
    # the client's .nist.gov allowlist but does not exist, so the query
    # deterministically fails (NXDOMAIN) regardless of network connectivity.
    r = pipeline("--input", str(FIXTURE_NORMAL), "--case", "SMOKE04",
                 "--ntp-source", "time.windows.com",
                 "--nist-server", "unreachable-smoke-test.nist.gov", outdir=outdir)
    assert r.returncode == 2, f"expected exit 2, got {r.returncode}:\n{r.stderr[:400]}"

    corr = outdir / "exports" / "SMOKE04_correlated.csv"
    assert not corr.exists(), "partial CSV written despite exit 2 (halt-before-compute violated)"

    audit = outdir / "analysis" / "forensic_audit.log"
    if audit.exists():
        assert "ENRICHER_FAIL" in audit.read_text(), "audit log missing ENRICHER_FAIL"


def t05_self_correction_exhausted(tmp: Path) -> None:
    """Pipeline exits 3 when implausible offsets remain after max iterations."""
    outdir = tmp / "t05"
    # The implausible fixture has an EID 35 offset of 15000000000 raw
    # → 15000000000 ÷ 10,000,000 = 1500 s — exceeds the ±1000 s plausibility bound
    r = pipeline("--input", str(FIXTURE_IMPLAUSIBLE), "--case", "SMOKE05",
                 "--ntp-source", "pool.ntp.org", outdir=outdir)
    assert r.returncode == 3, f"expected exit 3, got {r.returncode}:\n{r.stderr[:400]}"
    combined = r.stdout + r.stderr
    assert any(kw in combined.lower() for kw in ("self-correction", "implausible", "exhausted")), \
        f"no self-correction message:\n{combined[:400]}"


def t06_required_arg_validation(tmp: Path) -> None:
    """Missing or invalid flags exit 1 with a clear error message."""
    cases = [
        (["--case", "X", "--outdir", str(tmp / "t06a")], "missing --input"),
        (["--input", "/nonexistent_file.csv", "--case", "X", "--outdir", str(tmp / "t06b")],
         "nonexistent --input"),
        (["--input", str(FIXTURE_NORMAL), "--case", "X", "--outdir", str(tmp / "t06c"),
          "--unknown-flag"], "unknown flag"),
        (["--input", str(FIXTURE_NORMAL), "--outdir", str(tmp / "t06d")], "missing --case"),
        (["--input", str(FIXTURE_NORMAL), "--case", "X"], "missing --outdir"),
    ]
    for extra_args, description in cases:
        r = subprocess.run(
            ["bash", str(PIPELINE)] + extra_args,
            capture_output=True, text=True, timeout=30,
        )
        assert r.returncode == 1, \
            f"{description}: expected exit 1, got {r.returncode}. stderr: {r.stderr[:200]}"


def t07_accuracy_report_schema(tmp: Path) -> None:
    """Accuracy report contains required SPEC §2.3 keys."""
    outdir = tmp / "t07"
    r = pipeline("--input", str(FIXTURE_NORMAL), "--case", "SMOKE07",
                 "--ntp-source", "time.windows.com", outdir=outdir)
    assert r.returncode == 0, f"exit {r.returncode}:\n{r.stderr[:400]}"

    acc = outdir / "analysis" / "SMOKE07_accuracy.json"
    assert acc.exists(), "accuracy report not written"
    d = json.loads(acc.read_text())

    # Accept either name variant for total event count
    has_total = "rows_total" in d or "event_count" in d or "total_events" in d
    assert has_total, f"accuracy report missing total event count. Keys present: {list(d.keys())}"
    assert "rows_assumption_true" in d, \
        f"missing rows_assumption_true. Keys: {list(d.keys())}"
    assert "ntp_context" in d, \
        f"missing ntp_context. Keys: {list(d.keys())}"


def t08_audit_log_append_only_and_utc(tmp: Path) -> None:
    """Audit log appends across runs and uses ISO-8601 UTC timestamps."""
    outdir = tmp / "t08"
    for _ in range(2):
        r = pipeline("--input", str(FIXTURE_NORMAL), "--case", "SMOKE08",
                     "--skip-ntp", outdir=outdir)
        assert r.returncode == 0, f"run failed: {r.stderr[:200]}"

    audit = outdir / "analysis" / "forensic_audit.log"
    assert audit.exists(), "audit log not written"
    text = audit.read_text()

    starts = text.count("RUN START")
    assert starts == 2, \
        f"expected 2 RUN START entries (append-only), found {starts} (log may be overwriting)"

    utc_re = re.compile(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z")
    assert utc_re.search(text), "no UTC timestamps (YYYY-MM-DDTHH:MM:SSZ) in audit log"


# --- Main -------------------------------------------------------------------

def main() -> None:
    print(f"\n{'=' * 62}")
    print("  tlcorr_pipeline.sh — smoke test suite")
    if OFFLINE:
        print("  mode: --offline (T-02, T-07 skipped)")
    print(f"{'=' * 62}\n")

    errors = []
    if not PIPELINE.exists():
        errors.append(f"tlcorr_pipeline.sh not found: {PIPELINE}")
    if not FIXTURE_NORMAL.exists():
        errors.append(f"fixture not found: {FIXTURE_NORMAL}")
    if not FIXTURE_IMPLAUSIBLE.exists():
        errors.append(f"fixture not found: {FIXTURE_IMPLAUSIBLE}")
    if errors:
        for e in errors:
            print(f"  PREREQ ERROR: {e}")
        sys.exit(1)

    tmp = Path(tempfile.mkdtemp(prefix="tlcorr_smoke_"))
    print(f"  Temp dir: {tmp}\n")

    try:
        run("T-01  happy path (--skip-ntp, offline-safe)",        lambda: t01_happy_path_skip_ntp(tmp))
        run("T-02  ntp-source override + five enriched columns",  lambda: t02_ntp_source_override(tmp),      skip_if_offline=True)
        run("T-03a evidence integrity: outdir overlaps input",    lambda: t03a_evidence_integrity_outdir_overlaps_input(tmp))
        run("T-03b evidence integrity: guarded paths",            lambda: t03b_evidence_integrity_guarded_paths(tmp))
        run("T-04  NIST unreachable → exit 2",                    lambda: t04_nist_unreachable(tmp))
        run("T-05  self-correction exhausted → exit 3",           lambda: t05_self_correction_exhausted(tmp))
        run("T-06  required arg / invalid flag validation",       lambda: t06_required_arg_validation(tmp))
        run("T-07  accuracy report schema (SPEC §2.3)",           lambda: t07_accuracy_report_schema(tmp),   skip_if_offline=True)
        run("T-08  audit log: append-only + UTC timestamps",      lambda: t08_audit_log_append_only_and_utc(tmp))

        print(f"\n{'=' * 62}")
        passed = sum(1 for s, _, _ in RESULTS if s == "PASS")
        skipped = sum(1 for s, _, _ in RESULTS if s == "SKIP")
        failed = sum(1 for s, _, _ in RESULTS if s in ("FAIL", "ERROR"))
        print(f"  {passed} passed  {failed} failed  {skipped} skipped  /  {len(RESULTS)} total")
        print(f"{'=' * 62}\n")

        if failed:
            print("Failed tests:")
            for status, label, reason in RESULTS:
                if status in ("FAIL", "ERROR"):
                    print(f"  [{status}] {label}")
                    if reason:
                        print(f"           {reason}")
            keep = Path("/tmp/tlcorr_smoke_FAILED")
            if keep.exists():
                shutil.rmtree(keep)
            shutil.copytree(tmp, keep)
            print(f"\n  Outputs preserved at: {keep}")
            sys.exit(1)
        else:
            shutil.rmtree(tmp)

    except KeyboardInterrupt:
        print(f"\nInterrupted. Outputs preserved at: {tmp}")
        sys.exit(130)


if __name__ == "__main__":
    main()
