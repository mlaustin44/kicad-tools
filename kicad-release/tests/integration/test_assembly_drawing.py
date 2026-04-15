"""Integration test for assembly drawing composition."""
from __future__ import annotations
import shutil
from pathlib import Path

from release_generator.assembly_drawing import compose_assembly_drawing
from release_generator.config import load_config
from release_generator.utils import scaffold_output_dir
from ._helpers import write_test_config

REPO_ROOT = Path(__file__).resolve().parents[2]
TEMPLATE = REPO_ROOT / "templates" / "titleblock_assembly_a4.svg"


def test_assembly_drawing_pdf_is_produced(kicad_project, tmp_path):
    cfg_path = write_test_config(tmp_path, kicad_project)
    proj_dir = cfg_path.parent
    shutil.copy(TEMPLATE, proj_dir / "tb.svg")
    cfg = load_config(cfg_path)
    scaffold_output_dir(cfg)
    pdf, warnings = compose_assembly_drawing(cfg, verbose=False)
    assert pdf.exists()
    assert pdf.read_bytes()[:4] == b"%PDF"
    for w in warnings:
        print(f"warning: {w}")
