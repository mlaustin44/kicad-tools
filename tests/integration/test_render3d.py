"""Integration test for 3D render."""
from __future__ import annotations
from release_generator.config import load_config
from release_generator.render3d import render_pcb
from release_generator.utils import scaffold_output_dir
from ._helpers import write_test_config


def test_render_top_only(kicad_project, tmp_path):
    # Enable 3D render via the tables override
    cfg_path = write_test_config(
        tmp_path, kicad_project,
        tables={"assembly_drawing": {"include_3d_render": True}},
    )
    cfg = load_config(cfg_path)
    scaffold_output_dir(cfg)
    pngs, warnings = render_pcb(cfg, verbose=False)
    assert len(pngs) == 1
    assert pngs[0].exists()
    assert pngs[0].stat().st_size > 10_000  # nontrivial PNG
