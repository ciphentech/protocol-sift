"""NIST-anchored timeline enrichment + self-correction + CLI for Protocol SIFT.

FEATURE 5 — NIST-Anchored Timeline Enrichment (SPEC §2.2, §4 Phase 1)
FEATURE 1 — Evidence Integrity Guarantee  (SPEC §8)
FEATURE 7 — Self-Correction Loop          (SPEC §4 Phase 3)
FEATURE 6 — Bypass and Override Controls  (SPEC §4 CLI Flags)

Flat analysis-script. Reads a Plaso l2tcsv export (read-only), appends exactly the five
SPEC §2.2 columns in spec order, sorts on ``nist_time``, and writes a new CSV to the
writable output area (``./exports/``). The original file is never modified — verified by
a sha256 hash check. The self-correction loop re-resolves the NTP source (it does not
blindly zero the offset) and is bounded; on exhaustion it surfaces the unresolved rows.

Security: output paths are checked against a forbidden-prefix *allowlist boundary*
(``/cases/``, ``/mnt/``, ``/media/``) and rejected if they target source/evidence mounts
(SPEC §8); the source hash is re-verified after the run and a mismatch fails closed with
a RuntimeError; NIST unreachability halts the run (fail closed) with a chain-of-custody
warning; no shell, eval, or deserialization of untrusted data; CSV is parsed with
``keep_default_na=False`` so values are never silently coerced.
"""

from __future__ import annotations

import argparse
import hashlib
import shutil
import sys
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Callable, Optional

import pandas as pd

from ntp_resolver import (
    NTPContext,
    extract_eid_number,
    extract_phase_offset_s,
    resolve_ntp_source,
)

# Paths that must never be written to (evidence integrity — SPEC §8 + the
# plaso-timeline skill's existing /mnt//media guards).
_FORBIDDEN_OUTPUT_PREFIXES = ("/cases/", "/mnt/", "/media/")

# Exactly the five new columns, in SPEC §2.2 order.
NEW_COLUMNS = ["ntp_source", "nist_time", "ntp_offset_s", "ntp_assumption", "nist_delta_s"]

PLASO_DATE_FMT = "%m/%d/%Y"
PLASO_TIME_FMT = "%H:%M:%S"
NIST_TIME_FMT = "%Y-%m-%d %H:%M:%S.%fZ"

# SPEC §2.2 plausibility bound: offsets beyond ±1000 s are implausible for NTP.
PLAUSIBILITY_BOUND_S = 1000.0
# Post-enrichment row check: nist_time must be within 24 h of the original event.
PLAUSIBLE_NIST_DELTA_H = 24.0
# SPEC §4 Phase 3 bounded loop — a small fixed maximum iteration count.
MAX_ITERATIONS = 3

SKIP_NTP_CHAIN_OF_CUSTODY_WARNING = (
    "[ntp-enrichment] CHAIN OF CUSTODY WARNING: --skip-ntp was specified. The output "
    "timeline is NOT NIST-anchored. Per SPEC §4 CLI Flags / §6.4 (ISC2 admissibility), "
    "this run must be documented as such in any evidence package submitted to legal or "
    "regulatory proceedings."
)

NIST_HALT_WARNING = (
    "[ntp-enrichment] HALT: no NIST/NTP time server could be reached (SPEC §3.2). "
    "Verify outbound UDP/123 connectivity from the SIFT workstation. Proceeding without "
    "an authoritative time anchor means timestamps are not NIST-anchored; per ISC2 "
    "chain-of-custody guidance this must be documented if the timeline is submitted as "
    "legal evidence."
)


# --- enrichment -------------------------------------------------------------


def _sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def _parse_event_ts(row: dict) -> Optional[datetime]:
    """Parse date+time columns into an aware UTC datetime, or None on error."""
    try:
        dt_str = f"{row['date']} {row['time']}"
        naive = datetime.strptime(dt_str, f"{PLASO_DATE_FMT} {PLASO_TIME_FMT}")
        return naive.replace(tzinfo=timezone.utc)
    except (KeyError, ValueError, TypeError):
        return None


