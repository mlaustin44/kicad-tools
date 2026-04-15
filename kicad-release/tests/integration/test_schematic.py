"""Integration test for schematic PDF export."""
from __future__ import annotations
from release_generator.config import load_config
from release_generator.schematic import export_schematic_pdf
from release_generator.utils import scaffold_output_dir
from ._helpers import write_test_config


def test_schematic_pdf_is_produced(kicad_project, tmp_path):
    cfg_path = write_test_config(tmp_path, kicad_project)
    cfg = load_config(cfg_path)
    scaffold_output_dir(cfg)
    pdf, warnings = export_schematic_pdf(cfg, verbose=False)
    assert pdf.exists()
    assert pdf.stat().st_size > 1000
