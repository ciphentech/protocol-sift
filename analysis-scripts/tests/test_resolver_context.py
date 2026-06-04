"""Unit tests for the NTPContext data model (SPEC §2.2 / §4)."""

import math

import pytest
from dataclasses import FrozenInstanceError

from ntp_resolver import ConfidenceRank, NTPContext


def test_ntpcontext_dataclass_fields():
    ctx = NTPContext(ntp_source="dc01", ntp_offset_s=-0.001, ntp_assumption=False,
                     confidence_rank=1, source_eid=260)
    assert ctx.ntp_source == "dc01"
    assert ctx.ntp_offset_s == -0.001
    assert ctx.ntp_assumption is False
    assert ctx.confidence_rank == 1
    assert ctx.source_eid == 260


def test_ntpcontext_rejects_non_numeric_offset():
    with pytest.raises(TypeError, match="numeric"):
        NTPContext(ntp_source="dc01", ntp_offset_s="not-a-number")


def test_ntpcontext_rejects_nan_or_inf_offset():
    with pytest.raises(ValueError, match="finite"):
        NTPContext(ntp_source="dc01", ntp_offset_s=math.nan)
    with pytest.raises(ValueError, match="finite"):
        NTPContext(ntp_source="dc01", ntp_offset_s=math.inf)


def test_ntpcontext_rejects_invalid_eid():
    with pytest.raises(ValueError, match="35/260"):
        NTPContext(ntp_source="dc01", source_eid=4624)


def test_ntpcontext_rejects_invalid_confidence_rank():
    with pytest.raises(ValueError, match="confidence_rank"):
        NTPContext(ntp_source="dc01", confidence_rank=7)
    with pytest.raises(ValueError, match="confidence_rank"):
        NTPContext(ntp_source="dc01", confidence_rank=0)


def test_ntpcontext_rejects_confirmed_assumption_without_source():
    with pytest.raises(ValueError, match="non-empty"):
        NTPContext(ntp_source="", ntp_assumption=False)
    # Default (assumption=True, source="") is valid — the skip-ntp path.
    NTPContext()


def test_ntpcontext_is_frozen():
    ctx = NTPContext(ntp_source="dc01")
    with pytest.raises(FrozenInstanceError):
        ctx.ntp_source = "evil-dc"


def test_ntpcontext_to_dict_emits_int_rank():
    ctx = NTPContext(ntp_source="dc01", confidence_rank=ConfidenceRank.LOG_DERIVED,
                     ntp_assumption=False, source_eid=260)
    d = ctx.to_dict()
    assert d["confidence_rank"] == 1
    assert type(d["confidence_rank"]) is int
    assert d["ntp_source"] == "dc01"
    assert d["source_eid"] == 260
