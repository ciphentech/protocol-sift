"""NTP source resolution and time-evidence recovery for Protocol SIFT.

FEATURE 2 — Artifact-Based Time Evidence Recovery (SPEC §4 Phase 2 Detail)
FEATURE 4 — NTP Source Resolution (SPEC §4 Phase 2 Detail)

This module is a flat analysis-script (no package). Sibling scripts import it by
bare name: ``from ntp_resolver import NTPContext, resolve_ntp_source``. It holds the
single shared data model (``NTPContext`` / ``ConfidenceRank``), the EID 35/260 string
extractors, and the Phase-2 resolution decision tree.

Security: validates all extracted values (numeric/finite offsets, EID allow-set
{35, 260}, confidence-rank range 1–6) and *rejects* bad input rather than coercing it;
no shell, eval, or deserialization of untrusted data; reads are pure-Python regex over
strings already parsed by Plaso. Runs read-only in a sandboxed forensic workstation.
"""

from __future__ import annotations

import math
import re
from dataclasses import asdict, dataclass
from enum import IntEnum
from typing import Optional


class ConfidenceRank(IntEnum):
    """Confidence ranks for NTP source resolution (SPEC §4 Phase 2 Detail)."""

    LOG_DERIVED = 1         # EID 35/260, chronyc, w32tm recovered from the artifact
    ANALYST_CONFIRMED = 2   # --ntp-source provided AND consistent with logs
    ANALYST_UNVERIFIED = 3  # --ntp-source provided, no logs to cross-check
    CLOUD_DEFAULT = 4       # AWS/Azure environment default
    DOMAIN_DEFAULT = 5      # on-prem Windows domain/standalone assumption
    DISTRO_DEFAULT = 6      # Linux distro / unknown fallback


@dataclass(frozen=True, slots=True)
class NTPContext:
    """The single resolved NTP context for a case (SPEC §2.2 / §4).

    Exactly five fields. ``ntp_offset_s`` (never ``estimated_offset_s``) is the local
    clock offset from the NTP peer in seconds: positive means the source clock was
    ahead of NIST, negative means behind.
    """

    ntp_source: str = ""
    ntp_offset_s: float = 0.0
    ntp_assumption: bool = True
    confidence_rank: int = 6  # int in [1, 6] or ConfidenceRank
    source_eid: Optional[int] = None

    def __post_init__(self) -> None:
        # Declarative hints are not enforced at runtime — validate explicitly and
        # reject invalid input (fail closed) rather than trying to "fix" it.
        # bool is excluded because isinstance(True, int) is True in Python.
        if isinstance(self.ntp_offset_s, bool) or not isinstance(
            self.ntp_offset_s, (int, float)
        ):
            raise TypeError(
                f"ntp_offset_s must be numeric, got {type(self.ntp_offset_s).__name__}"
            )
        # NaN/inf are not meaningful clock offsets. The plausibility bound (±1000 s)
        # lives in ntp_enricher.validate_context() so the self-correction loop can
        # recover from implausible offsets rather than crash at construction.
        if math.isnan(self.ntp_offset_s) or math.isinf(self.ntp_offset_s):
            raise ValueError(f"ntp_offset_s must be finite, got {self.ntp_offset_s}")
        if not (1 <= int(self.confidence_rank) <= 6):
            raise ValueError(
                f"confidence_rank must be 1 through 6, got {self.confidence_rank}"
            )
        # Only EID 35 and EID 260 are in scope per SPEC §2.2 / §4 Phase 2.
        if self.source_eid is not None and self.source_eid not in (35, 260):
            raise ValueError(
                f"source_eid must be one of 35/260 or None, got {self.source_eid}"
            )
        # ntp_assumption=False represents a *known* source — it cannot be blank.
        if self.ntp_assumption is False and not self.ntp_source:
            raise ValueError("ntp_assumption=False requires a non-empty ntp_source")

    def to_dict(self) -> dict:
        """Serialize for manifest JSON. confidence_rank coerced to plain int."""
        d = asdict(self)
        d["confidence_rank"] = int(self.confidence_rank)
        return d


# --- EID extraction helpers (all return None on no match) -------------------

