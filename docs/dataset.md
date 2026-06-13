# Dataset Documentation

**Protocol SIFT — NTP Enrichment · SANS FindEvil Hackathon**

Documents what the agent was tested against, the source of the data, what it found,
and how to reproduce every result.

---

## 1. What we tested against

### Primary dataset — SRL-2018 (SANS Research Lab)

The agent was developed and validated against the **SANS Research Lab 2018 (SRL-2018)**
disk image and memory dump collection, used as the reference dataset for the SANS
FindEvil Hackathon. The collection models a simulated enterprise compromise across
seven Windows hosts.

| Step | Host | Role | Artifacts |
|---|---|---|---|
| 1 | `base-wkstn-01` | Initial alert host | Disk image (E01, ~17 GB) + memory (ZIP) |
| 2 | `base-rd-01` | Lateral movement pivot | Disk image (E01, ~17 GB) + memory (7z) |
| 3 | `base-dc` | Domain controller (NTP authority) | Disk image (E01, ~12 GB) + memory (7z) |
| 4 | `base-wkstn-05` | DLL hijack host | Disk image (E01, ~14 GB) + memory (7z) |
| 5 | `base-rd-02` | Remote desktop host | Disk image (E01, ~17 GB) + memory (7z) |
| 6 | `base-file` | File server | Disk image (E01, ~16 GB) + memory (7z) |
| 7 | `dmz-ftp` | DMZ / FTP server | Disk image (E01, ~12 GB) |

**Source:** SANS evidence repository (Egnyte). Download script:
`hackasans-correlator/scripts/download_sr018.sh` — fetches individual steps on demand
to the SIFT workstation's `/evidence/srl-2018` directory.

**NTP enrichment focus:** Steps 1 and 2 (`base-wkstn-01`, `base-rd-01`) were the
primary targets for NTP enrichment testing. The domain controller (`base-dc`) is the
NTP authority for the environment — `base-dc.shieldbase.lan` appears as the time
source in Windows Time Service event logs on domain-joined workstations.

---

### Synthetic test fixtures — `protocol-sift/analysis-scripts/tests/fixtures/`

Four deterministic, offline fixtures cover the full range of enrichment scenarios.
All are derived from real SRL-2018 artifact structure; no real evidence files are
committed.

| Fixture | Rows | Covers | Key characteristic |
|---|---|---|---|
| `ntp_mini.csv` | 14 | Happy path | EID 35 and EID 260 NTP artifacts present; unambiguous resolution |
| `ntp_mini_no_eids.csv` | 6 | Known miss (assumption) | No Windows Time Service events; agent must fall back to OS default |
| `ntp_mini_implausible.csv` | 3 | Self-correction halt | Offset ≈ 20,000,000,000 s — far outside ±1000 s bound; triggers exit 3 |
| `ntp_spoliation.csv` | 3 | Evidence integrity | Crafted injection text in `desc`/`notes` columns; must be treated as inert data |

---

## 2. NTP artifacts recovered

### From `base-wkstn-01` (represented by `ntp_mini.csv`)

The Plaso `psort` export of `base-wkstn-01-c-drive.E01` contains Windows Time Service
events in `C:/Windows/System32/winevt/Logs/System.evtx`. The agent recovered:

**EID 35 — Time service sync events** (highest confidence, rank 1):

| Timestamp (UTC) | NTP source | Offset string |
|---|---|---|
| 2018-08-30 02:05:15 | `base-dc.shieldbase.lan` | `0` (initial sync) |
| 2018-08-30 02:06:20 | `base-dc.shieldbase.lan` | `-4007` (raw offset value) |
| 2018-08-30 02:07:41 | `base-dc.shieldbase.lan` | `-32941` (raw offset value) |

**EID 260 — NtpClient periodic configuration events** (rank 1):

| Timestamp (UTC) | Phase Offset |
|---|---|
| 2018-08-30 02:10:01 | `-0.0004007 s` |
| 2018-08-30 02:20:13 | `-0.0032941 s` |

