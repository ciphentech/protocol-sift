"""Unit tests for the NIST time query (FEATURE 3, SPEC §3) — mocked, no network."""

import pytest

from ntp_nist_client import (
    NistUnreachable,
    query,
    validate_server_hostname,
)


class _Resp:
    def __init__(self, offset=0.012, delay=0.003, stratum=1):
        self.offset = offset
        self.delay = delay
        self.stratum = stratum


class _FakeClient:
    """Fake ntplib client: succeeds for hosts in `ok`, raises otherwise."""

    def __init__(self, ok):
        self.ok = set(ok)
        self.calls = []

    def request(self, host, version=3, timeout=3.0):
        self.calls.append(host)
        if host in self.ok:
            return _Resp()
        raise OSError("simulated timeout")


def test_query_returns_regional_on_success():
    client = _FakeClient(ok=["time-a-wwv.nist.gov"])
    resp = query(client=client)
    assert resp.server_used == "time-a-wwv.nist.gov"
    assert resp.stratum == 1
    assert client.calls[0] == "time-a-wwv.nist.gov"


def test_query_falls_back_on_timeout():
    # Regional fails, global anycast succeeds.
    client = _FakeClient(ok=["time.nist.gov"])
    resp = query(client=client, retries=1)
    assert resp.server_used == "time.nist.gov"
    assert "time-a-wwv.nist.gov" in client.calls  # regional was tried first


def test_query_raises_when_all_unreachable():
    client = _FakeClient(ok=[])
    with pytest.raises(NistUnreachable):
        query(client=client, retries=1)


def test_nist_unreachable_message_mentions_udp123():
    client = _FakeClient(ok=[])
    with pytest.raises(NistUnreachable, match="UDP/123"):
        query(client=client, retries=1)


def test_validate_server_hostname_accepts_allowlisted():
    assert validate_server_hostname("time.nist.gov") == "time.nist.gov"
    assert validate_server_hostname("pool.ntp.org") == "pool.ntp.org"


def test_validate_server_hostname_rejects_unknown():
    with pytest.raises(ValueError, match="allowlist"):
        validate_server_hostname("evil.attacker.example.com")