# Matches "[260 / 0x0104]" or "[35 / 0x0023]" in the short/desc columns.
EID_PATTERN = re.compile(r"\[(\d+)\s*/\s*0x")

# EID 35 strings array: strings[0] = NTP peer hostname,
# strings[1] = phase offset in 100-ns units (÷10,000,000 → seconds). See SPEC §2.2.
EID35_STRINGS_PATTERN = re.compile(
    r"Strings:\s*\[\s*'([a-zA-Z0-9._-]+)'\s*,\s*'(-?\d+)'\s*\]"
)

# EID 260 periodic config: "Phase Offset: -0.0004007s".
PHASE_OFFSET_PATTERN = re.compile(r"Phase Offset:\s*([+-]?\d+\.\d+)s")


def extract_eid_number(row: dict) -> Optional[int]:
    """Return the Windows Event ID from the short or desc column, or None."""
    for col in ("short", "desc"):
        m = EID_PATTERN.search(str(row.get(col, "")))
        if m:
            return int(m.group(1))
    return None


def extract_ntp_source_hostname(desc: str) -> Optional[str]:
    """Extract the NTP peer hostname from an EID 35 Strings field (strings[0])."""
    m = EID35_STRINGS_PATTERN.search(desc)
    return m.group(1).strip() if m else None


def extract_eid35_offset_s(desc: str) -> Optional[float]:
    """Extract ntp_offset_s from EID 35 strings[1] per SPEC §2.2: 100-ns units / 1e7."""
    m = EID35_STRINGS_PATTERN.search(desc)
    return int(m.group(2)) / 10_000_000.0 if m else None


def extract_phase_offset_s(desc: str) -> Optional[float]:
    """Extract PhaseOffset seconds from an EID 260 desc; strips trailing 's'."""
    m = PHASE_OFFSET_PATTERN.search(desc)
    return float(m.group(1)) if m else None


# --- Phase 2 resolution -----------------------------------------------------

_LINUX_DISTRO_DEFAULTS = {
    "ubuntu": "ntp.ubuntu.com",
    "rhel": "rhel.pool.ntp.org",
    "centos": "rhel.pool.ntp.org",
    "debian": "debian.pool.ntp.org",
}


def _scan_artifact_for_ntp(df) -> tuple[Optional[str], Optional[float], Optional[int]]:
    """Recover (ntp_source, ntp_offset_s, source_eid) from in-scope NTP records.

    The peer hostname comes from EID 35 (strings[0]); the offset prefers an EID 260
    Phase Offset (the periodic, more precise value) and falls back to the EID 35
    offset. Returns (None, None, None) when no EID 35/260 records are present.
    """
    source: Optional[str] = None
    source_eid: Optional[int] = None
    eid35_offset: Optional[float] = None
    eid260_offset: Optional[float] = None

    for _, row in df.iterrows():
        eid = extract_eid_number(row)
        desc = str(row.get("desc", ""))
        if eid == 35 and source is None:
            host = extract_ntp_source_hostname(desc)
            if host:
                source = host
                source_eid = 35
                eid35_offset = extract_eid35_offset_s(desc)
        elif eid == 260 and eid260_offset is None:
            eid260_offset = extract_phase_offset_s(desc)

    if source is None and eid260_offset is None and eid35_offset is None:
        return None, None, None

    offset = eid260_offset if eid260_offset is not None else eid35_offset
    return source, offset, source_eid


