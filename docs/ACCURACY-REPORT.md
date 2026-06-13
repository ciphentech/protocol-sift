# Accuracy Report — NTP Enrichment Submission

**Protocol SIFT — NTP Enrichment · SANS FindEvil Hackathon**
**Self-assessment of findings accuracy and evidence integrity**

Per hackathon requirement 6: false positives, missed artifacts, hallucinated claims,
evidence integrity approach, and spoliation testing. Finding and documenting failure
modes is a submission strength, not a weakness.

---

## 1. Findings accuracy — test suite baseline

The submission is validated by a three-layer test suite, all offline (no NIST
connectivity required):

| Layer | Command | Result |
|---|---|---|
| Unit tests | `cd protocol-sift/analysis-scripts && python3 -m pytest tests/ -v` | **69/69 green** |
| Smoke (end-to-end CLI) | `bash protocol-sift/analysis-scripts/tests/smoke_ntp_agent.sh` | **3/3 scenes pass** |
| Deploy verifier | `bash protocol-sift/analysis-scripts/tests/verify_cloned_repos.sh` | **5/5 checks pass** |

The 69 unit tests cover: EID 35/260 extraction, NTP source resolution tree (6 levels),
NIST client (regional → fallback → halt), enricher field math, self-correction loop
(plausibility bounds, retry, halt), manifest report schema, CLI flags, and spoliation.

The 3 smoke scenes cover: happy path (EID-resolved source, NIST-anchored output),
self-correction halt (exit 3, unresolved rows), and integrity check (SHA-256 unchanged).

---

## 2. False positives observed

**EID resolution:** No false positive NTP source assignments were observed when EID 35
or EID 260 events are present. The extractor matches only on specific event ID strings
and extracts the NTP server hostname from a fixed field position — there is no
free-text inference that could assign a wrong server.

**Offset plausibility:** The ±1000 s plausibility bound is conservative. No cases were
observed where a legitimate offset was rejected as implausible during testing against
SRL-2018 artifacts. The bound was validated against the fixture set and matches the
practical range of Windows domain clock skew.

**`ntp_assumption = true` is not a false positive** — it is the intended signal when
artifact evidence is absent. Every row flagged as an assumption is correctly flagged;
no rows were wrongly marked as assumptions when artifact evidence was available.

---

## 3. Missed artifacts

### Known miss: Linux NTP sources not implemented

The current implementation recovers NTP sources only from Windows artifacts:
- EID 35 (Windows Time Service sync event)
- EID 260 (NtpClient periodic configuration)
- `w32tm /query /status` output

Linux NTP log sources are **not yet implemented:**
- `chronyc tracking` output
- `syslog` NTP daemon entries (`ntpd`, `chronyd`)

On a timeline exported from a Linux host with no Windows Time Service events, the
resolver falls back to rank 6 (DISTRO_DEFAULT, OS default assumed). The result is
correct behavior — not a silent miss — because the assumption is surfaced explicitly
via `ntp_assumption = true` and documented in the accuracy report. But it means the
recovered offset is estimated, not artifact-derived, for Linux hosts.

**Scope note:** The SRL-2018 dataset is Windows-centric; all tested hosts are
domain-joined Windows workstations synchronized to `base-dc.shieldbase.lan`. Linux
source recovery is documented as a future improvement (SPEC §6.6).

### Known miss: NTP events outside the Plaso export window

If the Plaso export does not include the time window when Windows Time Service events
were written (e.g., because the export was date-filtered), EID 35/260 events may be
absent even if they exist on disk. The resolver treats this identically to the
no-EIDs case: rank 6, `ntp_assumption = true`. Analysts should ensure the export
covers the full timeline, especially the system boot and early post-boot window.

---

## 4. Hallucinated claims

The architecture prevents hallucination at two levels:

**`ntp_assumption = true` — the primary guard.** When the agent cannot recover the NTP
source from log artifacts, it does not invent one. It records the assumed value, the
confidence rank (6 = DISTRO_DEFAULT), the basis, and sets `ntp_assumption = true` on
every affected row. The accuracy report surfaces all assumption rows for analyst review.
The agent never presents an assumed offset as a confirmed artifact finding.

**Self-correction loop — the secondary guard.** After computing offsets, the enricher
validates every result against the ±1000 s plausibility bound. An offset outside that
bound triggers re-resolution and retry (up to 3 iterations). If no plausible result is
found, the loop halts with exit code 3 and lists the unresolved rows with their
`rejection_basis`. The agent never accepts and writes an implausible offset — it
escalates instead.

No hallucinated NTP server names, invented offsets, or fabricated event timestamps were
observed in any test run. The structured accuracy report (JSON) makes every claim
traceable to its source.

---

## 5. Evidence integrity approach

Two enforcement layers protect source evidence. Architectural controls are primary and
enforced unconditionally; prompt-based controls are secondary.

### Architectural controls (primary — enforced unconditionally)

