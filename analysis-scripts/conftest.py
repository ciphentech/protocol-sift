"""Pytest bootstrap for the flat analysis-scripts.

Placing this conftest at the analysis-scripts root puts this directory on sys.path so
tests under tests/ can import the flat scripts by bare name (``from ntp_resolver import
...``) — the same import form used when the scripts run as
``python analysis-scripts/ntp_enricher.py``. No package, no sys.path hacks in the tests
themselves.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(__file__))
