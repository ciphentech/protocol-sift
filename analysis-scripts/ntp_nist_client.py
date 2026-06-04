"""NIST time reference query for Protocol SIFT.

FEATURE 3 — NIST Time Reference Query (SPEC §3)

Queries a public NIST/NTP time server over the NTP protocol (UDP/123) to validate the
assumed NTP source and derive a live clock offset. Anonymous — no API key, registration,
or credential. Tries the regional NIST servers first, then global NIST/anycast, then the
NTP pool. If every server is unreachable it raises ``NistUnreachable`` so the caller can
halt before any timestamp computation (SPEC §3.2).

Security: server hostnames are checked against an explicit *allowlist* (allowlists over
blocklists) before any network call, so a crafted ``--nist-server`` value cannot redirect
the query to an attacker-controlled host. Network failures fail closed (raise, never
silently continue). No shell, eval, or deserialization of untrusted data. The unencrypted
NTP transport is a documented proof-of-concept limitation (SPEC §6.6).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Sequence

import ntplib

# Regional → global → pool (SPEC §3.1).
DEFAULT_SERVERS = (
    "time-a-wwv.nist.gov",
    "time-b-wwv.nist.gov",
    "time.nist.gov",
    "pool.ntp.org",
)
DEFAULT_TIMEOUT_S = 3.0
DEFAULT_RETRIES = 2

# Allowlist of acceptable time-server hostname suffixes. Anything else is rejected.
_ALLOWED_HOST_SUFFIXES = (
    ".nist.gov",
    "time.nist.gov",
    "pool.ntp.org",
    ".pool.ntp.org",
    "time.windows.com",
    "ntp.ubuntu.com",
)


class NistUnreachable(Exception):
    """Raised when no configured time server can be reached (SPEC §3.2)."""


@dataclass(frozen=True, slots=True)
class NistResponse:
    """A successful time-server response."""

    offset_s: float
    delay_s: float
    queried_at_utc: str
    stratum: int
    server_used: str


def validate_server_hostname(host: str) -> str:
    """Return ``host`` if it is on the allowlist, else raise ValueError.

    Validation happens before any socket is opened (fail closed). Allowlist match is
    case-insensitive on a trusted suffix set.
    """
    if not isinstance(host, str) or not host.strip():
        raise ValueError("NIST server hostname must be a non-empty string")
    h = host.strip().lower()
    for suffix in _ALLOWED_HOST_SUFFIXES:
        if h == suffix or h.endswith(suffix):
            return host.strip()
    raise ValueError(
        f"NIST server {host!r} is not on the allowlist "
        f"({', '.join(_ALLOWED_HOST_SUFFIXES)})"
    )


def query(
    servers: Sequence[str] = DEFAULT_SERVERS,
    timeout_s: float = DEFAULT_TIMEOUT_S,
    retries: int = DEFAULT_RETRIES,
    client: ntplib.NTPClient | None = None,
) -> NistResponse:
    """Query the first reachable time server and return its NistResponse.

    Tries each server in order (regional → global → pool). Every hostname is validated
    against the allowlist first. Raises ``NistUnreachable`` if all servers fail.
    """
    if not servers:
        raise ValueError("at least one NIST server must be configured")

    client = client or ntplib.NTPClient()
    last_error: Exception | None = None

    for server in servers:
        host = validate_server_hostname(server)
        for _attempt in range(max(1, retries)):
            try:
                resp = client.request(host, version=3, timeout=timeout_s)
            except Exception as exc:  # ntplib raises NTPException / socket errors
                last_error = exc
                continue
            return NistResponse(
                offset_s=float(resp.offset),
                delay_s=float(resp.delay),
                queried_at_utc=datetime.now(timezone.utc).isoformat(),
                stratum=int(resp.stratum),
                server_used=host,
            )

    raise NistUnreachable(
        "No NIST/NTP time server could be reached "
        f"({', '.join(servers)}); last error: {last_error!r}. "
        "Verify outbound UDP/123 connectivity from the SIFT workstation."
    )
