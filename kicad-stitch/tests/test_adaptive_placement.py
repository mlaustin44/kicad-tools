from dataclasses import replace
import math

import pytest
from shapely.geometry import Point, box

from kicad_stitch.model import Settings
from kicad_stitch.planner import Planner, plan
from kicad_stitch.quality import island_recovery, placement_quality
from test_planner import board, encode, settings


def test_edge_and_interior_pitches_are_independent():
    config = replace(settings(), perimeter=True, grid=True, grid_pitch_mm=8,
                     perimeter_pitch_mm=2, signal_pitch_mm=1.5, finger_pitch_mm=2.5)
    result = plan(board(), config)
    assert result.parameters["grid_pitch_mm"] == 8
    assert result.parameters["perimeter_pitch_mm"] == 2
    assert result.parameters["signal_pitch_mm"] == 1.5
    assert result.parameters["finger_pitch_mm"] == 2.5
    assert result.parameters["perimeter_audit"]["max_contour_gap_mm"] <= 2.5


def test_default_edge_spacing_is_denser_than_interior():
    result = plan(board(), settings())
    assert result.parameters["perimeter_pitch_mm"] == result.parameters["grid_pitch_mm"] / 2


def test_frequency_limits_grid_and_fence_separately():
    b = board()
    b["outline"] = encode(box(0, 0, 200, 100))
    result = plan(b, replace(settings(), max_frequency_hz=2.4e9))
    assert result.parameters["grid_pitch_mm"] == pytest.approx(6.023865, abs=1e-5)
    assert result.parameters["perimeter_pitch_mm"] == pytest.approx(3.011933, abs=1e-5)


def test_obstructed_grid_target_moves_to_nearby_legal_site():
    b = board()
    b["outline"] = encode(box(3, 3, 20, 20))
    b["ground"] = {layer: encode(box(3.4, 3.4, 19.6, 19.6)) for layer in ("F.Cu", "B.Cu")}
    b["bridges"] = [{"at": [4, 19], "layers": ["F.Cu", "B.Cu"]}]
    blocked = box(5.2, 5.2, 6.8, 6.8)
    b["obstacles"] = [{"kind": "copper", "polygons": encode(blocked)}]
    result = plan(b, replace(settings(), grid=True, grid_pitch_mm=6, grid_pattern="square"))
    moved = next(c for c in result.candidates if c.rule == "grid" and c.target == [6, 6])
    assert 0.5 < moved.displacement_mm <= 3
    assert Point(moved.x, moved.y).distance(blocked) >= 0.5


def test_island_solver_finds_tiny_off_grid_remainder_after_spacing_exclusion():
    b = board()
    island = box(21.03, 21.09, 22.13, 22.19)
    b["ground"]["F.Cu"] = encode(box(1, 1, 10, 29)) + encode(island)
    b["existing_vias"] = [{"at": [20.8, 21.6], "net": "GND", "layers": ["B.Cu"]}]
    result = plan(b, settings())
    assert len(result.candidates) == 1
    via = result.candidates[0]
    assert via.rule == "island"
    assert Point(via.x, via.y).distance(Point(20.8, 21.6)) >= 1
    assert island.covers(Point(via.x, via.y).buffer(0.3))


@pytest.mark.parametrize("layer,policy,allowed", [
    ("In2.Cu", "internal_antipads", True), ("F.Cu", "internal_antipads", False),
    ("In2.Cu", "avoid", False), ("F.Cu", "antipads", True),
])
def test_power_plane_antipads_are_distinct_from_fixed_copper(layer, policy, allowed):
    b = board()
    power = box(8, 8, 30, 22)
    b["ground"]["In1.Cu"] = b["ground"]["B.Cu"]
    b["bridges"][0]["layers"].append("In1.Cu")
    if layer == "F.Cu":
        b["ground"]["F.Cu"] = encode(box(.4, .4, 39.6, 29.6).difference(power))
    b["obstacles"] = [{"kind": "zone", "net": "+3V3", "layer": layer, "polygons": encode(power)}]
    result = plan(b, replace(settings(), grid=True, grid_pitch_mm=6, zone_policy=policy))
    assert any(power.contains(Point(c.x, c.y)) for c in result.candidates) == allowed