def _compute_nist_time(event_ts: datetime, offset_s: float) -> datetime:
    """nist_time = event_ts - offset. Positive offset (clock ahead) → subtract."""
    return event_ts - timedelta(seconds=offset_s)


def _reject_forbidden_path(output_path: Path) -> None:
    s = str(output_path)
    for prefix in _FORBIDDEN_OUTPUT_PREFIXES:
        if s.startswith(prefix):
            raise ValueError(
                f"Output path {output_path} is inside a protected evidence directory "
                f"({prefix}). Write to ./exports/ (SPEC §8) instead."
            )


def enrich(csv_path: str | Path, ctx: NTPContext, output_path: str | Path) -> dict:
    """Enrich a Plaso CSV with the five SPEC §2.2 columns; write sorted output.

    Returns a summary dict. Raises ValueError if output_path targets a protected
    evidence prefix; RuntimeError if the source file hash changes during the run.
    """
    csv_path = Path(csv_path)
    output_path = Path(output_path)
    _reject_forbidden_path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    hash_before = _sha256_file(csv_path)

    # --skip-ntp (null context): pass the original columns through unchanged.
    if not ctx.ntp_source:
        print(SKIP_NTP_CHAIN_OF_CUSTODY_WARNING, file=sys.stderr)
        shutil.copy2(csv_path, output_path)
        return {
            "rows_processed": 0,
            "source_hash_before": hash_before,
            "source_hash_after": _sha256_file(csv_path),
            "integrity_ok": True,
            "output_path": str(output_path),
            "skip_ntp": True,
            "chain_of_custody_warning": SKIP_NTP_CHAIN_OF_CUSTODY_WARNING,
        }

    df = pd.read_csv(csv_path, dtype=str, keep_default_na=False)

    rows_out: list[dict] = []
    for _, row in df.iterrows():
        r = dict(row)
        # Per-event offset: an EID 260 row carries its own Phase Offset.
        if extract_eid_number(r) == 260:
            per_event = extract_phase_offset_s(r.get("desc", ""))
            offset = per_event if per_event is not None else ctx.ntp_offset_s
        else:
            offset = ctx.ntp_offset_s

        event_ts = _parse_event_ts(r)
        if event_ts is not None:
            r["nist_time"] = _compute_nist_time(event_ts, offset).strftime(
                "%Y-%m-%d %H:%M:%S.%f"
            )[:-3] + "Z"
        else:
            r["nist_time"] = ""

        r["ntp_source"] = ctx.ntp_source
        r["ntp_offset_s"] = round(offset, 7)
        r["ntp_assumption"] = ctx.ntp_assumption
        r["nist_delta_s"] = round(offset, 7)  # SPEC §2.2: nist_delta_s == ntp_offset_s
        rows_out.append(r)

    out_df = pd.DataFrame(rows_out)
    # Enforce exact SPEC §2.2 column order: original Plaso columns, then the five
    # new columns in spec order (regardless of dict-insertion order above).
    out_df = out_df[list(df.columns) + NEW_COLUMNS]
    if not out_df.empty:
        out_df = out_df.sort_values("nist_time", kind="stable")
    out_df.to_csv(output_path, index=False)

    hash_after = _sha256_file(csv_path)
    if hash_before != hash_after:
        raise RuntimeError(
            f"EVIDENCE INTEGRITY VIOLATION: {csv_path} was modified during enrichment. "
            f"before={hash_before[:12]}… after={hash_after[:12]}…"
        )

    return {
        "rows_processed": len(out_df),
        "source_hash_before": hash_before,
        "source_hash_after": hash_after,
        "integrity_ok": True,
        "output_path": str(output_path),
        "skip_ntp": False,
    }


# --- self-correction (SPEC §4 Phase 3) --------------------------------------


@dataclass(frozen=True, slots=True)
class ValidationResult:
    valid: bool
    reason: str = ""

    def __bool__(self) -> bool:
        return self.valid


@dataclass(frozen=True, slots=True)
class UnresolvedRow:
    row_id: str
    rejection_basis: str


