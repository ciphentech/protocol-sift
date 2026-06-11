"""Unit tests for the CLI wiring (FEATURE 6, SPEC §4 CLI Flags)."""

import glob
import json

import pandas as pd
import pytest

from ntp_enricher import NEW_COLUMNS, build_parser, main


def test_help_exits_zero():
    with pytest.raises(SystemExit) as exc:
        build_parser().parse_args(["--help"])
    assert exc.value.code == 0


def test_parser_reads_skip_ntp_flag():
    args = build_parser().parse_args(["--input", "a.csv", "--output", "b.csv", "--skip-ntp"])
    assert args.skip_ntp is True
    assert args.input == "a.csv"


def test_happy_path_produces_report(mini_csv_path, tmp_path):
    out = tmp_path / "case1" / "ntp_mini_enriched.csv"
    rc = main(["--input", str(mini_csv_path), "--output", str(out),
               "--skip-nist-check", "--non-interactive"])
    assert rc == 0
    reports = glob.glob(str(tmp_path / "case1" / "*_accuracy_report.json"))
    assert len(reports) == 1
    assert out.exists()


def test_skip_ntp_passthrough_warns(mini_csv_path, tmp_path, capsys):
    out = tmp_path / "case2" / "ntp_mini_enriched.csv"
    rc = main(["--input", str(mini_csv_path), "--output", str(out),
               "--skip-ntp", "--non-interactive"])
    assert rc == 0
    assert "CHAIN OF CUSTODY WARNING" in capsys.readouterr().err
    assert out.exists()


# G5: --skip-ntp output schema (SPEC §4 CLI Flags / §6.4).


def test_skip_ntp_adds_no_enrichment_columns(mini_csv_path, tmp_path, capsys):
    out = tmp_path / "case3" / "ntp_mini_passthrough.csv"
    rc = main(["--input", str(mini_csv_path), "--output", str(out),
               "--skip-ntp", "--non-interactive"])
    assert rc == 0
    src_cols = list(pd.read_csv(mini_csv_path, dtype=str, keep_default_na=False).columns)
    out_cols = list(pd.read_csv(out, dtype=str, keep_default_na=False).columns)
    # Pass-through: none of the five enrichment fields, originals untouched.
    assert out_cols == src_cols
    assert not set(NEW_COLUMNS) & set(out_cols)
    assert "CHAIN OF CUSTODY WARNING" in capsys.readouterr().err
    # §6.4: the warning is recorded in the accuracy report, not just printed.
    reports = glob.glob(str(tmp_path / "case3" / "*_accuracy_report.json"))
    assert len(reports) == 1
    report = json.loads(open(reports[0]).read())
    assert report["skip_ntp"] is True
    assert "CHAIN OF CUSTODY" in report["chain_of_custody_warning"]
