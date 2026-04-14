"""Integration test for gerbers export."""
from __future__ import annotations
import pytest
from release_generator.config import load_config
from release_generator.gerbers import export_gerbers
from release_generator.utils import scaffold_output_dir, output_dir_for
from ._helpers import write_test_config


def test_gerbers_produces_expected_files(kicad_project, tmp_path):
    cfg_path = write_test_config(tmp_path, kicad_project)
    cfg = load_config(cfg_path)
    scaffold_output_dir(cfg)
    artifacts, _ = export_gerbers(cfg, verbose=False)
    out = output_dir_for(cfg)
    gerber_dir = out / "gerbers"
    # Must have at least one .gbr (copper layer) and at least one .drl
    gbr_files = list(gerber_dir.glob("*.gbr"))
    drl_files = list(gerber_dir.glob("*.drl"))
    assert gbr_files, f"no .gbr files in {gerber_dir}"
    assert drl_files, f"no .drl files in {gerber_dir}"
    # Pick-and-place CSV exists and has a header row
    pos = out / "pick-and-place.csv"
    assert pos.exists()
    assert pos.read_text().count("\n") >= 1
