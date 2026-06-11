"""Shared fixtures for the NTP enrichment tests."""

import json
from pathlib import Path

import pytest

FIXTURES = Path(__file__).parent / "fixtures"


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
