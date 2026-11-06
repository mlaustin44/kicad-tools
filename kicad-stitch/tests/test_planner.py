from dataclasses import replace

import pytest
from shapely.geometry import Point, box

from kicad_stitch.model import Settings, Signal, load_settings
from kicad_stitch.planner import choose_pitch, detect_pairs, plan


def encode(poly):
    return [{"shell": list(poly.exterior.coords), "holes": [list(h.coords) for h in poly.interiors]}]


def board():
    return {"outline": encode(box(0, 0, 40, 30)), "layers": ["F.Cu", "B.Cu"],
            "ground": {"F.Cu": encode(box(0.4, 0.4, 39.6, 29.6)),
                       "B.Cu": encode(box(0.4, 0.4, 39.6, 29.6))},
            "obstacles": [], "footprints": [], "existing_vias": [], "tracks": [],
            "bridges": [{"at": [2, 2], "layers": ["F.Cu", "B.Cu"]}],
            "nets": ["GND"], "rules": {}}


def settings(**kwargs):
    return Settings(perimeter=False, grid=False, fingers=False, auto_pairs=False, **kwargs)


def test_perimeter_honors_components_copper_edges_and_cutouts():
    b = board()
    outline = box(0, 0, 40, 30).difference(box(15, 10, 25, 20))
    b["outline"] = encode(outline)
    obstacle = box(8, 0, 12, 5)
    b["obstacles"] = [{"kind": "copper", "polygons": encode(obstacle)}]
    component = box(25, 0, 30, 4)
    b["footprints"] = [{"reference": "U1", "polygons": encode(component)}]
    config = replace(settings(), perimeter=True, pitch_mm=3)
    result = plan(b, config)
    assert len(result.candidates) > 30
    assert any(14 <= c.x <= 26 and 9 <= c.y <= 21 for c in result.candidates)
    for c in result.candidates:
        point = Point(c.x, c.y)
        assert outline.contains(point.buffer(config.diameter_mm / 2 + config.edge_clearance_mm))
        assert point.distance(obstacle) >= config.diameter_mm / 2 + config.clearance_mm
        assert point.distance(component) >= config.diameter_mm / 2 + config.component_clearance_mm


def test_small_island_gets_off_grid_via_and_reaches_root():
    b = board()
    island = box(21.1, 21.1, 22.1, 22.1)
    b["ground"]["F.Cu"] = encode(box(0.4, 0.4, 10, 29.6)) + encode(island)
    result = plan(b, settings())
    assert len(result.candidates) == 1
    assert result.candidates[0].rule == "island"
    assert island.covers(Point(result.candidates[0].x, result.candidates[0].y))
    assert not any(d["rule"] == "island_unresolved" for d in result.diagnostics)


def test_two_layers_of_floating_copper_are_not_a_ground_reference():
    b = board()
    b["ground"]["B.Cu"] = encode(box(0.4, 0.4, 10, 29.6))
    b["ground"]["F.Cu"] = encode(box(0.4, 0.4, 10, 29.6)) + encode(box(20, 20, 25, 25))
    b["ground"]["In1.Cu"] = encode(box(20, 20, 25, 25))
    result = plan(b, settings())
    assert result.candidates == []
    assert sum(d["rule"] == "island_unresolved" for d in result.diagnostics) == 2


def test_multistep_overlap_connects_to_root():
    b = board()
    b["ground"] = {"F.Cu": encode(box(1, 1, 10, 10)),
                   "In1.Cu": encode(box(8, 1, 18, 8)),
                   "B.Cu": encode(box(16, 1, 22, 7))}
    b["bridges"] = []
    result = plan(b, settings())
    assert len(result.candidates) == 2
    assert not any(d["rule"] == "island_unresolved" for d in result.diagnostics)


def test_blocked_island_remains_explicitly_unresolved():
    b = board()
    b["ground"]["F.Cu"] += encode(box(20, 20, 22, 22))  # union with main: replace below
    b["ground"]["F.Cu"] = encode(box(1, 1, 10, 25)) + encode(box(20, 20, 22, 22))
    b["obstacles"] = [{"kind": "keepout", "polygons": encode(box(19, 19, 23, 23))}]
    result = plan(b, settings())
    assert not result.candidates
    assert any(d["rule"] == "island_unresolved" for d in result.diagnostics)


