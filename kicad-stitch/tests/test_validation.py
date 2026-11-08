from copy import deepcopy
from collections import Counter
import json

import pytest

from kicad_stitch.backend import check_via_dimensions, drc_issues, final_connectivity, partition_new_issues
from kicad_stitch.model import Candidate, Settings
from test_planner import board, encode
from shapely.geometry import box


def test_drc_comparison_catches_equal_count_but_different_violation():
    before = {"violations": [{"type": "clearance", "severity": "error", "items": [{"uuid": "old"}]}],
              "unconnected_items": []}
    after = deepcopy(before)
    after["violations"][0]["items"][0]["uuid"] = "new"
    assert sum((drc_issues(after) - drc_issues(before)).values()) == 1
    after = deepcopy(before)
    after["violations"] *= 2
    assert sum((drc_issues(after) - drc_issues(before)).values()) == 1


def test_final_validation_rejects_via_touching_only_one_ground_layer():
    b = board()
    b["ground"]["F.Cu"] = encode(box(1, 1, 5, 5))
    c = Candidate(20, 20, "grid", "test", ["F.Cu", "B.Cu"], "candidate")
    failures, _ = final_connectivity(b, [c], Settings())
    assert failures == ["candidate"]


def test_final_validation_rejects_via_joining_floating_ground_only():
    b = board()
    for layer in b["ground"]:
        b["ground"][layer] = encode(box(1, 1, 15, 25)) + encode(box(20, 20, 25, 25))
    b["bridges"].append({"at": [22, 22], "layers": ["F.Cu", "B.Cu"]})
    c = Candidate(22, 22, "grid", "test", ["F.Cu", "B.Cu"], "candidate")
    assert final_connectivity(b, [c], Settings())[0] == ["candidate"]


@pytest.mark.parametrize("diameter,drill", [(0.5, 0.3), (0.6, 0.4)])
def test_annular_global_minimum_does_not_preempt_native_drc(tmp_path, diameter, drill):
    project = tmp_path / "board.kicad_pro"
    project.write_text(json.dumps({"board": {"design_settings": {"rules": {
        "min_via_diameter": 0.5, "min_through_hole_diameter": 0.3, "min_via_annular_width": 0.16}}}}))
    check_via_dimensions(Settings(diameter_mm=diameter, drill_mm=drill), project)
    with pytest.raises(ValueError, match="via diameter"):
        check_via_dimensions(Settings(diameter_mm=0.4, drill_mm=0.3), project)
    with pytest.raises(ValueError, match="via drill"):
        check_via_dimensions(Settings(diameter_mm=0.5, drill_mm=0.2), project)


def _identity(kind="annular_width", severity="warning", uuids=("generated",), section="violations"):
    return (section, kind, severity, tuple((uid, 1, 2) for uid in uuids))


def test_non_hazard_warnings_are_advisory_and_hazards_always_block():
    isolated = _identity("isolated_copper", uuids=("existing-zone",))
    silk = _identity("silk_over_copper")
    hazards = [_identity("clearance"), _identity("shorting_items", uuids=("existing",)),
               _identity("unconnected_items", section="unconnected_items"),
               _identity("isolated_copper", severity="error")]
    issues = Counter({isolated: 2, silk: 1, **{h: 1 for h in hazards}})
    blocking, advisory = partition_new_issues(issues, ["generated"], Settings())
    assert advisory == Counter({isolated: 2, silk: 1})
    assert blocking == Counter({h: 1 for h in hazards})
    strict, none = partition_new_issues(issues, ["generated"], Settings(block_new_warnings=True))
    assert strict == issues and not none


def test_only_annular_warnings_on_generated_vias_are_advisory():
    identity = _identity
    accepted = identity()
    rejected = [identity(severity="error"), identity(kind="clearance"),
                identity(uuids=("existing",)), identity(uuids=("generated", "existing")),
                identity(uuids=())]
    issues = Counter({accepted: 3, **{issue: 1 for issue in rejected}})
    blocking, advisory = partition_new_issues(issues, ["generated"], Settings())
    assert advisory == Counter({accepted: 3})
    assert blocking == Counter({issue: 1 for issue in rejected})
    strict_blocking, strict_advisory = partition_new_issues(
        issues, ["generated"], Settings(allow_annular_width_warnings=False))
    assert strict_blocking == issues
    assert not strict_advisory