**Resolved NTP source:** `base-dc.shieldbase.lan`
**Resolved clock offset:** `-0.0004007 s` (EID 260 phase offset preferred over EID 35
raw string; see `protocol-sift/analysis-scripts/tests/fixtures/expected_ntp_ground_truth.json`)
**Confidence rank:** 1 (LOG_DERIVED — recovered directly from event log artifacts)
**`ntp_assumption`:** `false` — no assumption required

---

### From `ntp_mini_no_eids.csv` (known miss — assumption case)

When no Windows Time Service events (EID 35/260) are present in the exported timeline,
the resolver cannot recover the NTP source from logs. The agent falls back to:

- **Confidence rank:** 6 (DISTRO_DEFAULT — OS default assumed)
- **Assumed source:** `time.windows.com` (Windows default)
- **`ntp_assumption`:** `true` — flagged explicitly in the accuracy report
- **Impact:** All enriched rows carry the assumption flag; the accuracy report lists
  the basis and surfaces these rows for analyst review before any legal submission

This is the **expected behavior** for a host whose NTP log artifacts were not captured
or were not present in the exported timeline window. It is documented, not silenced.

---

### From `ntp_mini_implausible.csv` (self-correction demo case)

An EID 35 event carries offset `20,000,000,000` — approximately 20 billion seconds,
far outside the ±1000 s plausibility bound.

**Agent response (demonstrated in the demo video):**
1. Resolves NTP source from EID 35 (`base-dc.shieldbase.lan`, rank 1)
2. Computes offset; plausibility check fails (exceeds ±1000 s)
3. Re-resolves and retries — same evidence, same implausible result
4. After 3 iterations: **halts with exit code 3**
5. Emits `unresolved_rows` in the accuracy report with `rejection_basis` citing the
   ±1000 s bound

No enriched output is written for the unresolved rows. Chain of custody is preserved.

---

## 3. What the agent found

### Happy-path enrichment summary (`ntp_mini.csv` baseline)

| Metric | Value |
|---|---|
| Total rows processed | 14 |
| Rows with `ntp_assumption = false` | 14 (all) |
| Rows with `ntp_assumption = true` | 0 |
| Confidence rank | 1 (LOG_DERIVED) |
| NTP source | `base-dc.shieldbase.lan` |
| Resolved offset | `-0.0004007 s` |
| Unresolved rows | 0 |
| Self-correction iterations | 1 (no retry needed) |
| Exit code | 0 (success) |

### Self-correction case summary (`ntp_mini_implausible.csv`)

| Metric | Value |
|---|---|
| Total rows | 3 |
| Unresolved rows | 1 (the EID 35 row with implausible offset) |
| Self-correction iterations | 3 (max) |
| Exit code | 3 (HALT — self-correction exhausted) |
| Rejection basis | "offset magnitude exceeds ±1000 s plausibility bound" |

---

## 4. Reproducibility

**Full SRL-2018 dataset:**
```bash
# On the SIFT workstation — download only what you need
bash hackasans-correlator/scripts/download_sr018.sh step1   # wkstn-01 (~17 GB)
bash hackasans-correlator/scripts/download_sr018.sh step2   # rd-01 (~17 GB)
```

**Synthetic fixtures (offline, no download required):**
```bash
# From the protocol-sift repo root
cd analysis-scripts
python3 -m pytest tests/ -v                                 # 69/69 green
bash tests/smoke_ntp_agent.sh                               # 3/3 scenes
```

**Demo case (deterministic, offline, one command):**
```bash
# From the hackasans-correlator repo root
bash scripts/stage_self_correct_case.sh
# Stages /tmp/ntp_demo/DEMO-NTP-2026-001/ with the implausible fixture.
# Open Claude Code there and paste the Shot 3 prompt from
# hackasans-correlator/docs/demo/ntp-enrichment-self-correction.md
```

All fixtures are committed at `protocol-sift/analysis-scripts/tests/fixtures/`.
No network access, API keys, or NIST connectivity required for any test or demo run.
