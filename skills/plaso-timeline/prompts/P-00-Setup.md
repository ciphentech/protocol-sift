## P-00 — Python environment + pinned dependencies

**Goal:** If you are working on a local workstation, then run theses steps below to establish the Python runtime and lock dependency versions before
any code or tests are written. P-01 onwards assumes `pytest`, `pandas`, and
`ntplib` import cleanly. This step makes that assumption explicit and
verifiable.
*** Caveats ***
 If you are running this on a SIFT workstation direction, copy the repo using the main README.md directions and install, making sure you include the requirements.txt items.

**Depends on:** Nothing.

**Prompt:**

````
Work inside protocol-sift/. Establish the Python runtime environment for the
NTP enrichment feature. No production code or tests in this step — only
environment setup, dependency pinning, and import verification.

Deliverables:

1. Verify Python ≥ 3.10. The codebase uses PEP 604 union syntax (`str | Path`)
   and PEP 585 generics (`tuple[dict, NTPContext]`, `list[str]`). Both require
   Python 3.10 or higher.

     python3 --version

   If lower than 3.10, halt and notify the analyst. Do not attempt to proceed.
   The SIFT workstation Ubuntu 22.04 image ships with Python 3.10.

2. Create a virtual environment at ./venv/ if one does not already exist:

     python3 -m venv venv
     source venv/bin/activate

   All subsequent pytest, pip, and python invocations in P-01 through P-10
   assume this venv is active. Document this in a README note if helpful.

3. Establish requirements.txt at the repo root. If the file already exists,
   PRESERVE every existing entry — merge, do not overwrite. The complete set
   of NTP-enrichment dependencies with pinned ranges:

     # Test harness
     pytest>=7.4,<9.0

     # Data handling — spec §6 requires pandas ≥ 2.0
     pandas>=2.0,<3.0

     # NTP enrichment (also added in P-10 — duplicated here so that a single
     # `pip install -r requirements.txt` covers the whole feature)
     ntplib>=0.4.0

   Pinning rationale: minimum version locks the API surface we test against;
   upper bound on the major version prevents a future pandas 3.0 or pytest 9.0
   from breaking the build silently. Patch and minor updates remain allowed.

4. Install:

     pip install --upgrade pip
     pip install -r requirements.txt

5. Verify all three packages import and emit their versions to stdout:

     python -c "
     import sys
     print(f'Python: {sys.version.split()[0]}')
     import pytest;  print(f'pytest:  {pytest.__version__}')
     import pandas;  print(f'pandas:  {pandas.__version__}')
     import ntplib
     v = getattr(ntplib, '__version__', 'installed (no __version__ attr)')
     print(f'ntplib:  {v}')
     "

6. Pin the interpreter version with a .python-version file at the repo root:

     python3 -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')" \
       > .python-version

   This is read by pyenv and similar version managers; harmless if absent.

7. Add venv/ and .python-version handling to .gitignore (preserve existing
   entries — append only):

     venv/
     __pycache__/
     *.pyc
     .pytest_cache/

Acceptance:
  python3 --version
prints "Python 3.10.x" or higher.
  source venv/bin/activate && \
  python -c "import pytest, pandas, ntplib; print('imports OK')"
prints "imports OK".
  grep -E "^(pytest|pandas|ntplib)" requirements.txt | wc -l
prints 3.
  test -f .python-version && cat .python-version
prints a version ≥ 3.10.
````

**Acceptance check:**

````bash
cd protocol-sift
python3 --version
# Must show: Python 3.10.x or higher

# Activate the venv created by the prompt
source venv/bin/activate

python -c "import pytest, pandas, ntplib; print('imports OK')"
# Must show: imports OK

grep -E "^(pytest|pandas|ntplib)" requirements.txt | wc -l
# Must show: 3

test -f .python-version && cat .python-version
# Must show: a version string ≥ 3.10

# Sanity check: pandas major version is what we expect
python -c "import pandas; assert pandas.__version__.startswith('2.'), f'pandas major != 2: {pandas.__version__}'; print('pandas major OK')"
# Must show: pandas major OK
````

---