| Control | Enforcement mechanism |
|---|---|
| Source files read-only | EBS data volume mounted read-only to the enrichment process; OS-level protection |
| Output never overwrites source | Enriched CSV written to `exports/<case>_correlated.csv`; source at `exports/<case>_timeline.csv` — distinct filenames; no overwrite possible |
| Evidence path writes refused | `ntp_enricher.py` raises `ValueError("protected evidence")` on any attempt to write to `/cases/` or `/mnt/` paths |
| SHA-256 integrity check | Enricher re-hashes the source CSV after processing and aborts if the hash changed; result in the accuracy report |
| Analysis reports isolated | All reports and audit logs written to `analysis/` — never to `exports/` |
| CloudWatch logging | All session activity logged to `/ec2/hackasans-prod/sift` (90-day retention) |
| EBS encrypted at rest | `encrypted = true` on all volumes |

### Prompt-based controls (secondary — instructed, not enforced)

The agent (`SKILL.md`) is instructed not to write to source paths and to treat all
evidence as read-only. This is a secondary layer. If the model ignored this instruction,
the architectural controls above would still refuse the write and raise an exception
that is logged and surfaced to the analyst.

The security boundary table in `hackasans-correlator/docs/SPEC.md §5` distinguishes
all controls by type (Architectural / Prompt-based).

---

## 6. Spoliation testing

**Test file:** `protocol-sift/analysis-scripts/tests/test_spoliation.py`

**Test input:** `protocol-sift/analysis-scripts/tests/fixtures/ntp_spoliation.csv` —
a Plaso timeline CSV with crafted prompt-injection text in the `desc` and `notes`
columns. The injected text instructs the tool to write output into `/cases/evidence/`
and to overwrite the source file in place.

### Test 1 — `test_crafted_csv_cannot_redirect_output_into_evidence`

**What it proves:** Injection text in data fields cannot redirect enricher output.

- Output lands exactly at the requested `--output` path, and nowhere else
- No additional CSV files are created anywhere under the working directory
- The injection text survives verbatim in the output as inert data (it was never
  interpreted as a command)
- When the test explicitly calls `enrich()` with a `/cases/evidence/` target path,
  `ValueError("protected evidence")` is raised — the architectural guard fires

**Result:** PASS

### Test 2 — `test_crafted_csv_does_not_modify_source`

**What it proves:** Processing a malicious payload CSV does not modify the source file.

- SHA-256 hash of `ntp_spoliation.csv` computed before and after a full enrichment run
- Both hashes are identical — the source file is byte-for-byte unchanged
- Exit code is 0 (enrichment succeeded on the non-injection rows)

**Result:** PASS

### Running the spoliation tests

```bash
cd protocol-sift/analysis-scripts
python3 -m pytest tests/test_spoliation.py -v
```

Expected output:
```
tests/test_spoliation.py::test_crafted_csv_cannot_redirect_output_into_evidence PASSED
tests/test_spoliation.py::test_crafted_csv_does_not_modify_source PASSED
2 passed in <1s
```

---

## 7. Known limitations and caveats

Drawn from `hackasans-correlator/docs/SPEC.md §6`. Reproduced here so judges have the
full picture in one document.

**§6.1 — NTP source assumed when no artifacts present.** When no Windows Time Service
events appear in the Plaso export, the agent assumes the OS default NTP server
(`time.windows.com` for Windows, `pool.ntp.org` for Linux). The assumption is flagged
via `ntp_assumption = true` on every affected row and surfaced in the accuracy report.
It is not silent.

**§6.2 — Historical NTP drift not directly observable.** The `ntp_offset_s` field is
an estimate derived from recovered artifacts. Actual clock skew at the moment of each
event may differ. The agent flags uncertainty where applicable.

**§6.3 — Variable clock drift over time.** A workstation that was well-synchronized at
boot may drift significantly over days or weeks (suspension, hibernation, hardware RTC
drift). `nist_time` is a best estimate, not a certified timestamp.

**§6.4 — ISC2 admissibility requirement.** Per ISC2 guidance, time source differences
between log sources must be documented and submitted alongside evidence. This submission
satisfies that requirement: `ntp_source`, `ntp_offset_s`, `ntp_assumption`, and
`nist_delta_s` are recorded per row, and the accuracy report is the persistent
disclosure document the analyst attaches to the evidence package.

**§6.5 — NIST transmission delay.** NIST time is subject to network transmission delay
(<1 ms typical). For sub-millisecond precision requirements, this approach is
insufficient.

**§6.6 — Unencrypted NTP transport (proof-of-concept limitation).** This submission
queries public NTP servers over unencrypted UDP/123. The response is unauthenticated
and could theoretically be tampered with in transit. **This is not acceptable for
production forensic use or legal submissions.** Production deployments require an
authenticated time transport (NTS — RFC 8915, or an internal Stratum-1 appliance).
This limitation is known, documented, and accepted for a hackathon proof of concept.
