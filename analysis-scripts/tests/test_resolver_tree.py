"""Unit tests for the Phase 2 resolution decision tree (FEATURE 4, SPEC §4)."""

import pandas as pd
import pytest

from ntp_resolver import resolve_ntp_source


class PromptRecorder:
    """Fake prompt_fn that records every prompt and replays canned answers."""

    def __init__(self, answers=()):
        self.answers = list(answers)
        self.prompts = []

    def __call__(self, message):
        self.prompts.append(message)
        return self.answers.pop(0) if self.answers else ""


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


# --- G1: interactive Phase 2 prompt flow (FEATURES "one or two short prompts") ---


def test_interactive_asks_ntp_source_first(no_eids_csv_path):
    rec = PromptRecorder(["mydc.corp.local"])
    ctx = resolve_ntp_source(_df(no_eids_csv_path), interactive=True, prompt_fn=rec)
    assert "NTP source" in rec.prompts[0]
    # An answered first prompt resolves immediately — no follow-up.
    assert len(rec.prompts) == 1
    assert ctx.ntp_source == "mydc.corp.local"
    assert ctx.ntp_assumption is False
    assert ctx.confidence_rank == 3


def test_interactive_followup_asks_cloud_or_onprem(no_eids_csv_path):
    rec = PromptRecorder(["", "aws"])
    ctx = resolve_ntp_source(_df(no_eids_csv_path), interactive=True, prompt_fn=rec)
    assert len(rec.prompts) == 2
    assert "cloud" in rec.prompts[1].lower()
    assert "on-prem" in rec.prompts[1].lower()
    # The follow-up answer narrows the fallback to the cloud default.
    assert ctx.ntp_source == "169.254.169.123"
    assert ctx.ntp_assumption is True
    assert ctx.confidence_rank == 4


def test_interactive_followup_gcp_offers_cloud_default(no_eids_csv_path):
    rec = PromptRecorder(["", "gcp"])
    ctx = resolve_ntp_source(_df(no_eids_csv_path), interactive=True, prompt_fn=rec)
    assert len(rec.prompts) == 2
    assert "gcp" in rec.prompts[1].lower()
    # The follow-up answer narrows the fallback to the GCP default.
    assert ctx.ntp_source == "metadata.google.internal"
    assert ctx.ntp_assumption is True
    assert ctx.confidence_rank == 4


def test_interactive_never_more_than_two_prompts(no_eids_csv_path):
    rec = PromptRecorder(["", ""])  # decline both prompts
    ctx = resolve_ntp_source(_df(no_eids_csv_path), interactive=True, prompt_fn=rec)
    assert len(rec.prompts) <= 2
    # Both declined → assumption fallback, never a third question.
    assert ctx.ntp_assumption is True
    assert ctx.confidence_rank == 6


# --- G2: --ntp-source cross-check consistency (SPEC §4 Phase 2, ranks 2 vs 3) ---


def test_cli_source_consistent_with_artifact_sets_rank2(mini_csv_path):
    ctx = resolve_ntp_source(_df(mini_csv_path),
                             cli_ntp_source="base-dc.shieldbase.lan")
    assert ctx.confidence_rank == 2
    assert ctx.ntp_assumption is False
    assert ctx.ntp_source == "base-dc.shieldbase.lan"
    # The artifact's recovered offset is kept, not zeroed.
    assert abs(ctx.ntp_offset_s - (-0.0004007)) < 1e-7


def test_cli_source_inconsistent_flags_for_phase3(mini_csv_path):
    ctx = resolve_ntp_source(_df(mini_csv_path), cli_ntp_source="rogue.example.com")
    # The stated source is NOT silently accepted: the artifact (higher
    # confidence) wins, surfacing the discrepancy for the manifest / Phase 3.
    assert ctx.ntp_source != "rogue.example.com"
    assert ctx.ntp_source == "base-dc.shieldbase.lan"
    assert ctx.confidence_rank == 1
    assert ctx.source_eid == 35


# --- G3: assumption-fallback branch matrix (SPEC §4 Phase 2, ranks 4-6) ---


@pytest.mark.parametrize(
    "kwargs,expected_source,expected_rank",
    [
        (dict(hosting="aws"), "169.254.169.123", 4),
        (dict(hosting="azure"), "time.windows.com", 4),
        (dict(hosting="gcp"), "metadata.google.internal", 4),
        (dict(host_os="windows"), "time.windows.com", 5),  # standalone, no domain
        (dict(host_os="linux", linux_distro="ubuntu"), "ntp.ubuntu.com", 6),
        (dict(host_os="linux", linux_distro="rhel"), "rhel.pool.ntp.org", 6),
        (dict(host_os="linux", linux_distro="debian"), "debian.pool.ntp.org", 6),
        (dict(host_os="linux", linux_distro="arch"), "pool.ntp.org", 6),
    ],
    ids=["aws", "azure", "gcp", "win-standalone", "ubuntu", "rhel", "debian", "other-distro"],
)
def test_assumption_fallback_matrix(no_eids_csv_path, kwargs,
                                    expected_source, expected_rank):
    ctx = resolve_ntp_source(_df(no_eids_csv_path), **kwargs)
    assert ctx.ntp_source == expected_source
    assert ctx.confidence_rank == expected_rank
    assert ctx.ntp_assumption is True
