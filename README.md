# Protocol SIFT

Rob Lee developed Protocol SIFT and all the files found within this repository.

## Claude Code + SANS SIFT Workstation Setup

> [!IMPORTANT]
> Replication Guide for SANS SIFT + Unconfigured Claude Code

This repository contains everything needed to replicate the DFIR-tuned Claude Code
configuration on a bare SANS SIFT Ubuntu workstation. It covers global behavioral
rules, forensic tool skill files, per-case project templates, and PDF report tooling.

---

## Prerequisites

| Requirement | Notes |
|-------------|-------|
| SANS SIFT Workstation | Ubuntu x86-64 (22.04+), standard SIFT tool set installed |
| Claude Code CLI | `npm install -g @anthropic-ai/claude-code` (or via your org's approved channel) |
| Anthropic API key | Set in `~/.claude/.credentials.json` after first `claude` run — **never copy** this file |
| Python 3.10+ | Built into the SIFT image; verify with `python3 --version` |
| Python dependencies | `pip3 install -r requirements.txt` — installs `pytest`, `pandas`, `ntplib` for NTP enrichment |
| WeasyPrint | `pip3 install weasyprint` — required for PDF report generation only |
| NIST API key | **Optional**, but omitting it means the enrichment falls back to standard NTP rather than the secured sNTP variant. This is discouraged — NTP is an insecure protocol and should only be used in non-production environments. Obtain a key at [nvd.nist.gov/developers/api-key-requested](https://nvd.nist.gov/developers/api-key-requested). See [NIST API Key](#nist-api-key) below for secure setup. |
| dotnet runtime v6 | Pre-installed on SIFT; EZ Tools run against `/opt/zimmermantools/` |

---

## Installation

Choose one of three methods. All three end up with the same files in `~/.claude/`.

---

### Method 1 — curl one-liner (recommended)

Requires `git` on the target machine (standard on SIFT).

```bash
curl -fsSL https://raw.githubusercontent.com/teamdfir/protocol-sift/main/install.sh | bash
```

The script will:
- Clone this repo into a temporary directory (cleaned up on exit)
- Back up any existing `~/.claude/{CLAUDE.md,settings.json,settings.local.json}` to `.bak-<timestamp>` before overwriting
- Install global config, all skills, the case template, analysis scripts (including NTP enrichment tools), and Python dependencies into `~/.claude/`
- Print WeasyPrint install instructions (WeasyPrint prompt is skipped when stdin is piped)

To also install WeasyPrint in the same step, run the script directly instead:

```bash
curl -fsSL https://raw.githubusercontent.com/teamdfir/protocol-sift/main/install.sh -o /tmp/install.sh
bash /tmp/install.sh
```

---

### Method 2 — Clone the repo

```bash
git clone --depth=1 https://github.com/teamdfir/protocol-sift.git
cd protocol-sift
bash install.sh
```

Keep the cloned directory around if you want to pull updates later (`git pull && bash install.sh`).

---

### Method 3 — Download as ZIP archive

1. Go to `https://github.com/teamdfir/protocol-sift` → **Code → Download ZIP**
2. Extract the archive:
   ```bash
   unzip protocol-sift-main.zip
   cd protocol-sift-main
   ```
3. Either run the bundled script:
   ```bash
   bash install.sh
   ```
   Or follow the manual file-by-file steps in the [File-by-File Installation Instructions](#file-by-file-installation-instructions) section below.

---

## Repository Structure

```
protocol-sift/
├── README.md                          ← this file
├── install.sh                         ← automated installer
├── requirements.txt                   ← Python dependencies (pytest, pandas, ntplib, boto3)
├── global/
│   ├── CLAUDE.md                      ← global behavioral instructions (1)
│   ├── settings.json                  ← tool permissions + Stop hook    (2)
│   └── settings.local.json            ← local sudo / apt overrides      (3)
├── skills/
│   ├── memory-analysis/SKILL.md       ← Volatility 3 skill              (4)
│   ├── plaso-timeline/SKILL.md        ← Plaso / log2timeline skill      (5)
│   ├── ntp-enrichment/SKILL.md        ← NTP time enrichment skill       (6)
│   ├── sleuthkit/SKILL.md             ← Sleuth Kit / TSK skill          (7)
│   ├── windows-artifacts/SKILL.md     ← EZ Tools / EVTX / Registry      (8)
│   └── yara-hunting/SKILL.md          ← YARA / threat hunting skill     (9)
├── case-templates/
│   └── CLAUDE.md                      ← per-case project template       (10)
└── analysis-scripts/
    ├── generate_pdf_report.py         ← WeasyPrint PDF generator        (11)
    ├── ntp_resolver.py                ← NTP source resolution tool      (12)
    ├── ntp_enricher.py                ← NTP field computation + writer  (13)
    ├── ntp_manifest.py                ← manifest JSON writer + rubric   (14)
    ├── ntp_nist_client.py             ← NIST time service client        (15)
    ├── sift_logger.py                 ← skill-level forensic audit log  (16)
    └── sift_s3_sync.py                ← cron-driven S3 log sync script  (17)
```

---

## File-by-File Installation Instructions

### (1) global/CLAUDE.md → `~/.claude/CLAUDE.md`

**What it is:** The global system prompt that loads for every Claude Code session,
regardless of working directory. Sets the operator role (Principal DFIR Orchestrator),
evidence integrity rules, tool routing table, installed tool paths, and the no-questions
autonomous operation preference.

**Install:**
```bash
cp global/CLAUDE.md ~/.claude/CLAUDE.md
```

**Customise:**
- Update the `Installed Tool Paths` table if your SIFT instance has tools in different locations.
- If you use MemProcFS or VSCMount (Windows VMs only), add them to the table.
- The `## Operator Preferences` section sets fully autonomous mode — adjust if you prefer confirmations.

---

### (2) global/settings.json → `~/.claude/settings.json`

**What it is:** The main Claude Code permission policy. Pre-approves all DFIR CLI tools
(Volatility, Sleuth Kit, EZ Tools, Plaso, bulk_extractor, YARA, hash tools, etc.) so
Claude never pauses to ask permission mid-investigation. Also contains a `Stop` hook
that writes a forensic audit log entry to `./analysis/forensic_audit.log` at the end
of every conversation.

**Install:**
```bash
cp global/settings.json ~/.claude/settings.json
```

**Key sections:**
- `permissions.allow` — all forensic CLIs are pre-approved
- `permissions.deny` — blocks `rm -rf`, `dd`, `wget`, `curl`, `ssh`, and `WebFetch`
  (prevents Claude from exfiltrating data or wiping evidence)
- `permissions.defaultMode` — `"acceptEdits"` means file edits in allowed paths
  auto-approve without a prompt
- `hooks.Stop` — appends conversation summary to `./analysis/forensic_audit.log`
  for chain-of-custody documentation

**Important — Write path restrictions:**
The `Write` and `Edit` allow-list is scoped to `./analysis/*`, `./reports/*`, and
`./exports/*` (relative to whichever case directory you `cd` into before launching
`claude`). This is intentional — it prevents writing to evidence directories. Do **not**
broaden this to `/cases/**` or `/mnt/**`.

---

### (3) global/settings.local.json → `~/.claude/settings.local.json`

**What it is:** Machine-local overrides. Currently allows `sudo apt` installs and the
`psort.py` Plaso command. This file is intentionally minimal — it holds only things
that differ per-machine, not per-case.

**Install:**
```bash
cp global/settings.local.json ~/.claude/settings.local.json
```

---

### (4–9) skills/ → `~/.claude/skills/`

**What they are:** Skill files are domain-specific prompt libraries that Claude loads
on demand. Each `SKILL.md` contains exact CLI invocations, common flags, known
gotchas, and output interpretation guidance for a specific forensic toolset.

| Skill file | Domain | Key tools covered |
|------------|--------|-------------------|
| `memory-analysis/SKILL.md` | Memory forensics | Volatility 3 plugins, symbol resolution, memory baseliner |
| `plaso-timeline/SKILL.md` | Timeline generation | log2timeline.py, psort.py, pinfo.py, super-timeline filters |
| `ntp-enrichment/SKILL.md` | NTP time enrichment | ntp_resolver.py, ntp_enricher.py, ntp_manifest.py, ntp_nist_client.py — NIST-anchored timestamp normalization |
| `sleuthkit/SKILL.md` | Filesystem forensics | fls, icat, mmls, mactime, tsk_recover, ewfmount offsets |
| `windows-artifacts/SKILL.md` | Windows artifacts | EZ Tools suite, EvtxECmd, MFTECmd, RECmd, AmcacheParser |
| `yara-hunting/SKILL.md` | Threat hunting | YARA rules, IOC sweeps, bulk scanning |

**How Claude uses them:** The global `CLAUDE.md` contains a routing table that
tells Claude which skill file to consult before using each tool category. Claude
reads the skill file at task time — you do not need to invoke them manually.

---

### (9) case-templates/ → `/cases/<casename>/CLAUDE.md`

**What it is:** A per-case project CLAUDE.md. When you `cd /cases/<casename>` and
launch `claude`, this file is loaded automatically as project-level instructions,
layered on top of the global `~/.claude/CLAUDE.md`.

**Install for a new case:**

If you used the installer (`install.sh` or the curl one-liner), the template is already
at `~/.claude/case-templates/CLAUDE.md`:
```bash
mkdir -p /cases/<CASENAME>
cp ~/.claude/case-templates/CLAUDE.md /cases/<CASENAME>/CLAUDE.md
```

If you have the repo or archive available, copy from there instead:
```bash
mkdir -p /cases/<CASENAME>
cp case-templates/CLAUDE.md /cases/<CASENAME>/CLAUDE.md
```

**Required customisations for each new case:**
1. Update `## Case Overview` — client name, domain, threat actor, incident date, role
2. Update `## Evidence Files` — list all E01/img files with their system/role
3. Update `## Common Commands` — adjust image paths and filenames
4. Update `## Network Topology` — subnet map for the specific engagement
5. Update `## Domain Accounts` — DA and service accounts discovered
6. Update `## Known IOCs` — populate as artifacts are confirmed
7. Update `## Incident Timeline` — build out as analysis progresses

The template as shipped reflects the SRL FOR508 lab scenario. Strip the SRL-specific
content and fill in new case details before use.

---

### (11) analysis-scripts/generate_pdf_report.py → `/cases/<casename>/analysis/generate_pdf_report.py`

**What it is:** A reusable WeasyPrint-based PDF report generator. Claude uses this
as its output engine for all forensic PDF reports. It accepts a `data` dict and an
`output_path` string and renders an HTML template to PDF.

**Install:**

If you used the installer, copy from `~/.claude/analysis-scripts/`:
```bash
mkdir -p /cases/<CASENAME>/analysis
cp ~/.claude/analysis-scripts/generate_pdf_report.py /cases/<CASENAME>/analysis/generate_pdf_report.py
```

If you have the repo or archive available:
```bash
mkdir -p /cases/<CASENAME>/analysis
cp analysis-scripts/generate_pdf_report.py /cases/<CASENAME>/analysis/generate_pdf_report.py
```

**Dependency:**
```bash
pip3 install weasyprint
# If weasyprint fails, also install:
sudo apt-get install -y python3-gi python3-gi-cairo gir1.2-gtk-3.0 libpango-1.0-0
```

**Usage pattern:** Claude generates a `generate_<topic>_report.py` script per
investigation that imports this module:
```python
import sys
sys.path.insert(0, './analysis')
from generate_pdf_report import generate_report

DATA = {
    "case_id":     "CASE-ID-001",
    "client":      "Client Name",
    "prepared_by": "DFIR Consultant",
    "title":       "Report Title",
    "subtitle":    "Evidence source · System · Key Finding",
    "body_html":   BODY,   # MUST be r"""...""" raw string if body contains Windows paths
}
generate_report(DATA, "./analysis/report-name.pdf")
```

**Critical gotcha:** The `body_html` variable must use a Python **raw string**
(`r"""..."""`) if it contains Windows filesystem paths (e.g. `C:\Users\...`).
Otherwise Python will raise a `SyntaxError: unicode error 'unicodeescape'` on `\U`
and `\S` escape sequences.

---

### (12–15) analysis-scripts/ntp_*.py → `~/.claude/analysis-scripts/`

**What they are:** The NTP enrichment tool layer. The agent calls these via `Bash()` as part of the `ntp-enrichment` skill workflow.

| Script | Purpose |
|--------|---------|
| `ntp_resolver.py` | Resolves the NTP source for the investigated system — extracts EID 35/260 from the Plaso export, or falls back to analyst prompt / environment assumption. Emits an `NTPContext` with `ConfidenceRank`. |
| `ntp_enricher.py` | Reads the psort CSV, computes `ntp_source`, `nist_time`, `ntp_offset_s`, `ntp_assumption`, `nist_delta_s` per row, writes the enriched CSV sorted on `nist_time`, and runs the self-correction loop. |
| `ntp_manifest.py` | Writes the manifest JSON the agent reads to decide whether to accept the result or self-correct (`rubric_pass`, `rubric_failures`, `suggested_corrective_action`). |
| `ntp_nist_client.py` | Queries the NIST time service to validate the NTP source and derive a clock offset. Requires `NIST_API_KEY` for production use. |

**Install** (handled automatically by `install.sh`):
```bash
cp analysis-scripts/ntp_resolver.py    ~/.claude/analysis-scripts/ntp_resolver.py
cp analysis-scripts/ntp_enricher.py    ~/.claude/analysis-scripts/ntp_enricher.py
cp analysis-scripts/ntp_manifest.py    ~/.claude/analysis-scripts/ntp_manifest.py
cp analysis-scripts/ntp_nist_client.py ~/.claude/analysis-scripts/ntp_nist_client.py
pip3 install -r requirements.txt
```

**NIST API key** — optional, but strongly recommended {#nist-api-key}

Without a key the enrichment falls back to standard NTP, which is an insecure protocol subject to spoofing and man-in-the-middle attacks. Use of plain NTP is **discouraged in production or legal proceedings** and should be limited to lab or non-production environments. With a key, the tooling uses the secured sNTP variant anchored to NIST time services.

> **Security rules:**
> - Never hardcode the key in a script or config file inside a case directory
> - Never commit it to git — add `*.env` and `secrets.*` to `.gitignore`
> - Never share it in Slack, email, or case documentation
> - If the key is exposed, revoke it immediately at nvd.nist.gov and request a new one
> - On shared SIFT workstations, store the key in your user's `~/.bashrc` only — not in `/etc/environment` or any system-wide profile

---

## What Is NOT Included (and Why)

| Excluded | Reason |
|----------|--------|
| `~/.claude/.credentials.json` | Contains your Anthropic API key — never share or copy this |
| `~/.claude/history.jsonl` | Session command history — machine/session specific |
| `~/.claude/projects/` | Session memory and conversation state — case specific |
| `~/.claude/debug/` | Session debug logs — not portable |
| `~/.claude/telemetry/` | Usage telemetry — machine specific |
| `~/.claude/cache/` | Auto-regenerated on first run |
| `~/.claude/backups/` | Auto-generated config backups |
| `~/.claude/plugins/` | Auto-downloaded from Anthropic marketplace on first run |
| `/cases/srl/analysis/*.py` (generated) | Case-specific report scripts — not reusable as-is |
| Evidence files (*.E01, *.img) | Read-only evidence — never copy or share |

---

## Starting a Fresh Investigation

After running the installer, the case template and analysis script live in `~/.claude/`
and are ready to copy into any new case directory — no need to keep the repo around.

```bash
# 1. Prepare case directory
export CASE=CLIENT-IR-2025-001
mkdir -p /cases/${CASE}/{analysis,exports,reports}
cp ~/.claude/case-templates/CLAUDE.md /cases/${CASE}/CLAUDE.md
cp ~/.claude/analysis-scripts/generate_pdf_report.py /cases/${CASE}/analysis/
nano /cases/${CASE}/CLAUDE.md   # fill in case details

# 2. Mount evidence (example — adjust paths)
sudo mkdir -p /mnt/ewf_rd01 /mnt/rd01
sudo ewfmount /cases/${CASE}/suspect.E01 /mnt/ewf_rd01
OFFSET=$(sudo mmls /mnt/ewf_rd01/ewf1 | awk '/NTFS/{print $3; exit}')
sudo mount -o ro,loop,noatime,offset=$((OFFSET*512)) /mnt/ewf_rd01/ewf1 /mnt/rd01

# 3. Launch Claude from case root (critical — sets relative Write paths)
cd /cases/${CASE}
claude
```

---

## How to Use Claude SIFT Workstation Prompts

Once `claude` is launched from the case directory, you interact with it using natural
language prompts. Claude reads the global `CLAUDE.md` and the per-case `CLAUDE.md`
automatically — you do not need to tell it which skill to use. It consults the appropriate
skill file based on the task.

### Available Skills

| Skill | What it does | Example trigger phrase |
|-------|-------------|----------------------|
| `plaso-timeline` | Builds super-timelines with log2timeline, filters with psort | "Build a super-timeline from the disk image" |
| `ntp-enrichment` | Normalises timestamps against NIST-anchored NTP source; enriches psort CSV | "Enrich the timeline CSV with NTP-corrected timestamps" |
| `memory-analysis` | Volatility 3 memory forensics — processes, network, injected code | "Run memory analysis on the RAM capture" |
| `sleuthkit` | Filesystem forensics — file listing, carving, deleted file recovery | "List all deleted files in the NTFS partition" |
| `windows-artifacts` | EZ Tools suite — MFT, Event Logs, Registry, Prefetch, LNK, Jump Lists | "Parse the MFT and event logs for lateral movement" |
| `yara-hunting` | YARA rule scanning, IOC sweeps across carved files or mounted image | "Sweep all executables with the threat hunting YARA rules" |

### Example — Plaso Timeline with NTP Enrichment

The most common investigation workflow combines the `plaso-timeline` and
`ntp-enrichment` skills in sequence. Claude handles both automatically from a
single prompt.

**Step 1 — Generate the super-timeline**

After mounting evidence and launching `claude` from the case directory, type:

```
Build a super-timeline from /mnt/rd01. Write the .plaso file to exports/ and
filter it to exports/timeline.csv sorted by time.
```

Claude will:
1. Run `log2timeline.py` against the mounted image
2. Run `psort.py` to filter and export a sorted CSV
3. Verify tool output and report any errors

**Step 2 — Enrich timestamps with NTP correction**

Once the CSV is ready, prompt:

```
Enrich exports/timeline.csv with NTP-corrected timestamps. The case directory
is /cases/CLIENT-IR-2025-001. Write the enriched output to exports/.
```

Claude will:
1. Invoke `ntp_resolver.py` to identify the NTP source from EID 35/260 events in the timeline
2. Query the NIST time service via `ntp_nist_client.py` to validate the source and measure clock offset
3. Run `ntp_enricher.py` to compute corrected timestamps for every row and write the enriched CSV
4. Write a session audit log to `./logs/<session_id>.jsonl` and a human-readable summary to `./analysis/<session_id>_forensic_audit.log`
5. Run a self-correction loop if any rows fall outside the plausibility bound

**Combined one-shot prompt**

You can also ask Claude to do both steps in a single prompt:

```
Build a super-timeline from /mnt/rd01, export to exports/timeline.csv, then
enrich the timestamps using the NTP enrichment skill with NIST validation.
Case directory is /cases/CLIENT-IR-2025-001.
```

Claude will chain the skills automatically — timeline first, enrichment second —
and produce both `exports/timeline_enriched.csv` and the forensic audit logs.

> **Tip:** If you know the NTP source already (e.g. from network logs), include it
> in the prompt: "The system used `time.windows.com` as its NTP server." This
> skips the auto-detection phase and is logged as a higher-confidence assumption.

---

## Notes on Chain of Custody

- Claude never writes to `/cases/`, `/mnt/`, or `/media/` — enforced by `settings.json`
- The `Stop` hook appends an audit log entry to `./analysis/forensic_audit.log`
  after every session — review this log as part of your case documentation
- All tool outputs use `tee` to write to `./exports/` — raw tool output is preserved
- Always verify image integrity before analysis: `ewfverify /cases/${CASE}/*.E01`

---

## Audit Logging

Protocol SIFT ships two complementary layers of audit logging.

### Layer 1 — Agent-level trace (always active)

The `PostToolUse` hook in `settings.json` fires after **every Claude tool call** and
appends a structured JSON line to `~/.protocol-sift/agent_trace.jsonl`. This records
every `Bash`, `Read`, `Write`, and `Edit` call the agent makes, with timestamp,
tool name, truncated input, and token usage.

The `Stop` hook appends a conversation summary to `./analysis/forensic_audit.log`
at the end of every session.

No configuration required — these hooks are installed automatically.

### Layer 2 — Skill-level structured log (`sift_logger.py`)

Python scripts in `analysis-scripts/` emit granular, per-phase events that are
invisible to the agent-level hook (internal Python file I/O, NIST queries,
enrichment phases, self-correction loops). These are written by `sift_logger.py`.

**Log files produced per skill run:**

| File | Description |
|------|-------------|
| `./logs/<session_id>.jsonl` | Per-session JSONL event stream — one JSON object per line |
| `./analysis/<session_id>_forensic_audit.log` | Human-readable skill summary with evidence file list and source citations |

Session IDs are unique per run (`SIFT-YYYY-MM-DD-<8-hex-chars>`) — no log is ever
overwritten.

### Log destination: local-only vs S3

**Local-only mode (default — no configuration required)**

Logs are written to the case working directory. No env vars needed, no network
access, no boto3 calls.

```
./logs/<session_id>.jsonl
./analysis/<session_id>_forensic_audit.log
```

**S3 mode (opt-in)**

#### Prerequisites

Before enabling S3 logging the following must be in place:

| Requirement | Details |
|-------------|---------|
| AWS account | An active AWS account with permission to create and manage S3 buckets |
| S3 bucket | A bucket in your chosen region (e.g. `agent_logs_sift`). Create it in the AWS Console under **S3 → Create bucket**. Keep the default "Block all public access" setting — these are audit logs, not public artifacts. Enable **versioning** on the bucket to retain overwritten objects. |
| IAM permissions | The IAM user, role, or EC2 instance profile running the SIFT workstation needs: `s3:PutObject` and `s3:GetObject` on the bucket objects, and `s3:ListBucket` and `s3:HeadObject` on the bucket itself. See the minimal IAM policy below. |
| boto3 installed | Included in `requirements.txt` — installed automatically by `install.sh` or `pip3 install -r requirements.txt`. |
| AWS credentials | Configured via environment variables, `~/.aws/credentials` (`aws configure`), or an EC2 instance profile. See the credential chain below. |

**Minimal IAM policy** — attach this to the IAM user or role running the SIFT workstation:
```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Action": ["s3:PutObject", "s3:GetObject", "s3:HeadObject"],
      "Resource": "arn:aws:s3:::agent_logs_sift/*"
    },
    {
      "Effect": "Allow",
      "Action": "s3:ListBucket",
      "Resource": "arn:aws:s3:::agent_logs_sift"
    }
  ]
}
```

Replace `agent_logs_sift` with your actual bucket name.

#### How logs are shipped to S3

Log shipping is handled by **`sift_s3_sync.py`** — a standalone Python script that
runs on a cron schedule. It does **not** run inline with the skill; it is a separate
process that syncs completed log files from the local `./logs/` directory to S3
at a configurable interval.

On each cron run, `sift_s3_sync.py`:
1. Scans the case `logs/` directory for all `.jsonl` files produced by `sift_logger.py`
2. Computes an MD5 of each local file and compares it against the S3 object ETag
3. Uploads only files that are new or have changed since the last sync (`PutObject`)
4. Prints a timestamped line per upload to stdout (captured by cron to a log file)

S3 object key structure:
```
s3://<SIFT_S3_BUCKET>/<SIFT_S3_PREFIX>/<YYYY-MM-DD>/<session_id>/events.jsonl
```

Example:
```
s3://agent_logs_sift/sift-logs/2026-06-11/SIFT-2026-06-11-a3f17c2e/events.jsonl
```

#### Setting up the cron job

The script is installed to `~/.claude/analysis-scripts/sift_s3_sync.py` by
`install.sh`. Set up the cron job once per case (or per workstation if you
want to sync across all cases):

```bash
crontab -e
```

Add one line per active case directory. The recommended interval is every
15 minutes — adjust to suit your operational tempo:

```
# Protocol SIFT — S3 audit log sync (every 15 minutes)
*/15 * * * * SIFT_S3_BUCKET=agent_logs_sift SIFT_S3_REGION=us-west-2 SIFT_S3_PREFIX=sift-logs \
    python3 ~/.claude/analysis-scripts/sift_s3_sync.py \
    --logs-dir /cases/CLIENT-IR-2025-001/logs >> ~/sift-s3-sync.log 2>&1
```

To verify the cron job works before committing to the schedule, run it manually first:

```bash
SIFT_S3_BUCKET=agent_logs_sift SIFT_S3_REGION=us-west-2 \
    python3 ~/.claude/analysis-scripts/sift_s3_sync.py \
    --logs-dir /cases/CLIENT-IR-2025-001/logs --dry-run
```

The `--dry-run` flag lists what would be uploaded without touching S3.

#### Configuration environment variables

`sift.env` at the repo root is the canonical place to set these. Source it before
launching `claude` or in each cron entry:

```bash
source /path/to/protocol-sift/sift.env
```

The file ships with the following variables pre-configured:

```bash
export SIFT_S3_BUCKET=hackasans-correlator-dev-sift-ai-logs   # S3 bucket name
export SIFT_S3_REGION=us-west-2                                # AWS region
export SIFT_S3_PREFIX=sift-logs                                # key prefix
```

`sift.env` is listed in `.gitignore` — it is machine-local and should never be
committed, especially if AWS credentials are added to it. Edit the values in place
after cloning or installing.

#### AWS credential chain

`sift_s3_sync.py` uses the standard boto3 credential resolution order:

1. Environment variables (`AWS_ACCESS_KEY_ID` / `AWS_SECRET_ACCESS_KEY` / `AWS_SESSION_TOKEN`)
2. `~/.aws/credentials` (populated via `aws configure`)
3. EC2 instance profile — if the SIFT workstation is an EC2 instance with an
   attached IAM role, no credentials need to be stored on disk at all

For EC2-hosted SIFT workstations, attaching an IAM role with the minimal policy
above is the recommended approach.

Sync errors are non-fatal — the script prints the error to stderr (captured by
cron) and continues with remaining files. Local logging is always written
regardless of S3 sync status.

### Model attribution

The model name is recorded in every `session_init` event. Set it to match the
Claude model driving the session:

```bash
export SIFT_AGENT_MODEL=claude-sonnet-4-6   # default
```

### JSONL event schema

Every line in `<session_id>.jsonl` is a JSON object. The following fields appear
in all events; additional fields are event-type specific.

| Field | Source | Present in |
|-------|--------|-----------|
| `type` | event name | every entry |
| `session_id` | generated at session start | every entry |
| `timestamp` | `datetime.now(timezone.utc).isoformat()` — microsecond UTC | every entry |
| `os_user` | `getpass.getuser()` — OS user who ran the skill | every entry |
| `skill` | `SiftSession` constructor arg | `session_init` |
| `model` | `SIFT_AGENT_MODEL` env var | `session_init` |
| `platform` | `sys.platform` | `session_init` |
| `project_directory` | `os.getcwd()` at session start | `session_init` |
| `reasoning` | caller-supplied string explaining the forensic rationale | tool/phase events |
| `files_accessed` | list of evidence paths read during this phase | tool/phase events |
| `is_error` | `true` for failure or halt events | error events |
| `tool_name` | CLI tool invoked | `tool_called` |
| `tool_input` | exact args dict passed to the tool | `tool_called` |
| `output_path` | path of any file written | completion events |
| `duration_s` | wall-clock seconds for the full session | `session_complete`, `session_error` |
| `exit_code` | process exit code | `session_complete` |

**Example `session_init` entry:**
```json
{
  "type": "session_init",
  "session_id": "SIFT-2026-06-09-a3f17c2e",
  "timestamp": "2026-06-09T14:16:07.043821+00:00",
  "os_user": "sansforensics",
  "skill": "ntp-enrichment",
  "model": "claude-sonnet-4-6",
  "platform": "linux",
  "project_directory": "/cases/CLIENT-IR-2025-001",
  "case_dir": "/cases/CLIENT-IR-2025-001",
  "input": "exports/timeline.csv"
}
```

### Adding logging to additional skills

Any Python script in `analysis-scripts/` can participate by importing `SiftSession`:

```python
from sift_logger import SiftSession

with SiftSession("plaso-timeline", case_dir=args.case_dir) as sess:
    sess.log(
        "tool_called",
        tool_name="log2timeline.py",
        tool_input=vars(args),
        reasoning="Building super-timeline from disk image.",
    )
    # ... skill logic ...
    sess.log(
        "timeline_complete",
        output_path=str(plaso_path),
        files_accessed=[args.image],
        reasoning="log2timeline completed; .plaso artifact written.",
    )
    sess.set_exit_code(0)
```

The `SiftSession` context manager automatically emits `session_init` on entry and
`session_complete` (or `session_error`) on exit, and writes the
`<session_id>_forensic_audit.log` summary regardless of how the skill exits.
