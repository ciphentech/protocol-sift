"""Assumption transparency and accuracy report for Protocol SIFT.

FEATURE 8 — Assumption Transparency and Accuracy Report (SPEC §2.3)

Flat analysis-script. Emits the SPEC §2.3 accuracy report JSON alongside the enriched
timeline. The report is built from the run's single ``NTPContext`` plus the enriched
rows' real columns and the self-correction loop's unresolved-row summary — never from a
per-row ``confidence_rank`` column (the SPEC §2.2 schema does not add one; one context is
resolved per case).

Security: read-only over already-produced output; writes only to the caller-provided
output directory; no shell, eval, or deserialization of untrusted data. JSON is emitted
with ``json.dumps`` (no template injection surface).
"""

from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable, Optional

from ntp_resolver import ConfidenceRank, NTPContext

# SPEC §6 caveat IDs the report may surface for a run (mirror §6.1–§6.6 exactly).
_SPEC_CAVEATS = {
    "6.1": "NTP source assumed when no logs available",
    "6.2": "Historical NTP drift not directly observable",
    "6.3": "Variable clock drift over time",
    "6.4": "ISC2 / legal admissibility requires disclosure",
    "6.5": "NIST as ground truth — network transmission delay",
    "6.6": "Unencrypted NTP transport — proof-of-concept only",
}

# Human-readable basis per confidence rank (SPEC §4 Phase 2 Detail), so every
# assumption is reproducible.
_RANK_BASIS = {
    ConfidenceRank.LOG_DERIVED: "Recovered from artifact NTP logs (EID 35/260)",
    ConfidenceRank.ANALYST_CONFIRMED: "Analyst-provided and consistent with log evidence",
    ConfidenceRank.ANALYST_UNVERIFIED: "Analyst-provided, no logs to cross-check",
    ConfidenceRank.CLOUD_DEFAULT: "Cloud provider default for the hosting environment",
    ConfidenceRank.DOMAIN_DEFAULT: "On-prem Windows domain/standalone default",
    ConfidenceRank.DISTRO_DEFAULT: "Linux distro / unknown NTP pool default",
}


def applicable_caveats(ctx: NTPContext) -> list[str]:
    """SPEC §2.3: the §6 caveats that apply to this run."""
    caveats = ["6.5", "6.6"]  # always applicable (NIST ground truth + unencrypted NTP)
    if ctx.ntp_assumption:
        caveats.insert(0, "6.1")  # an assumption was used
        caveats.append("6.4")     # disclosure required
    caveats.extend(["6.2", "6.3"])  # historical / drift caveats
    # de-dupe, preserve order
    seen: set[str] = set()
    ordered = [c for c in caveats if not (c in seen or seen.add(c))]
    return [f"{c}: {_SPEC_CAVEATS[c]}" for c in ordered]


def _assumption_bases(ctx: NTPContext, rows_total: int) -> list[dict]:
    """One reproducible basis entry when the source was assumed (SPEC §2.3)."""
    if not ctx.ntp_assumption:
        return []
    rank = ConfidenceRank(int(ctx.confidence_rank))
    return [
        {
            "assumed_ntp_source": ctx.ntp_source,
            "confidence_rank": int(ctx.confidence_rank),
            "rows_affected": rows_total,
            "basis": _RANK_BASIS.get(rank, "assumed"),
        }
    ]


def emit(
    ctx: NTPContext,
    enriched_rows: list[dict],
    result: dict,
    output_dir: str | Path,
    unresolved_rows: Optional[Iterable] = None,
    nist=None,
    cli_args: Optional[dict] = None,
) -> Path:
    """Write the SPEC §2.3 accuracy report; return its path.

    ``unresolved_rows`` is the self-correction loop's halt summary (objects with
    ``row_id`` / ``rejection_basis``). One bounded loop → one halt summary; no
    per-iteration files.
    """
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    stem = Path(result.get("output_path", "timeline")).stem
    report_path = output_dir / f"{stem}_accuracy_report.json"

    rows_total = result.get("rows_processed", len(enriched_rows))
    rows_assumption_true = sum(
        1
        for r in enriched_rows
        if str(r.get("ntp_assumption", "")).lower() == "true"
    )
    # One context per case → the distribution is that single rank over all rows.
    rank_distribution = {str(int(ctx.confidence_rank)): rows_total} if rows_total else {}

    unresolved_list = [
        {"row_id": str(u.row_id), "rejection_basis": str(u.rejection_basis)}
        for u in (unresolved_rows or [])
    ]

    report = {
        # SPEC §2.3 required fields
        "rows_total": rows_total,
        "rows_assumption_true": rows_assumption_true,
        "confidence_rank_distribution": rank_distribution,
        "assumption_bases": _assumption_bases(ctx, rows_total),
        "spec_caveats_applicable": applicable_caveats(ctx),
        # SPEC §4 Phase 3 halt summary (empty when nothing is unresolved)
        "unresolved_rows": unresolved_list,
        # Reproducibility / submission item #8 metadata
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "ntp_context": ctx.to_dict(),
        "nist_query": (
            {
                "server_used": nist.server_used,
                "offset_s": nist.offset_s,
                "stratum": nist.stratum,
                "queried_at_utc": nist.queried_at_utc,
            }
            if nist is not None
            else None
        ),
        "integrity_ok": result.get("integrity_ok", False),
        "source_hash_before": result.get("source_hash_before", ""),
        "source_hash_after": result.get("source_hash_after", ""),
        "skip_ntp": bool(result.get("skip_ntp", False)),
        "chain_of_custody_warning": result.get("chain_of_custody_warning", ""),
        "output_path": result.get("output_path", ""),
        "cli_args": cli_args or {},
    }

    try:
        report_path.write_text(json.dumps(report, indent=2))
    except OSError as exc:
        print(
            f"[ntp-manifest] ERROR: Could not write accuracy report to {report_path}: {exc}",
            file=sys.stderr,
        )
        raise
    return report_path
