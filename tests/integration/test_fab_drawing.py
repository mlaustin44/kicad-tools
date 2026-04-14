"""Integration test for fab drawing composition."""
from __future__ import annotations
import shutil
from pathlib import Path

from release_generator.config import load_config
from release_generator.fab_drawing import compose_fab_drawing
from release_generator.utils import scaffold_output_dir
from ._helpers import write_test_config

REPO_ROOT = Path(__file__).resolve().parents[2]
TEMPLATE = REPO_ROOT / "templates" / "titleblock_a4.svg"


def test_fab_drawing_pdf_is_produced(kicad_project, tmp_path):
    cfg_path = write_test_config(tmp_path, kicad_project)
    # The helper writes a stub `tb.svg` next to the config; overwrite it with
    # the real shipped A4 template so the composition has real regions to use.
    proj_dir = cfg_path.parent
    shutil.copy(TEMPLATE, proj_dir / "tb.svg")
    cfg = load_config(cfg_path)
    scaffold_output_dir(cfg)
    pdf, warnings = compose_fab_drawing(cfg, verbose=False)
    assert pdf.exists()
    assert pdf.read_bytes()[:4] == b"%PDF"
    for w in warnings:
        print(f"warning: {w}")
