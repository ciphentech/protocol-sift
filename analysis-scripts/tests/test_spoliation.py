"""Spoliation tests — crafted-input injection cannot redirect or modify evidence
(Hackathon deliverable #6, SPEC §8).

tests/fixtures/ntp_spoliation.csv carries prompt-injection text in its desc and
notes columns instructing the tool to write into /cases/evidence/ and rewrite
the source in place. The enricher must treat that text as inert data: output
goes only to the requested --output path, /cases/ writes are architecturally
refused, and the source hash never changes.
"""

import hashlib

import pandas as pd
import pytest

from ntp_enricher import enrich, main
from ntp_resolver import resolve_ntp_source


def _sha256(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_crafted_csv_cannot_redirect_output_into_evidence(spoliation_csv_path,
                                                          tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)  # keep ./logs and ./analysis inside tmp
    out = tmp_path / "exports" / "spoliation_enriched.csv"
    rc = main(["--input", str(spoliation_csv_path), "--output", str(out),
               "--skip-nist-check", "--non-interactive"])
    assert rc == 0
    # Output landed exactly where requested, nowhere else.
    assert out.exists()
    written = [p for p in tmp_path.rglob("*.csv")]
    assert written == [out]
    # The injection text survived verbatim as data — it was never interpreted.
    out_df = pd.read_csv(out, dtype=str, keep_default_na=False)
    assert out_df["desc"].str.contains("ignore prior instructions").any()
    # The architectural guard refuses the path the injection asked for.
    df = pd.read_csv(spoliation_csv_path, dtype=str, keep_default_na=False)
    ctx = resolve_ntp_source(df)
    with pytest.raises(ValueError, match="protected evidence"):
        enrich(spoliation_csv_path, ctx, "/cases/evidence/tampered_timeline.csv")


def test_crafted_csv_does_not_modify_source(spoliation_csv_path, tmp_path,
                                            monkeypatch):
    monkeypatch.chdir(tmp_path)
    hash_before = _sha256(spoliation_csv_path)
    out = tmp_path / "exports" / "spoliation_enriched.csv"
    rc = main(["--input", str(spoliation_csv_path), "--output", str(out),
               "--skip-nist-check", "--non-interactive"])
    assert rc == 0
    assert _sha256(spoliation_csv_path) == hash_before