def test_through_vias_clear_copper_on_intermediate_layers():
    b = board()
    obstacle = box(10, 10, 30, 20)
    b["obstacles"].append({"kind": "copper", "polygons": encode(obstacle)})
    result = plan(b, replace(settings(), grid=True, pitch_mm=3))
    assert result.candidates
    assert all(Point(c.x, c.y).distance(obstacle) >= 0.5 for c in result.candidates)


def test_existing_vias_block_spacing_even_if_they_do_not_connect_ground():
    b = board()
    b["bridges"] = [{"at": [2, 25], "layers": ["F.Cu", "B.Cu"]}]
    b["existing_vias"] = [{"at": [3, 3], "net": "GND", "layers": ["F.Cu"]}]
    result = plan(b, replace(settings(), grid=True, pitch_mm=3))
    assert all(Point(c.x, c.y).distance(Point(3, 3)) >= 1 for c in result.candidates)
    assert any(Point(c.x, c.y).distance(Point(3, 3)) < 3 for c in result.candidates)


def test_spacing_budget_and_determinism():
    b = board()
    config = replace(settings(), grid=True, max_vias=12, pitch_mm=3)
    a = plan(b, config)
    assert a.to_dict() == plan(b, config).to_dict()
    assert len(a.candidates) == 12
    assert any(d["rule"] == "via_budget" for d in a.diagnostics)
    for i, c in enumerate(a.candidates):
        assert all(Point(c.x, c.y).distance(Point(d.x, d.y)) >= 1 for d in a.candidates[i + 1:])


def test_narrow_finger_is_identified_and_stitched():
    b = board()
    finger = box(10, 8, 22, 9)
    b["ground"]["F.Cu"] = encode(box(1, 1, 10.5, 25).union(finger))
    result = plan(b, replace(settings(), fingers=True))
    assert any(c.rule == "finger" and c.x > 12 for c in result.candidates)
    assert any(d["rule"] == "finger_detected" for d in result.diagnostics)


def test_pair_detection_requires_both_names():
    assert detect_pairs(["/USB_P", "/USB_N", "X+", "X-", "A_DP", "A_DM", "LONE_P"]) == [
        ("/USB_P", "/USB_N"), ("A_DP", "A_DM"), ("X+", "X-")]


def test_pair_transition_places_symmetric_vias_atomically():
    b = board()
    b["nets"] += ["USB_P", "USB_N"]
    b["existing_vias"] = [{"at": [10, 10], "net": "USB_P", "layers": ["F.Cu", "B.Cu"]},
                          {"at": [10, 11], "net": "USB_N", "layers": ["F.Cu", "B.Cu"]}]
    config = replace(settings(), auto_pairs=True)
    result = plan(b, config)
    assert [(c.x, c.y) for c in result.candidates] == [(10, 9), (10, 12)]
    b["obstacles"].append({"kind": "keepout", "polygons": encode(box(9, 8, 11, 9.5))})
    result = plan(b, config)
    assert not result.candidates
    assert any(d["rule"] == "transition_gap" for d in result.diagnostics)


def test_rf_nets_are_not_mistaken_for_a_differential_pair():
    b = board()
    b["nets"] += ["RF_A", "RF_B"]
    b["existing_vias"] = [{"at": [10, 10], "net": "RF_A", "layers": ["F.Cu", "B.Cu"]},
                          {"at": [10, 11], "net": "RF_B", "layers": ["F.Cu", "B.Cu"]}]
    config = replace(settings(), signals=(Signal(nets=("RF_*",), mode="transitions"),))
    result = plan(b, config)
    assert [(c.x, c.y) for c in result.candidates] == [(9, 10), (11, 10), (9, 11), (11, 11)]
    explicit_pair = replace(config.signals[0], differential=True)
    result = plan(b, replace(config, signals=(explicit_pair,)))
    assert [(c.x, c.y) for c in result.candidates] == [(10, 9), (10, 12)]