@dataclass(frozen=True, slots=True)
class CorrectionResult:
    result: dict
    final_context: NTPContext
    iterations: int
    unresolved: list[UnresolvedRow] = field(default_factory=list)


def validate_context(ctx: NTPContext) -> ValidationResult:
    """Pre-enrichment plausibility check (SPEC §2.2): |offset| ≤ ±1000 s."""
    if abs(ctx.ntp_offset_s) > PLAUSIBILITY_BOUND_S:
        return ValidationResult(
            False,
            f"ntp_offset_s={ctx.ntp_offset_s:.4f} exceeds plausibility bound "
            f"±{PLAUSIBILITY_BOUND_S} s (SPEC §2.2)",
        )
    return ValidationResult(True)


def validate_enriched_row(row: dict) -> ValidationResult:
    """Post-enrichment check: nist_time within 24 h of the original event."""
    try:
        event_ts = _parse_event_ts(row)
        nist_ts = datetime.strptime(row["nist_time"], NIST_TIME_FMT).replace(
            tzinfo=timezone.utc
        )
        if event_ts is None:
            return ValidationResult(False, "unparseable event timestamp")
        delta_h = abs((nist_ts - event_ts).total_seconds()) / 3600
        if delta_h > PLAUSIBLE_NIST_DELTA_H:
            return ValidationResult(
                False, f"nist_time delta {delta_h:.1f} h exceeds {PLAUSIBLE_NIST_DELTA_H} h"
            )
    except (KeyError, ValueError, TypeError) as exc:
        return ValidationResult(False, str(exc))
    return ValidationResult(True)


def _check_enriched_rows(output_path: Path) -> list[UnresolvedRow]:
    """Flag rows whose written ntp_offset_s exceeds the ±1000 s bound (SPEC §4 Ph3)."""
    unresolved: list[UnresolvedRow] = []
    try:
        df = pd.read_csv(output_path, dtype=str, keep_default_na=False)
    except (FileNotFoundError, pd.errors.EmptyDataError):
        return unresolved
    for idx, row in df.iterrows():
        try:
            offset = float(row.get("ntp_offset_s", "0"))
        except (TypeError, ValueError):
            continue
        if abs(offset) > PLAUSIBILITY_BOUND_S:
            unresolved.append(
                UnresolvedRow(
                    row_id=str(idx),
                    rejection_basis=(
                        f"ntp_offset_s={offset:.4f} exceeds plausibility bound "
                        f"±{PLAUSIBILITY_BOUND_S} s (SPEC §2.2)"
                    ),
                )
            )
    return unresolved


def validate_and_correct(
    csv_path: str | Path,
    ctx: NTPContext,
    output_path: str | Path,
    resolver_fn: Callable[[int], NTPContext],
    max_iterations: int = MAX_ITERATIONS,
) -> CorrectionResult:
    """Run enrich(); if the offset is implausible, RE-RESOLVE the source and retry.

    ``resolver_fn(iteration)`` returns a fresh NTPContext (re-resolution with whatever
    updated information is available). The loop is bounded by ``max_iterations``; when
    it exhausts without a plausible offset it returns a halt summary listing the
    unresolved rows (SPEC §4 Phase 3) — it never silently zeroes the offset.
    """
    current = ctx
    iterations = 0
    while True:
        pre = validate_context(current)
        if pre.valid:
            result = enrich(csv_path, current, output_path)
            unresolved = _check_enriched_rows(Path(output_path))
            if not unresolved:
                return CorrectionResult(result, current, iterations, [])
        else:
            unresolved = [UnresolvedRow("context", pre.reason)]

        iterations += 1
        if iterations >= max_iterations:
            return CorrectionResult({}, current, iterations, unresolved)
        current = resolver_fn(iterations)


