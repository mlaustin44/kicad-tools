from copy import deepcopy

from kicad_stitch.backend import drc_issues, final_connectivity
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
