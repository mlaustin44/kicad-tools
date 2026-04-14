"""Integration test for schematic PDF export."""
from __future__ import annotations
import shutil
from pathlib import Path
from release_generator.config import load_config
from release_generator.schematic import export_schematic_pdf
from release_generator.utils import scaffold_output_dir


def _write_test_config(workdir: Path, kicad_project: Path) -> Path:
    """Copy the test project files alongside a release.toml in workdir.

    Creates a minimal release.toml that passes validation and points at
    the copied board/schematic files. The template is a stub SVG.
    """
    sch = next(kicad_project.glob("*.kicad_sch"))
    pcb = next(kicad_project.glob("*.kicad_pcb"))
    shutil.copy(sch, workdir / sch.name)
    shutil.copy(pcb, workdir / pcb.name)
    (workdir / "tb.svg").write_text("<svg/>")
    (workdir / "release.toml").write_text(f"""
[project]
name = "Test"
version = "T1"
date = "auto"
pcb_file = "{pcb.name}"
schematic_file = "{sch.name}"

[titleblock]
template = "tb.svg"
company = "ACME"
drawn_by = "M Test"
confidentiality = "PROPRIETARY"

[[revisions]]
rev = "01"
ec = "N/A"
description = "Initial"

[fab_drawing]
title = "Fab Drawing"
page_size = "A4"
notes = []
include_3d_render = false
render_view = "top"

[assembly_drawing]
title = "Assembly Drawing"
page_size = "A4"
notes = []
layers_front = ["F.Fab", "Edge.Cuts"]
layers_back = ["B.Fab", "Edge.Cuts"]

[bom]
group_by = ["value"]
columns = ["reference", "value", "quantity"]

[gerbers]
layers = "auto"
subtract_soldermask = false
""")
    return workdir / "release.toml"


def test_schematic_pdf_is_produced(kicad_project, tmp_path):
    cfg_path = _write_test_config(tmp_path, kicad_project)
    cfg = load_config(cfg_path)
    scaffold_output_dir(cfg)
    pdf, warnings = export_schematic_pdf(cfg, verbose=False)
    assert pdf.exists()
    assert pdf.stat().st_size > 1000  # nontrivial PDF