# --- CLI (SPEC §4 CLI Flags) ------------------------------------------------


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="ntp_enricher.py",
        description="NIST-anchored NTP enrichment for a Plaso l2tcsv timeline.",
    )
    p.add_argument("--input", required=True, help="Plaso l2tcsv export (read-only)")
    p.add_argument("--output", required=True, help="enriched CSV path (under ./exports/)")
    p.add_argument("--case-dir", default=None, help="case directory (context only)")
    p.add_argument("--ntp-source", default=None, help="skip the Phase 2 prompt; use this source")
    p.add_argument("--skip-ntp", action="store_true", help="bypass enrichment entirely")
    p.add_argument("--nist-server", default=None, help="override the NIST server hostname")
    p.add_argument("--skip-nist-check", action="store_true", help="skip the live NIST query (offline/testing)")
    p.add_argument("--hosting", default="unknown", choices=["aws", "azure", "on_prem", "unknown"])
    p.add_argument("--host-os", default="unknown", choices=["windows", "linux", "unknown"])
    p.add_argument("--linux-distro", default="unknown")
    p.add_argument("--windows-domain-joined", action="store_true")
    p.add_argument("--non-interactive", action="store_true", help="never prompt the analyst")
    return p


def _preflight(args: argparse.Namespace) -> None:
    """Validate critical preconditions before opening the audit session.

    Failures here produce a descriptive [ntp-enrichment] ERROR to stderr and
    exit 1 — before any SiftSession JSONL file is created, so the analyst can
    fix the configuration without a partial audit trail to clean up.
    """
    errors: list[str] = []

    input_path = Path(args.input)
    if not input_path.exists():
        errors.append(f"Input file not found: {input_path}")
    elif not input_path.is_file():
        errors.append(f"Input path is not a regular file: {input_path}")

    output_parent = Path(args.output).parent
    try:
        output_parent.mkdir(parents=True, exist_ok=True)
    except PermissionError as exc:
        errors.append(f"Output directory not writable: {output_parent} — {exc}")

    for module in ("ntp_manifest", "ntp_nist_client", "sift_logger", "ntp_resolver"):
        try:
            __import__(module)
        except ImportError as exc:
            errors.append(f"Required module not importable: {module} — {exc}")

    if errors:
        for msg in errors:
            print(f"[ntp-enrichment] ERROR: {msg}", file=sys.stderr)
        sys.exit(1)