def test_keepouts_remain_hard_even_when_zone_antipads_are_enabled():
    b = board()
    keepout = box(10, 10, 30, 20)
    b["obstacles"] = [{"kind": "keepout", "polygons": encode(keepout)}]
    result = plan(b, replace(settings(), grid=True, zone_policy="antipads"))
    assert all(Point(c.x, c.y).distance(keepout) >= 0.3 for c in result.candidates)


def test_continuous_coverage_finds_a_pocket_without_any_grid_target(monkeypatch):
    b = board()
    finger = box(5, 3.4, 8.3, 3.6)
    pocket = box(8.2, 3, 9.2, 4)
    b["ground"]["F.Cu"] = encode(box(1, 1, 5, 5).union(finger).union(pocket))
    monkeypatch.setattr("kicad_stitch.planner.grid_targets", lambda *args: iter([]))
    result = plan(b, replace(settings(), grid=True, grid_pitch_mm=8))
    assert any(c.rule == "coverage" and pocket.contains(Point(c.x, c.y)) for c in result.candidates)


def test_a_via_across_a_slot_does_not_serve_the_finger():
    b = board()
    finger = box(10, 8, 22, 9)
    main = box(1, 1, 10.5, 25).union(finger)
    b["ground"]["F.Cu"] = encode(main) + encode(box(15, 10, 22, 12))
    b["bridges"].append({"at": [18, 10.5], "layers": ["F.Cu", "B.Cu"]})
    b["existing_vias"] = [{"at": [18, 10.5], "net": "GND", "layers": ["F.Cu", "B.Cu"]}]
    result = plan(b, replace(settings(), fingers=True))
    assert any(c.rule == "finger" and c.x > 16 and 8 <= c.y <= 9 for c in result.candidates)


def test_floating_sliver_is_an_island_rather_than_a_connected_ground_finger():
    b = board()
    sliver = box(15, 8, 27, 9)
    b["ground"]["F.Cu"] = encode(box(1, 1, 10, 25)) + encode(sliver)
    result = plan(b, replace(settings(), islands=False, fingers=True))
    assert not any(c.rule == "finger" for c in result.candidates)
    assert not any(d["rule"] == "finger_detected" for d in result.diagnostics)
    assert any(d["rule"] == "island_unresolved" for d in result.diagnostics)


def test_return_vias_rotate_together_around_an_obstacle():
    b = board()
    b["nets"] += ["USB_P", "USB_N"]
    b["existing_vias"] = [{"at": [10, 10], "net": "USB_P", "layers": ["F.Cu", "B.Cu"]},
                          {"at": [10, 11], "net": "USB_N", "layers": ["F.Cu", "B.Cu"]}]
    b["obstacles"] = [{"kind": "keepout", "polygons": encode(box(9.7, 8.7, 10.3, 9.3))}]
    result = plan(b, replace(settings(), auto_pairs=True))
    assert len(result.candidates) == 2
    a, c = result.candidates
    assert a.x + c.x == pytest.approx(20)
    assert a.y + c.y == pytest.approx(21)
    assert any(v.displacement_mm > 0.01 for v in result.candidates)


def test_removed_floating_copper_is_not_reported_as_recovered():
    before = board()
    island = box(20, 20, 21, 21)
    before["ground"]["F.Cu"] = encode(box(1, 1, 10, 29)) + encode(island)
    after = {**before, "ground": {**before["ground"], "F.Cu": encode(box(1, 1, 10, 29))}}
    result = island_recovery(before, after, settings(), {"layer": "B.Cu", "at": [2, 2]})
    assert result["counts"] == {"removed_by_fill": 1}


def test_final_quality_is_measured_from_actual_vias_not_planned_targets():
    result = placement_quality(board(), Settings(), {"layer": "F.Cu", "at": [2, 2]})
    assert result["perimeter_gaps"]
    assert any(row["significant_gap"] for row in result["coverage"])


@pytest.mark.parametrize("kwargs", [{"grid_pattern": "random"}, {"zone_policy": "ignore"},
                                   {"perimeter_pitch_mm": 0}, {"grid_wavelength_divisor": 0}])
def test_invalid_adaptive_settings_are_rejected(kwargs):
    with pytest.raises(ValueError):
        Settings(**kwargs)
