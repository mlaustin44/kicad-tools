"""Integration test for board introspection."""
from __future__ import annotations
from release_generator.board_introspect import parse_board


def test_parses_real_board(kicad_project):
    pcb = next(kicad_project.glob("*.kicad_pcb"))
    info = parse_board(pcb)

    # Should have a non-trivial stackup (≥ 4 layers for a 2-layer board, more for 4-layer)
    assert len(info.stackup) >= 4
    # Should detect copper layers
    cu = [l for l in info.stackup if l.type == "copper"]
    assert len(cu) >= 2
    # All enabled layers should be strings
    assert info.enabled_layers
    assert all(isinstance(n, str) for n in info.enabled_layers)
    # Board dimensions should be plausible (PCBs are between 1mm and 1m)
    assert info.width_mm is not None and 1.0 < info.width_mm < 1000.0
    assert info.height_mm is not None and 1.0 < info.height_mm < 1000.0
    # Characteristics: copper count matches the copper stackup entries.
    assert info.copper_layer_count == len(cu)
    # Board thickness, if computable, is positive and under 10mm.
    if info.board_thickness_mm is not None:
        assert 0.0 < info.board_thickness_mm < 10.0
    # Impedance flag is boolean (not None).
    assert isinstance(info.impedance_controlled, bool)
    assert isinstance(info.edge_plating, bool)
    assert isinstance(info.castellated_pads, bool)
