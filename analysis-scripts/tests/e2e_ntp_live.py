#!/usr/bin/env python3
"""
e2e_ntp_live.py — Live NTP end-to-end test.

Queries a real NTP server, synthesizes a minimal l2tcsv row from the live
response, runs ntp_enricher.py on it, and verifies the output is enriched.

Usage:
  python3 e2e_ntp_live.py [--ntp-host pool.ntp.org] [--case-dir /tmp/...] [--keep-tmp]

Requires: ntplib (pip install ntplib), network access to --ntp-host.
Security: no case evidence touched; writes only to --case-dir (auto-cleaned).
"""
import argparse
import csv
import os
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

try:
    import ntplib
except ImportError:
    sys.exit("ntplib not installed — run: pip install ntplib")

SCRIPT_DIR = Path(__file__).resolve().parent
ENRICHER = SCRIPT_DIR.parent / "ntp_enricher.py"
ANALYSIS_SCRIPTS = SCRIPT_DIR.parent


def query_ntp(host: str) -> dict:
    last_exc = None
    for attempt in range(1, 4):
        try:
            c = ntplib.NTPClient()
            resp = c.request(host, version=3)
            return {
                "host": host,
                "offset_sec": resp.offset,
                "stratum": resp.stratum,
                "ref_id": ntplib.ref_id_to_text(resp.ref_id, resp.stratum),
            }
        except Exception as exc:
            last_exc = exc
            if attempt < 3:
                delay = 2 ** (attempt - 1)
                print(
                    f"      [warn] NTP attempt {attempt}/3 failed ({exc}); "
                    f"retry in {delay}s",
                    file=sys.stderr,
                )
                time.sleep(delay)
    raise last_exc


def build_synthetic_csv(ntp: dict, path: Path) -> None:
    """One l2tcsv row mimicking a W32tm EventID 35 NTP source-discovery event."""
    offset_100ns = int(ntp["offset_sec"] * 10_000_000)
    row = {
        "date": "05/04/2018",
        "time": "22:14:29",
        "timezone": "UTC",
        "MACB": ".....",
        "source": "EVT",
        "sourcetype": "WinEvtx",
        "type": "Content Modification Time",
        "user": "N/A",
        "host": "rd01",
        "short": (
            f"[35 / 0x0023] NTP offset: {ntp['offset_sec']:.3f}s "
            f"stratum:{ntp['stratum']}"
        ),
        "desc": (
            f"[35 / 0x0023] The time provider NtpClient is currently "
            f"receiving valid time data from {ntp['host']}. "
            f"Strings: ['{ntp['host']}', '{offset_100ns}']"
        ),
        "version": 2,
        "filename": r"C:\Windows\System32\winevt\Logs\System.evtx",
        "inode": "N/A",
        "notes": "",
        "format": "WinEvtx",
        "extra": "",
    }
    with open(path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(row.keys()))
        writer.writeheader()
        writer.writerow(row)


def run_enricher(
    input_csv: Path, output_csv: Path, case_dir: Path
) -> subprocess.CompletedProcess:
    env = os.environ.copy()
    env["PYTHONPATH"] = str(ANALYSIS_SCRIPTS) + os.pathsep + env.get("PYTHONPATH", "")
    return subprocess.run(
        [
            sys.executable,
            str(ENRICHER),
            "--input", str(input_csv),
            "--output", str(output_csv),
            "--case-dir", str(case_dir),
            "--windows-domain-joined",
        ],
        capture_output=True,
        text=True,
        env=env,
    )


def verify_output(input_csv: Path, output_csv: Path) -> list:
    failures = []
    if not output_csv.exists():
        return ["output CSV was not created"]
    with open(input_csv) as f:
        in_cols = len(next(csv.reader(f)))
    with open(output_csv) as f:
        reader = csv.DictReader(f)
        rows = list(reader)
        out_cols = len(reader.fieldnames or [])
    if not rows:
        failures.append("output CSV has no data rows")
    if out_cols <= in_cols:
        failures.append(
            f"no enrichment columns added (in={in_cols} out={out_cols})"
        )
    return failures


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--ntp-host", default="pool.ntp.org",
                    help="NTP server to query (default: pool.ntp.org)")
    ap.add_argument("--case-dir", default=None,
                    help="Case dir passed to ntp_enricher.py (default: temp dir)")
    ap.add_argument("--keep-tmp", action="store_true",
                    help="Do not delete the temp directory on exit")
    args = ap.parse_args()

    tmp = tempfile.mkdtemp(prefix="ntp_e2e_")
    try:
        case_dir = Path(args.case_dir) if args.case_dir else Path(tmp)
        case_dir.mkdir(parents=True, exist_ok=True)
        input_csv = Path(tmp) / "synthetic_ntp.csv"
        output_csv = Path(tmp) / "synthetic_ntp_enriched.csv"

        print(f"[1/3] Querying NTP server: {args.ntp_host}")
        try:
            ntp = query_ntp(args.ntp_host)
        except Exception as exc:
            sys.exit(f"FAIL: NTP query failed: {exc}")
        print(
            f"      offset={ntp['offset_sec']:.6f}s  "
            f"stratum={ntp['stratum']}  ref={ntp['ref_id']}"
        )

        print("[2/3] Synthesizing CSV row and running ntp_enricher.py")
        build_synthetic_csv(ntp, input_csv)
        result = run_enricher(input_csv, output_csv, case_dir)
        if result.returncode != 0:
            print(result.stderr, file=sys.stderr)
            sys.exit(f"FAIL: ntp_enricher.py exited {result.returncode}")

        print("[3/3] Verifying enriched output")
        failures = verify_output(input_csv, output_csv)
        if failures:
            for msg in failures:
                print(f"  FAIL: {msg}", file=sys.stderr)
            sys.exit(1)

        print("PASS: live NTP e2e OK")
    finally:
        if not args.keep_tmp:
            shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    main()
