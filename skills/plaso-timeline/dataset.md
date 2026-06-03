# Dataset Documentation

## Overview

This file documents the datasets and test fixtures used to develop and validate the Protocol:SIFT plaso-timeline and NTP enrichment skills.

---

## 1. Synthetic Test Fixtures

These fixtures live in `tests/fixtures/` and are checked into the repository. They are used by the pytest suite (P-01 through P-07) and the smoke test harness (P-09).

| File | Rows | Purpose |
|---|---|---|
| `ntp_mini.csv` | 14 | Synthetic l2tcsv export in real EID format derived from case RD01. Contains EID 259, 260, and 37 rows for NTP source auto-detection. Used as the primary happy-path fixture. |
| `ntp_mini_no_eids.csv` | 14 | Same structure as `ntp_mini.csv` but with all NTP-related EID rows removed. Forces the resolver down the analyst-prompt / assumption branch in `resolve_ntp_source()`. |
| `expected_ntp_ground_truth.json` | — | Ground-truth NTP offset and source values for `ntp_mini.csv`. Used by enricher unit tests to assert field correctness. |

### NTP field values in fixtures

The `ntp_mini.csv` fixture captures the following real values from case RD01:

| Field | Value |
|---|---|
| `ntp_source` | `base-dc.shieldbase.lan` |
| `ntp_offset_s` | `-0.0004007` (≈ 400 µs behind NIST) |
| EID source | EID 260 (Windows Time Service) |
| `ntp_assumption` | `false` — confirmed from artifact logs |
| `confidence_rank` | 1 (`ARTIFACT_LOG`) |

Phase offset values present in the fixture: `-0.0004007s`, `-0.0032941s`.

---

## 2. Case RD01 (Demo Case — shieldbase.lan)

The full end-to-end demo (IMPLEMENTATION.md §demo video) and smoke test Scene 2 are based on a sanitised export from case **RD01**.

| Property | Value |
|---|---|
| Case ID | RD01 |
| Domain | shieldbase.lan |
| NTP source (confirmed) | `base-dc.shieldbase.lan` |
| Detection method | EID 260 in Windows Time Service logs |
| Timeline rows | ~847,234 (full psort l2tcsv export) |
| Parser preset used | `win10` |
| Self-correction triggered | Yes — iter0 `rubric_pass=false` (offset threshold); iter1 `rubric_pass=true` after threshold relaxation |

The synthetic fixtures (`ntp_mini.csv`, `ntp_mini_no_eids.csv`) are derived from this case with row count reduced and any case-sensitive values sanitised for safe repository inclusion.

---

## 3. MITRE ATT&CK STIX Bundle

Used by the `attck-correlation` skill for offline technique mapping.

| Property | Value |
|---|---|
| Source | MITRE CTI GitHub — `enterprise-attack.json` |
| Format | STIX 2.1 |
| Install path | `~/.claude/knowledge-bases/attck/enterprise-attack.json` |
| Update cadence | Quarterly via `install.sh --with-attck-bundle` |
| Air-gap support | Yes — vendored at install time; no CDN or live API calls at runtime |

Mini smoke fixture: `analysis-scripts/tests/fixtures/mini_attck_bundle.json` — a small subset of the full bundle used by `smoke_tlcorr.sh` to keep test runs fast and offline.

---

## 4. NTP Assumption Test Cases

The following assumption branches were exercised during development and should be re-validated on any dataset used for legal submission:

| Scenario | `ntp_source` assumed | `ntp_assumption` | Notes |
|---|---|---|---|
| Windows domain-joined, no NTP logs | `Domain Controller` | `true` | Default for on-prem domain hosts |
| Windows standalone, no NTP logs | `time.windows.com` | `true` | Default for standalone Windows |
| AWS Linux/Windows | `169.254.169.123` | `true` | Amazon Time Sync Service |
| Azure Linux/Windows | `time.windows.com` | `true` | Azure default |
| GCP Linux/Windows | `metadata.google.internal` | `true` | Google Cloud NTP |
| Ubuntu on-prem, no NTP logs | `ntp.ubuntu.com` | `true` | |
| RHEL/CentOS on-prem, no NTP logs | `rhel.pool.ntp.org` | `true` | |

Any row with `ntp_assumption=true` must be disclosed in legal or regulatory submissions (SPEC.md §6.4).

---

## 5. Accuracy Report Notes

Per the hackathon submission checklist (SPEC.md §7, item 6), the following failure modes were identified during testing:

- **Implausible offset (>±1000 s):** Triggers self-correction `recheck-offset` action. The `validate_and_correct()` loop recovers in iter1 for most cases; iter ≥ 3 escalates to operator.
- **`ntp_assumption` on assumed sources:** Any assumption branch produces `ntp_assumption=true`. The rubric can be configured (`require_assumption_false=True` in `analysis/ntp_rubric.json`) for cases requiring artifact-confirmed sources only.
- **No NTP logs + unknown host type:** Falls back to `pool.ntp.org` (rank 6, `DISTRO_DEFAULT`). Lowest confidence — flag prominently in evidence package.
- **Spoliation check:** SHA-256 of the source CSV is verified before and after enrichment. Any mismatch halts the run and logs to `forensic_audit.log`.
