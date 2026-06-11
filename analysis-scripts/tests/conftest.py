"""Shared fixtures for the NTP enrichment tests."""

import json
from pathlib import Path

import pytest

FIXTURES = Path(__file__).parent / "fixtures"


@pytest.fixture(autouse=True)
def _isolated_logs_dir(tmp_path, monkeypatch):
    """Keep test session logs out of the real ~/.protocol-sift logs dir."""
    try:
        import sift_logger
    except ImportError:  # not built yet (P-01..P-05 stages of the series)
        return
    monkeypatch.setattr(sift_logger, "LOGS_DIR", tmp_path / "logs")


@pytest.fixture
def mini_csv_path():
    return FIXTURES / "ntp_mini.csv"


@pytest.fixture
def no_eids_csv_path():
    return FIXTURES / "ntp_mini_no_eids.csv"


@pytest.fixture
def implausible_csv_path():
    return FIXTURES / "ntp_mini_implausible.csv"


@pytest.fixture
def spoliation_csv_path():
    return FIXTURES / "ntp_spoliation.csv"


@pytest.fixture
def ground_truth():
    return json.loads((FIXTURES / "expected_ntp_ground_truth.json").read_text())
