"""Thin CLI frontend; the planner and transaction API are independently usable."""
from __future__ import annotations

import argparse
from collections import Counter
import json
from pathlib import Path
import shlex
import sys

from . import __version__
from .backend import BackendError, KiCad, run
from .model import load_settings
from .preview import svg
from .workflow import apply_review, ensure_closed, restore_backup


def parser():
    p = argparse.ArgumentParser(description="Plan and verify ground stitching vias on a KiCad 10 board",
        epilog="Review/apply: kicad-stitch apply REPORT_DIR. Undo: kicad-stitch restore BACKUP_DIR.")
    p.add_argument("board", type=Path)
    p.add_argument("--config", type=Path, help="TOML placement settings")
    output = p.add_mutually_exclusive_group()
    output.add_argument("--output", type=Path, help="Export a separate board/project (default: REPORT_DIR/board/)")
    output.add_argument("--in-place", action="store_true", help="Back up and replace the source PCB after validation")
    p.add_argument("--report-dir", type=Path, help="New directory for JSON, SVG and DRC reports")
    p.add_argument("--runtime", choices=["auto", "native", "flatpak"], default="auto")
    p.add_argument("--kicad-python", help="Explicit Python with pcbnew (native runtime; otherwise autodetected)")
    p.add_argument("--kicad-cli", help="kicad-cli executable (native runtime)")
    p.add_argument("--version", action="version", version=__version__)
    return p


def build_summary(result, report):
    validation = result.validation
    blocking = validation["blocking_issues"]
    failures = validation["unconnected_candidate_uuids"]
    count = sum(issue["count"] for issue in blocking)
    reasons = []
    if count:
        reasons.append(f"KiCad reported {count} new blocking DRC issue(s).")
    if failures:
        reasons.append(f"{len(failures)} proposed via(s) failed ground connectivity verification.")
    if validation.get("stop_reason") == "no_generated_via_implicated":
        reasons.append("Blocking issues reference existing objects or the board; no generated via was identified for removal.")
    elif validation.get("stop_reason") == "validation_limit":
        reasons.append("Reached the native validation iteration limit.")
    details = validation.get("blocking_issue_details", [])
    return {"status": validation["status"], "vias": len(result.candidates),
            "runtime": validation["runtime"],
            "by_rule": dict(Counter(c.rule for c in result.candidates)), "report": str(report),
            "output": validation["published_board"],
            "diagnostics": dict(Counter(d["rule"] for d in result.diagnostics)),
            "rejected_vias": len(validation["rejected_candidates"]),
            "advisory_issue_count": sum(i["count"] for i in validation["advisory_issues"]),
            "advisory_issues": validation.get("advisory_issue_details", [])[:5],
            "unchanged_connectivity_issue_count": sum(i["count"] for i in validation.get("unchanged_connectivity_issues", [])),
            "blocking_issue_count": count,
            "blocking_issues": details[:5],
            "additional_blocking_issues": sum(issue.get("count", 1) for issue in details[5:]),
            "unconnected_via_count": len(failures),
            "failure_reasons": reasons,
            "placement_quality": {
                "relocated_vias": validation.get("placement_quality", {}).get("relocated_vias", 0),
                "perimeter_gap_count": len(validation.get("placement_quality", {}).get("perimeter_gaps", [])),
                "coverage_gap_layers": [row["layer"] for row in validation.get("placement_quality", {}).get("coverage", [])
                                        if row["significant_gap"]],
                "island_states": validation.get("island_recovery", {}).get("counts", {})}}


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    if argv and argv[0] in {"apply", "restore"}:
        return workflow_command(argv)
    args = parser().parse_args(argv)
    created_report = False
    try:
        settings = load_settings(args.config)
        report = (args.report_dir or args.board.with_name(args.board.stem + ".stitch-report")).resolve()
        if report.exists():
            raise ValueError("Report directory already exists; choose a new --report-dir")
        if args.in_place:
            ensure_closed(args.board.resolve())
        backend = KiCad(args.runtime, args.kicad_python, args.kicad_cli)
        report.mkdir(parents=True, exist_ok=False)
        created_report = True
        output = args.output or report / "board" / args.board.resolve().name
        print("Planning and running KiCad refill/DRC on scratch copies…", file=sys.stderr)
        result, snapshot, before, after = run(args.board, settings, backend, output=output)
        for name, data in (("plan.json", result.to_dict()), ("baseline-drc.json", before), ("final-drc.json", after)):
            (report / name).write_text(json.dumps(data, indent=2) + "\n")
        (report / "preview.svg").write_text(svg(snapshot, result, settings))
        summary = build_summary(result, report)
        verified = result.validation["status"] in {"verified", "verified_with_warnings"}
        if verified:
            if args.in_place:
                summary["application"] = apply_review(report)
            else:
                summary["apply_command"] = shlex.join(["kicad-stitch", "apply", str(report)])
        elif result.validation["published_board"]:
            summary["inspect"] = ("Proposed board saved for inspection; open it in KiCad and compare "
                                  "final-drc.json with baseline-drc.json")
            summary["apply_command"] = shlex.join(["kicad-stitch", "apply", "--force", str(report)])
        print(json.dumps(summary, indent=2))
        return 0 if result.validation["status"] in {"verified", "verified_with_warnings"} else 2
    except (BackendError, ValueError, TypeError, OSError) as exc:
        if created_report:
            try:
                report.rmdir()  # Remove only an empty reservation, never review artifacts.
            except OSError:
                pass
        print(f"error: {exc}", file=sys.stderr)
        return 1


def workflow_command(argv):
    command = argv[0]
    p = argparse.ArgumentParser(prog=f"kicad-stitch {command}", description=(
        "Apply an unchanged verified review to its original board, saving a backup" if command == "apply" else
        "Restore a backed-up PCB, preserving the current board in another backup"))
    p.add_argument("path", type=Path, help="Review directory/plan.json" if command == "apply" else "Backup directory/backup.json")
    if command == "restore":
        p.add_argument("--force", action="store_true", help="Restore despite later edits, backing up current files first")
    else:
        p.add_argument("--force", action="store_true",
                       help="Apply a review that failed native validation (after inspecting it)")
        p.add_argument("--runtime", choices=["auto", "native", "flatpak"], default="auto",
                       help="KiCad runtime for revalidating a renamed export")
        p.add_argument("--kicad-python", help="Explicit native KiCad Python interpreter")
        p.add_argument("--kicad-cli", help="Explicit native kicad-cli executable")
    args = p.parse_args(argv[1:])
    try:
        if command == "apply":
            print("Applying review; renamed exports receive native validation under the original board name…", file=sys.stderr)
            result = apply_review(args.path, KiCad(args.runtime, args.kicad_python, args.kicad_cli),
                                  force=args.force)
        else:
            result = restore_backup(args.path, force=args.force)
        print(json.dumps(result, indent=2))
        return 0
    except (BackendError, ValueError, OSError, KeyError, TypeError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