def main(argv: Optional[list[str]] = None) -> int:
    args = build_parser().parse_args(argv)
    _preflight(args)

    # Import here so the module imports cleanly even if siblings are absent.
    import ntp_manifest
    from ntp_nist_client import DEFAULT_SERVERS, NistUnreachable, query
    from sift_logger import SiftSession

    csv_path = Path(args.input)
    output_path = Path(args.output)
    output_dir = output_path.parent

    resolve_kwargs = dict(
        cli_ntp_source=args.ntp_source,
        skip_ntp=args.skip_ntp,
        interactive=not args.non_interactive,
        hosting=args.hosting,
        host_os=args.host_os,
        linux_distro=args.linux_distro,
        windows_domain_joined=args.windows_domain_joined,
    )

    with SiftSession("ntp-enrichment", case_dir=args.case_dir, input=args.input) as sess:
        sess.log(
            "tool_called",
            tool_name="ntp_enricher.py",
            tool_input=vars(args),
            reasoning="Parsing CLI arguments to determine NTP enrichment configuration.",
        )

        df = pd.read_csv(csv_path, dtype=str, keep_default_na=False)
        ctx = resolve_ntp_source(df, **resolve_kwargs)
        sess.log(
            "ntp_resolution",
            ntp_source=ctx.ntp_source or "",
            confidence_rank=int(ctx.confidence_rank) if ctx.ntp_source else None,
            assumption=ctx.ntp_assumption,
            files_accessed=[args.input],
            reasoning="Phase 2: resolving NTP source from artifact logs and CLI hints (SPEC §4 Phase 2).",
        )

        # --skip-ntp: pass through, emit manifest, done.
        if args.skip_ntp or not ctx.ntp_source:
            sess.log(
                "skip_ntp_warning",
                warning=SKIP_NTP_CHAIN_OF_CUSTODY_WARNING,
                reasoning="--skip-ntp flag set or no NTP source resolved; bypassing enrichment per analyst instruction.",
            )
            result = enrich(csv_path, NTPContext(), output_path)
            report = ntp_manifest.emit(ctx, [], result, output_dir, cli_args=vars(args))
            print(f"[ntp-enrichment] accuracy report: {report}")
            sess.set_exit_code(0)
            return 0

        # NIST validation query (fail closed on total unreachability — SPEC §3.2).
        nist = None
        if not args.skip_nist_check:
            servers = (args.nist_server,) if args.nist_server else DEFAULT_SERVERS
            try:
                nist = query(servers)
                print(
                    f"[ntp-enrichment] NIST: {nist.server_used} responded "
                    f"(offset={nist.offset_s:+.4f}s stratum={nist.stratum})"
                )
                sess.log(
                    "nist_query",
                    server=nist.server_used,
                    offset_s=nist.offset_s,
                    stratum=nist.stratum,
                    reachable=True,
                    reasoning="Validating resolved NTP source against NIST reference per SPEC §3.2.",
                )
            except NistUnreachable:
                sess.log(
                    "nist_query",
                    reachable=False,
                    is_error=True,
                    message=NIST_HALT_WARNING,
                    reasoning="All NIST servers unreachable; halting per SPEC §3.2 fail-closed policy.",
                )
                print(NIST_HALT_WARNING, file=sys.stderr)
                sess.set_exit_code(2)
                return 2

        resolver_fn = lambda _i: resolve_ntp_source(df, **resolve_kwargs)  # noqa: E731
        correction = validate_and_correct(csv_path, ctx, output_path, resolver_fn)

        if correction.result:
            sess.log(
                "evidence_integrity",
                path=args.input,
                sha256_before=correction.result.get("source_hash_before", ""),
                sha256_after=correction.result.get("source_hash_after", ""),
                ok=correction.result.get("integrity_ok", True),
                files_accessed=[args.input],
                reasoning="Verifying source CSV was not modified during enrichment (chain of custody).",
            )

        enriched_rows: list[dict] = []
        if correction.result.get("output_path"):
            try:
                enriched_rows = pd.read_csv(
                    correction.result["output_path"], dtype=str, keep_default_na=False
                ).to_dict("records")
            except (FileNotFoundError, pd.errors.EmptyDataError):
                enriched_rows = []

        # On a halt the correction has no output CSV; still name the report after the
        # requested --output path so it is discoverable next to the case.
        result = dict(correction.result)
        result.setdefault("output_path", str(output_path))
        report = ntp_manifest.emit(
            correction.final_context,
            enriched_rows,
            result,
            output_dir,
            unresolved_rows=correction.unresolved,
            nist=nist,
            cli_args=vars(args),
        )
        print(f"[ntp-enrichment] accuracy report: {report}")

        if correction.unresolved:
            sess.log(
                "enrichment_halted",
                iterations=correction.iterations,
                unresolved_count=len(correction.unresolved),
                is_error=True,
                reasoning=(
                    f"Phase 3 self-correction exhausted {correction.iterations} iteration(s) "
                    f"with {len(correction.unresolved)} rows still outside "
                    f"±1000s plausibility bound (SPEC §4 Phase 3)."
                ),
            )
            print(
                f"[ntp-enrichment] HALT after {correction.iterations} iteration(s): "
                f"{len(correction.unresolved)} unresolved row(s) (SPEC §4 Phase 3).",
                file=sys.stderr,
            )
            sess.set_exit_code(3)
            return 3

        sess.log(
            "enrichment_complete",
            rows_processed=correction.result.get("rows_processed", 0),
            ntp_source=correction.final_context.ntp_source,
            assumption=correction.final_context.ntp_assumption,
            rank=int(correction.final_context.confidence_rank),
            output_path=correction.result.get("output_path", ""),
            files_accessed=[args.input],
            reasoning="Enrichment complete; all rows within ±1000s plausibility bound.",
        )
        print(
            f"[ntp-enrichment] done: {correction.result.get('rows_processed', 0)} rows, "
            f"source={correction.final_context.ntp_source}, "
            f"assumption={correction.final_context.ntp_assumption}, "
            f"rank={int(correction.final_context.confidence_rank)}"
        )
        sess.set_exit_code(0)
        return 0


if __name__ == "__main__":
    sys.exit(main())
