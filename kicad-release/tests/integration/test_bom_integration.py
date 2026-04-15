"""Integration test for BOM generation."""
from __future__ import annotations
import csv
import io
from release_generator.config import load_config
from release_generator.bom import generate_bom
from release_generator.utils import scaffold_output_dir
from ._helpers import write_test_config


def test_bom_against_real_project(kicad_project, tmp_path):
    cfg_path = write_test_config(tmp_path, kicad_project)
    cfg = load_config(cfg_path)
    scaffold_output_dir(cfg)
    bom, _ = generate_bom(cfg, verbose=False)
    assert bom.exists()
    rows = list(csv.DictReader(io.StringIO(bom.read_text())))
    assert rows, "expected at least one BOM row"
    assert "reference" in rows[0]
    assert "value" in rows[0]
    assert "quantity" in rows[0]