def resolve_ntp_source(
    df,
    cli_ntp_source: Optional[str] = None,
    skip_ntp: bool = False,
    interactive: bool = False,
    hosting: str = "unknown",
    host_os: str = "unknown",
    linux_distro: str = "unknown",
    windows_domain_joined: bool = False,
    prompt_fn=input,
) -> NTPContext:
    """Full SPEC §4 Phase 2 Detail decision tree.

    Resolution priority (highest confidence first):
      1. LOG_DERIVED        — EID 35/260 recovered from the artifact
      2. ANALYST_CONFIRMED  — --ntp-source provided AND consistent with logs
      3. ANALYST_UNVERIFIED — --ntp-source provided, no logs to cross-check
      4. CLOUD_DEFAULT      — hosting in {aws, azure}
      5. DOMAIN_DEFAULT     — on-prem Windows (domain or standalone)
      6. DISTRO_DEFAULT     — on-prem Linux distro / unknown pool fallback

    --skip-ntp is handled by the caller (CLI) per SPEC §4 CLI Flags; when skip_ntp
    is True this returns a null context so the caller can skip enrichment after
    emitting the chain-of-custody warning.
    """
    if skip_ntp:
        return NTPContext(
            ntp_source="",
            ntp_assumption=True,
            confidence_rank=ConfidenceRank.DISTRO_DEFAULT,
        )

    artifact_source, artifact_offset, artifact_eid = _scan_artifact_for_ntp(df)
    has_artifact = artifact_source is not None

    # Priority 2 / 3: analyst-provided source, cross-checked against the artifact.
    if cli_ntp_source:
        if not has_artifact:
            return NTPContext(
                ntp_source=cli_ntp_source,
                ntp_offset_s=0.0,
                ntp_assumption=False,
                confidence_rank=ConfidenceRank.ANALYST_UNVERIFIED,
            )
        if artifact_source.lower() == cli_ntp_source.lower():
            return NTPContext(
                ntp_source=cli_ntp_source,
                ntp_offset_s=artifact_offset or 0.0,
                ntp_assumption=False,
                confidence_rank=ConfidenceRank.ANALYST_CONFIRMED,
                source_eid=artifact_eid,
            )
        # Stated source disagrees with the artifact — trust the artifact (higher
        # confidence) and surface the discrepancy via the manifest / Phase 3.
        return NTPContext(
            ntp_source=artifact_source,
            ntp_offset_s=artifact_offset or 0.0,
            ntp_assumption=False,
            confidence_rank=ConfidenceRank.LOG_DERIVED,
            source_eid=artifact_eid,
        )

    # Priority 1: artifact alone.
    if has_artifact:
        return NTPContext(
            ntp_source=artifact_source,
            ntp_offset_s=artifact_offset or 0.0,
            ntp_assumption=False,
            confidence_rank=ConfidenceRank.LOG_DERIVED,
            source_eid=artifact_eid,
        )

    # Priority 3: interactive prompt fallback (no flag, no logs).
    # FEATURES: "one or two short prompts — never more". Prompt 1 asks for the
    # source; if declined, prompt 2 narrows the environment so the assumption
    # fallback below picks the right default. Never a third prompt.
    if interactive:
        answer = prompt_fn(
            "[ntp-enrichment] Do you know the NTP source for this host? "
            "(hostname/IP, Enter to skip): "
        ).strip()
        if answer:
            return NTPContext(
                ntp_source=answer,
                ntp_offset_s=0.0,
                ntp_assumption=False,
                confidence_rank=ConfidenceRank.ANALYST_UNVERIFIED,
            )
        if hosting == "unknown":
            env = prompt_fn(
                "[ntp-enrichment] Was the system cloud-hosted or on-prem? "
                "(aws/azure/on_prem, Enter to skip): "
            ).strip().lower()
            if env in ("aws", "azure"):
                hosting = env

    # Priority 4: cloud provider defaults.
    if hosting == "aws":
        return NTPContext(
            ntp_source="169.254.169.123",
            ntp_assumption=True,
            confidence_rank=ConfidenceRank.CLOUD_DEFAULT,
        )
    if hosting == "azure":
        return NTPContext(
            ntp_source="time.windows.com",
            ntp_assumption=True,
            confidence_rank=ConfidenceRank.CLOUD_DEFAULT,
        )

    # Priority 5: on-prem Windows.
    if host_os == "windows":
        source = "Domain Controller" if windows_domain_joined else "time.windows.com"
        return NTPContext(
            ntp_source=source,
            ntp_assumption=True,
            confidence_rank=ConfidenceRank.DOMAIN_DEFAULT,
        )

    # Priority 6: on-prem Linux distro defaults / unknown pool fallback.
    pool = _LINUX_DISTRO_DEFAULTS.get(linux_distro.lower(), "pool.ntp.org")
    return NTPContext(
        ntp_source=pool,
        ntp_assumption=True,
        confidence_rank=ConfidenceRank.DISTRO_DEFAULT,
    )
