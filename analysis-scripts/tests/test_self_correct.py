"""Unit tests for the self-correction loop (FEATURE 7, SPEC §4 Phase 3)."""

from ntp_enricher import (
    MAX_ITERATIONS,
    validate_and_correct,
    validate_context,
    validate_enriched_row,
)
from ntp_resolver import NTPContext


def test_validate_context_rejects_implausible_offset():
    vr = validate_context(NTPContext(ntp_source="dc01", ntp_offset_s=99999.0,
                                     ntp_assumption=True, confidence_rank=6))
    assert not vr.valid
    assert "1000" in vr.reason


def test_validate_enriched_row_rejects_more_than_24h():
    row = {"date": "08/30/2018", "time": "02:05:15",
           "nist_time": "2019-01-01 02:05:15.000Z"}
    assert not validate_enriched_row(row).valid


def test_self_correction_reruns_and_re_resolves(mini_csv_path, tmp_path):
    bad = NTPContext(ntp_source="base-dc", ntp_offset_s=50000.0,
                     ntp_assumption=False, confidence_rank=1, source_eid=35)
    good = NTPContext(ntp_source="Domain Controller", ntp_offset_s=0.0,
                      ntp_assumption=True, confidence_rank=5)
    cr = validate_and_correct(mini_csv_path, bad, tmp_path / "out.csv",
                              resolver_fn=lambda i: good)
    # Re-resolved to a different source — not a blind reset of the offset to 0.
    assert cr.final_context.ntp_source == "Domain Controller"
    assert cr.final_context.ntp_assumption is True
    assert cr.iterations == 1
    assert cr.unresolved == []


def test_self_correction_caps_at_max_iterations(mini_csv_path, tmp_path):
    bad = NTPContext(ntp_source="x", ntp_offset_s=5000.0, ntp_assumption=True,
                     confidence_rank=6)
    cr = validate_and_correct(mini_csv_path, bad, tmp_path / "out.csv",
                              resolver_fn=lambda i: bad)
    assert cr.iterations == MAX_ITERATIONS
    assert cr.result == {}


def test_self_correction_halt_summary_lists_unresolved(mini_csv_path, tmp_path):
    bad = NTPContext(ntp_source="x", ntp_offset_s=5000.0, ntp_assumption=True,
                     confidence_rank=6)
    cr = validate_and_correct(mini_csv_path, bad, tmp_path / "out.csv",
                              resolver_fn=lambda i: bad)
    assert len(cr.unresolved) >= 1
    assert cr.unresolved[0].row_id == "context"
    assert "1000" in cr.unresolved[0].rejection_basis