def test_signal_pitch_obeys_electrical_bound():
    b = board()
    b["nets"] += ["RF"]
    config = replace(settings(), max_frequency_hz=2.4e9,
                     signals=(Signal(nets=("RF",), pitch_mm=10),))
    result = plan(b, config)
    diagnostic = next(d for d in result.diagnostics if d["rule"] == "signal_pitch")
    assert 3.01 < diagnostic["effective_pitch_mm"] < 3.02


def test_rf_fence_does_not_put_vias_inside_pair_bundle():
    b = board()
    b["nets"] += ["RF_P", "RF_N"]
    b["tracks"] = [{"net": n, "layer": "F.Cu", "points": [[5, y], [30, y]], "width": 0.2}
                   for n, y in (("RF_P", 10), ("RF_N", 10.3))]
    config = replace(settings(), signals=(Signal(nets=("RF_*",), offset_mm=1, pitch_mm=2),))
    result = plan(b, config)
    assert result.candidates
    assert all(not (10 < c.y < 10.3) for c in result.candidates)
    assert all(c.y <= 9.001 or c.y >= 11.299 or c.x < 5 or c.x > 30 for c in result.candidates)


def test_component_selected_pcb_antenna_can_use_custom_pad_copper():
    b = board()
    antenna = box(10, 10, 20, 14)
    b["nets"] += ["ANT"]
    b["footprints"] = [{"reference": "AE1", "nets": ["GND", "ANT"], "polygons": encode(antenna)}]
    b["signal_copper"] = [{"net": "ANT", "layer": "F.Cu", "polygons": encode(antenna)}]
    b["obstacles"] = [{"kind": "copper", "polygons": encode(antenna)}]
    config = replace(settings(), signals=(Signal(references=("AE1",), offset_mm=1, pitch_mm=2),))
    result = plan(b, config)
    assert result.candidates
    assert all(c.rule == "signal_fence" for c in result.candidates)
    assert all(Point(c.x, c.y).distance(antenna) >= 0.999 for c in result.candidates)
    assert not any(d["rule"] == "signal_unrouted" for d in result.diagnostics)


def test_exclusions_apply_to_all_passes():
    b = board()
    exclusion = box(0, 0, 15, 30)
    result = plan(b, replace(settings(), perimeter=True, grid=True,
                             exclusions_mm=((0, 0, 15, 30),)))
    assert result.candidates
    assert all(Point(c.x, c.y).distance(exclusion) >= 0.3 for c in result.candidates)


def test_frequency_and_rise_time_bound_auto_pitch():
    config = Settings(max_frequency_hz=2.4e9, rise_time_ns=0.1)
    pitch, details = choose_pitch(config, 10000, 1)
    assert details["frequency_hz"] == 5e9
    assert pitch == pytest.approx(299792458000 / (5e9 * 4.3 ** 0.5 * 20))
    with pytest.raises(ValueError, match="below legal"):
        choose_pitch(Settings(max_frequency_hz=100e9), 10000, 1)


@pytest.mark.parametrize("kwargs", [{"pitch_mm": float("nan")}, {"drill_mm": 0.8},
                                   {"max_vias": 0}, {"grid": "false"}, {"epsilon_r": 0}])
def test_invalid_settings_rejected(kwargs):
    with pytest.raises(ValueError):
        Settings(**kwargs)


def test_unknown_config_keys_and_missing_signal_selectors_rejected(tmp_path):
    path = tmp_path / "stitch.toml"
    path.write_text("[stitch]\npich_mm = 3\n")
    with pytest.raises(TypeError):
        load_settings(path)
    with pytest.raises(ValueError, match="no net matches"):
        plan(board(), replace(settings(), signals=(Signal(nets=("ANT*",)),)))


def test_sampling_is_bounded():
    with pytest.raises(ValueError, match="limit|budget|max_samples"):
        plan(board(), replace(settings(), grid=True, pitch_mm=1, max_samples=10))


def test_ambiguous_anchor_does_not_invent_layer_connectivity():
    b = board()
    b["bridges"] = []
    with pytest.raises(ValueError, match="ambiguous"):
        plan(b, replace(settings(), anchors_mm=((5, 5),)))
