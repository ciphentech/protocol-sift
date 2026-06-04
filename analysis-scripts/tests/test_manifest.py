"""Unit tests for the SPEC §2.3 accuracy report (FEATURE 8)."""

import json

from ntp_enricher import UnresolvedRow
from ntp_manifest import emit
from ntp_resolver import NTPContext


def _result(tmp_path, rows=2):
    return {"rows_processed": rows, "integrity_ok": True,
            "source_hash_before": "h", "source_hash_after": "h",
            "output_path": str(tmp_path / "out.csv")}


def test_report_has_spec_2_3_required_fields(tmp_path):
    ctx = NTPContext(ntp_source="dc01", ntp_offset_s=-0.0004, ntp_assumption=False,
                     confidence_rank=1, source_eid=260)
    rows = [{"ntp_source": "dc01", "ntp_assumption": "False", "ntp_offset_s": "-0.0004"}] * 2
    report = json.loads(emit(ctx, rows, _result(tmp_path), tmp_path).read_text())
    for field in ("rows_total", "rows_assumption_true", "confidence_rank_distribution",
                  "assumption_bases", "spec_caveats_applicable", "unresolved_rows"):
        assert field in report, f"SPEC §2.3 field {field} missing"


def test_report_flags_unresolved_at_bound(tmp_path):
    ctx = NTPContext(ntp_source="dc01", ntp_assumption=True, confidence_rank=6)
    rows = [{"ntp_source": "dc01", "ntp_assumption": "True", "ntp_offset_s": "5000.0"}]
    unresolved = [UnresolvedRow("42", "ntp_offset_s=5000.0 exceeds ±1000.0 s (SPEC §2.2)")]
    report = json.loads(
        emit(ctx, rows, _result(tmp_path, 1), tmp_path, unresolved_rows=unresolved).read_text()
    )
    assert len(report["unresolved_rows"]) == 1
    assert report["unresolved_rows"][0]["row_id"] == "42"
    assert "1000" in report["unresolved_rows"][0]["rejection_basis"]


def test_rank_distribution_derives_from_context(tmp_path):
    # Distribution comes from the single context rank over all rows — not a per-row col.
    ctx = NTPContext(ntp_source="dc01", ntp_offset_s=-0.0004, ntp_assumption=False,
                     confidence_rank=1, source_eid=260)
    rows = [{"ntp_assumption": "False"}] * 2
    report = json.loads(emit(ctx, rows, _result(tmp_path, 2), tmp_path).read_text())
    assert report["confidence_rank_distribution"] == {"1": 2}


def test_assumption_basis_derives_from_context(tmp_path):
    ctx = NTPContext(ntp_source="pool.ntp.org", ntp_assumption=True, confidence_rank=6)
    rows = [{"ntp_assumption": "True"}] * 3
    report = json.loads(emit(ctx, rows, _result(tmp_path, 3), tmp_path).read_text())
    assert len(report["assumption_bases"]) == 1
    assert report["assumption_bases"][0]["confidence_rank"] == 6
    assert report["assumption_bases"][0]["assumed_ntp_source"] == "pool.ntp.org"
