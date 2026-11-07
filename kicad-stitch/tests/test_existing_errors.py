from collections import Counter
from pathlib import Path

from kicad_stitch.backend import describe_issues, drc_issues
from kicad_stitch.cli import build_summary
from kicad_stitch.model import Plan
from kicad_stitch.validation import preserves_connections, unchanged_unconnected_issues


def connections(groups):
    return {"nets": groups, "item_nets": {uid: net for net, components in groups.items()
                                          for component in components for uid in component}}


def issue(a, b, x=1):
    return {"type": "unconnected_items", "severity": "error", "description": "Missing connection on USB_D_P",
            "items": [{"uuid": a, "pos": {"x": x, "y": 2}}, {"uuid": b, "pos": {"x": 3, "y": 4}}]}


def test_different_ratsnest_endpoints_do_not_invent_new_disconnection():
    before = connections({"USB_D_P": [["track-a", "pad-a"], ["track-b", "pad-b"]]})
    baseline = {"unconnected_items": [issue("pad-a", "pad-b")]}
    final = {"unconnected_items": [issue("track-a", "pad-b", x=59.797)]}
    changed = drc_issues(final) - drc_issues(baseline)
    assert changed
    assert unchanged_unconnected_issues(changed, baseline, before, before) == changed


def test_new_split_blocks_even_if_another_repair_keeps_total_count_equal():
    before = connections({"USB": [["a", "b"], ["c"], ["d"]]})
    after = connections({"USB": [["a"], ["b"], ["c", "d"]]})
    baseline = {"unconnected_items": [issue("a", "c"), issue("c", "d")]}
    final = {"unconnected_items": [issue("a", "c"), issue("a", "b")]}
    changed = drc_issues(final) - drc_issues(baseline)
    assert not preserves_connections(before, after, "USB")
    assert not unchanged_unconnected_issues(changed, baseline, before, after)


def test_repair_merging_existing_components_is_allowed():
    before = connections({"USB": [["a", "b"], ["c"], ["d"]]})
    after = connections({"USB": [["a", "b", "c"], ["d"]]})
    baseline = {"unconnected_items": [issue("b", "c"), issue("c", "d")]}
    final = {"unconnected_items": [issue("a", "d")]}
    assert preserves_connections(before, after, "USB")
    changed = drc_issues(final) - drc_issues(baseline)
    assert unchanged_unconnected_issues(changed, baseline, before, after) == changed


def test_unknown_or_generated_endpoints_are_not_treated_as_existing():
    before = connections({"USB": [["a"], ["b"]]})
    after = connections({"USB": [["a"], ["b"], ["new-via"]]})
    baseline = {"unconnected_items": [issue("a", "b")]}
    for endpoint in ("new-via", "unknown-zone"):
        changed = drc_issues({"unconnected_items": [issue("a", endpoint)]})
        assert not unchanged_unconnected_issues(changed, baseline, before, after)


def test_removed_or_reassigned_existing_item_prevents_relaxation():
    before = connections({"USB": [["a", "b"], ["c"]]})
    baseline = {"unconnected_items": [issue("a", "c")]}
    changed = drc_issues({"unconnected_items": [issue("b", "c")]})
    for after in (connections({"USB": [["b"], ["c"]]}),
                  connections({"USB": [["b"], ["c"]], "OTHER": [["a"]]})):
        assert not unchanged_unconnected_issues(changed, baseline, before, after)


def test_no_baseline_disconnection_or_other_rule_is_never_waived():
    data = connections({"USB": [["a"], ["b"]]})
    changed = drc_issues({"unconnected_items": [issue("a", "b")]})
    assert not unchanged_unconnected_issues(changed, {}, data, data)
    other = issue("a", "b")
    other["type"] = "clearance"
    changed = drc_issues({"violations": [other]})
    assert not unchanged_unconnected_issues(changed, {"unconnected_items": [issue("a", "b")]}, data, data)


def test_descriptions_retain_issue_multiplicity_and_native_objects():
    selected = issue("a", "b")
    other = issue("c", "d")
    report = {"unconnected_items": [selected, selected, other]}
    identity = next(iter(drc_issues({"unconnected_items": [selected]})))
    result = describe_issues(report, Counter({identity: 1}))
    assert result == [{**selected, "section": "unconnected_items", "count": 1}]


def test_failed_cli_summary_explains_the_actual_blocker():
    native_issue = {**issue("existing-track", "existing-pad"), "section": "unconnected_items", "count": 1}
    identity = next(iter(drc_issues({"unconnected_items": [native_issue]})))
    result = Plan(validation={"status": "failed", "runtime": "native", "published_board": None,
        "blocking_issues": [{"identity": identity, "count": 1}], "blocking_issue_details": [native_issue],
        "advisory_issues": [{"count": 63}], "unconnected_candidate_uuids": [], "rejected_candidates": [],
        "stop_reason": "no_generated_via_implicated"})
    summary = build_summary(result, Path("report"))
    assert summary["blocking_issue_count"] == 1
    assert summary["advisory_issue_count"] == 63
    assert summary["unconnected_via_count"] == 0
    assert summary["blocking_issues"][0]["description"] == native_issue["description"]
    assert any("existing objects" in reason for reason in summary["failure_reasons"])


def test_summary_distinguishes_failed_ground_connections_and_limits_output():
    result = Plan(validation={"status": "failed", "runtime": "native", "published_board": None,
        "blocking_issues": [{"count": 8}], "blocking_issue_details": [{"description": str(i)} for i in range(8)],
        "advisory_issues": [], "unconnected_candidate_uuids": ["via"], "rejected_candidates": [],
        "stop_reason": "validation_limit"})
    summary = build_summary(result, Path("report"))
    assert len(summary["blocking_issues"]) == 5
    assert summary["additional_blocking_issues"] == 3
    assert any("ground connectivity" in reason for reason in summary["failure_reasons"])
