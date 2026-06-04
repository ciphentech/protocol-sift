"""Unit tests for EID 35/260 extraction (FEATURE 2, SPEC §2.2)."""

import pytest

from ntp_resolver import (
    extract_eid35_offset_s,
    extract_ntp_source_hostname,
    extract_phase_offset_s,
)

EID35 = "Strings: ['base-dc.shieldbase.lan', '-4007']"


def test_eid35_extracts_ntp_offset_seconds():
    assert extract_eid35_offset_s(EID35) == pytest.approx(-0.0004007)


def test_eid35_extracts_ntp_hostname():
    assert extract_ntp_source_hostname(EID35) == "base-dc.shieldbase.lan"


def test_eid260_extracts_phase_offset_negative():
    assert extract_phase_offset_s("Phase Offset: -0.0004007s") == pytest.approx(-0.0004007)


def test_eid260_extracts_phase_offset_positive():
    assert extract_phase_offset_s("Phase Offset: 0.0279051s") == pytest.approx(0.0279051)


def test_eid260_strips_trailing_s():
    result = extract_phase_offset_s("Phase Offset: -0.0032941s")
    assert isinstance(result, float)
    assert result == pytest.approx(-0.0032941)
