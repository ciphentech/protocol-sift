"""Unit tests for the Phase 2 resolution decision tree (FEATURE 4, SPEC §4)."""

import pandas as pd

from ntp_resolver import resolve_ntp_source


def _df(path):
    return pd.read_csv(path, dtype=str, keep_default_na=False)


def test_decision_tree_uses_artifact_when_eids_present(mini_csv_path):
    ctx = resolve_ntp_source(_df(mini_csv_path))
    assert ctx.ntp_assumption is False
    assert ctx.confidence_rank == 1
    assert ctx.ntp_source == "base-dc.shieldbase.lan"
    assert abs(ctx.ntp_offset_s - (-0.0004007)) < 1e-7


def test_decision_tree_uses_cli_flag_when_provided(no_eids_csv_path):
    ctx = resolve_ntp_source(_df(no_eids_csv_path), cli_ntp_source="mydc.corp.local")
    assert ctx.ntp_source == "mydc.corp.local"
    assert ctx.ntp_assumption is False
    # No logs to cross-check → ANALYST_UNVERIFIED (rank 3).
    assert ctx.confidence_rank == 3


def test_decision_tree_sets_assumption_true_when_defaulting(no_eids_csv_path):
    ctx = resolve_ntp_source(_df(no_eids_csv_path), host_os="windows",
                             windows_domain_joined=True)
    assert ctx.ntp_assumption is True
    assert ctx.confidence_rank >= 4


def test_decision_tree_windows_domain_default(no_eids_csv_path):
    ctx = resolve_ntp_source(_df(no_eids_csv_path), host_os="windows",
                             windows_domain_joined=True)
    assert ctx.ntp_source == "Domain Controller"
    assert ctx.confidence_rank == 5


def test_decision_tree_returns_null_on_skip_ntp(mini_csv_path):
    ctx = resolve_ntp_source(_df(mini_csv_path), skip_ntp=True)
    assert ctx.ntp_source == ""
    assert ctx.confidence_rank == 6
