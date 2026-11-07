"""Thin CLI frontend; the planner and transaction API are independently usable."""
from __future__ import annotations

import argparse
from collections import Counter
import json
from pathlib import Path
import sys

from . import __version__
from .backend import BackendError, KiCad, run
from .model import load_settings
from .preview import svg


def parser():
    p = argparse.ArgumentParser(description="Plan and verify ground stitching vias on a KiCad 10 board")
    p.add_argument("board", type=Path)
    p.add_argument("--config", type=Path, help="TOML placement settings")
    p.add_argument("--output", type=Path, help="Publish a new verified board and project at this path")
    p.add_argument("--report-dir", type=Path, help="New directory for JSON, SVG and DRC reports")
    p.add_argument("--runtime", choices=["auto", "native", "flatpak"], default="auto")
    p.add_argument("--kicad-python", help="Explicit Python with pcbnew (native runtime; otherwise autodetected)")
    p.add_argument("--kicad-cli", help="kicad-cli executable (native runtime)")
    p.add_argument("--version", action="version", version=__version__)
    return p


def main(argv=None):
    args = parser().parse_args(argv)
    try:
        settings = load_settings(args.config)
        report = (args.report_dir or args.board.with_name(args.board.stem + ".stitch-report")).resolve()
        if report.exists():
            raise ValueError("Report directory already exists; choose a new --report-dir")
        backend = KiCad(args.runtime, args.kicad_python, args.kicad_cli)
        print("Planning and running KiCad refill/DRC on scratch copies…", file=sys.stderr)
        result, snapshot, before, after = run(args.board, settings, backend, output=args.output)
        report.mkdir(parents=True, exist_ok=False)
        for name, data in (("plan.json", result.to_dict()), ("baseline-drc.json", before), ("final-drc.json", after)):
            (report / name).write_text(json.dumps(data, indent=2) + "\n")
        (report / "preview.svg").write_text(svg(snapshot, result, settings))
        counts = Counter(c.rule for c in result.candidates)
        summary = {"status": result.validation["status"], "vias": len(result.candidates),
                   "runtime": result.validation["runtime"],
                   "by_rule": dict(counts), "report": str(report),
                   "output": result.validation["published_board"],
                   "diagnostics": dict(Counter(d["rule"] for d in result.diagnostics)),
                   "rejected_vias": len(result.validation["rejected_candidates"]),
                   "advisory_issue_count": sum(i["count"] for i in result.validation["advisory_issues"])}
        print(json.dumps(summary, indent=2))
        return 0 if result.validation["status"] in {"verified", "verified_with_warnings"} else 2
    except (BackendError, ValueError, TypeError, OSError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
