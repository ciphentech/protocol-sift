"""Unit tests for enrichment + the safe writer (FEATURE 5 + 1, SPEC §2.2 / §8)."""

import csv
from datetime import datetime, timezone

import pytest

from ntp_enricher import NEW_COLUMNS, _compute_nist_time, enrich
from ntp_resolver import NTPContext


def test_nist_time_negative_offset_shifts_forward():
    event_ts = datetime(2018, 8, 30, 2, 5, 15, tzinfo=timezone.utc)
    assert _compute_nist_time(event_ts, -0.0004007) > event_ts


def test_nist_time_positive_offset_shifts_backward():
    event_ts = datetime(2018, 8, 30, 10, 20, 13, tzinfo=timezone.utc)
    assert _compute_nist_time(event_ts, 0.0032941) < event_ts


def test_nist_time_zero_offset_unchanged():
    event_ts = datetime(2023, 1, 25, 14, 52, 4, tzinfo=timezone.utc)
    assert _compute_nist_time(event_ts, 0.0) == event_ts


def test_nist_delta_s_equals_ntp_offset_s(mini_csv_path, tmp_path):
    ctx = NTPContext(ntp_source="dc01", ntp_offset_s=-0.001, ntp_assumption=False)
    out = tmp_path / "out.csv"
    enrich(mini_csv_path, ctx, out)
    rows = list(csv.DictReader(open(out)))
    for r in rows:
        assert float(r["nist_delta_s"]) == float(r["ntp_offset_s"])


def test_output_preserves_all_original_columns(mini_csv_path, tmp_path):
    ctx = NTPContext(ntp_source="dc01", ntp_offset_s=0.0, ntp_assumption=False)
    out = tmp_path / "out.csv"
    enrich(mini_csv_path, ctx, out)
    original = csv.DictReader(open(mini_csv_path)).fieldnames
    produced = csv.DictReader(open(out)).fieldnames
    for col in original:
        assert col in produced


def test_output_appends_five_columns_in_spec_order(mini_csv_path, tmp_path):
    ctx = NTPContext(ntp_source="dc01", ntp_offset_s=0.0, ntp_assumption=False)
    out = tmp_path / "out.csv"
    enrich(mini_csv_path, ctx, out)
    produced = csv.DictReader(open(out)).fieldnames
    # The last five columns are exactly the SPEC §2.2 columns, in spec order.
    assert produced[-5:] == NEW_COLUMNS
    assert NEW_COLUMNS == ["ntp_source", "nist_time", "ntp_offset_s",
                           "ntp_assumption", "nist_delta_s"]


def test_output_sorted_on_nist_time(mini_csv_path, tmp_path):
    ctx = NTPContext(ntp_source="dc01", ntp_offset_s=0.0, ntp_assumption=False)
    out = tmp_path / "out.csv"
    enrich(mini_csv_path, ctx, out)
    nist_times = [r["nist_time"] for r in csv.DictReader(open(out))]
    assert nist_times == sorted(nist_times)


def test_output_path_rejects_cases_dir(mini_csv_path):
    ctx = NTPContext(ntp_source="dc01", ntp_offset_s=0.0, ntp_assumption=False)
    with pytest.raises(ValueError, match="protected evidence"):
        enrich(mini_csv_path, ctx, "/cases/srl/evil.csv")


def test_output_path_rejects_mnt_dir(mini_csv_path):
    ctx = NTPContext(ntp_source="dc01", ntp_offset_s=0.0, ntp_assumption=False)
    with pytest.raises(ValueError, match="protected evidence"):
        enrich(mini_csv_path, ctx, "/mnt/rd01/evil.csv")


def test_source_csv_hash_unchanged_after_enrich(mini_csv_path, tmp_path):
    ctx = NTPContext(ntp_source="dc01", ntp_offset_s=0.0, ntp_assumption=False)
    result = enrich(mini_csv_path, ctx, tmp_path / "out.csv")
    assert result["integrity_ok"] is True
    assert result["source_hash_before"] == result["source_hash_after"]
