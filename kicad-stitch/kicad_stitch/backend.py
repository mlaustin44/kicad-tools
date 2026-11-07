"""File-based KiCad 10 adapter and validation transaction.

The planner never imports this module. A future IPC adapter can implement the same
snapshot/place/refill operations without changing the placement algorithms.
"""
from __future__ import annotations

from collections import Counter
from dataclasses import asdict
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile

from .geometry import Connectivity, decode
from .model import Settings
from .planner import plan
from .runtime import RuntimeDiscoveryError, discover_python, probe_python
from .validation import unchanged_unconnected_issues
from .quality import island_recovery, placement_quality


class BackendError(RuntimeError):
    pass


class KiCad:
    def __init__(self, runtime="auto", python=None, cli=None, timeout=600):
        if runtime not in {"auto", "native", "flatpak"}:
            raise ValueError(f"Unknown KiCad runtime: {runtime}")
        if runtime == "flatpak" and (python or cli):
            raise ValueError("--kicad-python and --kicad-cli select native executables; use --runtime native")
        self._auto_fallback = runtime == "auto" and not (python or cli)
        self._explicit_python = python
        self._version = None
        if runtime == "auto":
            runtime = "native" if python or cli or shutil.which("kicad-cli") else "flatpak"
        self.runtime = runtime
        self.timeout = timeout
        if runtime == "native":
            self.python = [python or sys.executable]
            self.cli = [cli or "kicad-cli"]
        else:
            self.python = ["flatpak", "run", "--command=python3", "org.kicad.KiCad"]
            self.cli = ["flatpak", "run", "--command=kicad-cli", "org.kicad.KiCad"]

    def command(self, args, payload=None, *, timeout=None):
        try:
            result = subprocess.run(args, input=json.dumps(payload) if payload is not None else None,
                                    text=True, capture_output=True, timeout=self.timeout if timeout is None else timeout)
        except (OSError, subprocess.TimeoutExpired) as exc:
            raise BackendError(f"Could not run KiCad: {exc}") from exc
        if result.returncode:
            raise BackendError(f"KiCad command failed ({result.returncode}): {result.stderr.strip() or result.stdout.strip()}")
        return result.stdout

    def check(self):
        if self._version is not None:
            return self._version
        try:
            return self._check_runtime()
        except (BackendError, RuntimeDiscoveryError) as native_error:
            if self.runtime == "native" and self._auto_fallback and shutil.which("flatpak"):
                self.runtime = "flatpak"
                self.python = ["flatpak", "run", "--command=python3", "org.kicad.KiCad"]
                self.cli = ["flatpak", "run", "--command=kicad-cli", "org.kicad.KiCad"]
                try:
                    return self._check_runtime()
                except (BackendError, RuntimeDiscoveryError) as flatpak_error:
                    raise BackendError(f"Native KiCad unavailable: {native_error}\n"
                                       f"Flatpak KiCad unavailable: {flatpak_error}") from flatpak_error
            raise BackendError(str(native_error)) from native_error

    def _check_runtime(self):
        version = self.command([*self.cli, "version"]).strip()
        if not version.startswith("10."):
            raise BackendError(f"Requires KiCad 10.x, found {version}")
        run_probe = lambda args: self.command(args, timeout=min(self.timeout, 15))
        if self.runtime == "native":
            self.python = discover_python(self.cli[0], version, run_probe, explicit=self._explicit_python)
        else:
            probe_python(self.python, version, run_probe)
        self._version = version
        return version

    def worker(self, action, board, **kwargs):
        self.check()
        output = self.command([*self.python, str(Path(__file__).with_name("worker.py"))],
                              {"action": action, "board": str(board), **kwargs})
        try:
            return json.loads(output)
        except json.JSONDecodeError as exc:
            raise BackendError(f"Invalid KiCad worker response: {output[:500]}") from exc

    def snapshot(self, board, net):
        return self.worker("snapshot", board, net=net)

    def drc(self, board, output):
        self.check()
        self.command([*self.cli, "pcb", "drc", "--format", "json", "--severity-all",
                      "--all-track-errors", "--units", "mm", "--refill-zones", "--save-board",
                      "--output", str(output), str(board)])
        try:
            report = json.loads(output.read_text())
        except (OSError, json.JSONDecodeError) as exc:
            raise BackendError(f"KiCad did not produce a valid DRC report: {exc}") from exc
        if not all(key in report for key in ("violations", "unconnected_items")):
            raise BackendError("Unrecognized KiCad DRC report schema")
        if report.get("coordinate_units") != "mm":
            raise BackendError("KiCad DRC returned unexpected coordinate units")
        return report


def drc_issues(report):
    """Compare issue identities and multiplicities, not just total counts.

    Locations are retained: two same-type violations against the same objects at
    distinct locations must not mask one another. KiCad reports in millimetres.
    """
    records = []
    for section in ("violations", "unconnected_items", "schematic_parity"):
        for issue in report.get(section, []):
            # Explicitly excluded project violations keep their existing semantics.
            if issue.get("severity") == "exclusion":
                continue
            items = tuple(sorted((str(item.get("uuid", "")),
                                  round(item.get("pos", {}).get("x", 0), 4),
                                  round(item.get("pos", {}).get("y", 0), 4))
                                 for item in issue.get("items", [])))
            records.append((section, issue.get("type"), issue.get("severity"), items))
    return Counter(records)


def describe_issues(report, issues):
    """Attach native descriptions/items to a selected issue Counter."""
    records, seen = [], set()
    for section in ("violations", "unconnected_items", "schematic_parity"):
        for issue in report.get(section, []):
            for identity in drc_issues({section: [issue]}):
                if identity in issues and identity not in seen:
                    records.append({**issue, "section": section, "count": issues[identity]})
                    seen.add(identity)
    return records


def copy_project(source, directory, name=None):
    directory.mkdir(parents=True, exist_ok=True)
    target = directory / (name or source.name)
    shutil.copy2(source, target)
    for suffix in (".kicad_pro", ".kicad_dru"):
        sibling = source.with_suffix(suffix)
        if sibling.exists():
            shutil.copy2(sibling, target.with_suffix(suffix))
    return target


def fingerprint(source):
    return {str(path): hashlib.sha256(path.read_bytes()).hexdigest()
            for path in (source, source.with_suffix(".kicad_pro"), source.with_suffix(".kicad_dru"))
            if path.exists()}


def check_via_dimensions(settings, project):
    data = json.loads(project.read_text())
    rules = data.get("board", {}).get("design_settings", {}).get("rules", {})
    # Annular width must be evaluated by native DRC: its severity may be a
    # warning/ignored and effective custom rules may differ from the global min.
    checks = [(settings.diameter_mm, rules.get("min_via_diameter", 0), "via diameter"),
              (settings.drill_mm, rules.get("min_through_hole_diameter", 0), "via drill")]
    for actual, minimum, name in checks:
        if actual + 1e-9 < minimum:
            raise ValueError(f"Configured {name} {actual} mm is below project minimum {minimum} mm")


def partition_new_issues(new, candidate_ids, settings):
    """Keep only annular-width warnings on generated vias as advisories.

    Never waive annular errors, violations on pre-existing items, or other rule
    types. Raw KiCad reports and the complete new-issue list remain unchanged.
    """
    blocking, advisory = Counter(), Counter()
    candidate_ids = set(candidate_ids)
    for identity, count in new.items():
        section, kind, severity, items = identity
        if (settings.allow_annular_width_warnings and section == "violations"
                and kind == "annular_width" and severity == "warning" and items
                and all(item[0] in candidate_ids for item in items)):
            advisory[identity] = count
        else:
            blocking[identity] = count
    return blocking, advisory


def compare_native_issues(backend, original, proposed, baseline_drc, final_drc):
    """Compare native issues, including changed representatives of old airwires."""
    new = drc_issues(final_drc) - drc_issues(baseline_drc)
    changed_edges = [key for key in new if key[0] == "unconnected_items"]
    unchanged = Counter()
    if changed_edges:
        endpoints = sorted({item[0] for key in changed_edges for item in key[3]})
        before = backend.worker("connectivity", original, item_uuids=endpoints)
        after = backend.worker("connectivity", proposed, nets=list(before["nets"]))
        unchanged = unchanged_unconnected_issues(new, baseline_drc, before, after)
    return new, unchanged


def final_connectivity(snapshot, candidates, settings, reference=None):
    """Verify proposed vias against actual, normally refilled copper.

    The snapshot's ground polygons exclude via pads, so a via cannot prove its own
    landing. The center must land in ground on at least two layers and reach the
    selected reference component after the real island-removal settings apply.
    """
    ground = {layer: decode(polys) for layer, polys in snapshot["ground"].items()}
    graph = Connectivity(ground, snapshot["bridges"], settings.anchors_mm)
    from shapely.geometry import Point
    if reference:
        nodes = graph.touch(Point(reference["at"]), [reference["layer"]])
        if not nodes:
            raise BackendError("Reference ground disappeared during final fill")
        graph.root = nodes[0]
    failures = []
    for candidate in candidates:
        at = Point(candidate.x, candidate.y)
        touched = graph.touch(at)
        layers = {graph.regions[i][0] for i in touched}
        if len(layers) < 2 or not any(graph.rooted(i) for i in touched):
            failures.append(candidate.uuid)
        else:
            candidate.layers = sorted(layers)
    return failures, [{"layer": graph.regions[i][0],
                       "area_mm2": graph.regions[i][1].area,
                       "at": list(graph.regions[i][1].representative_point().coords)[0]}
                      for i in graph.missing()]


def revalidate_export(source, content, settings, candidates, reference, backend, audit):
    """Refill/check existing reviewed vias under the original project basename.

    Never plan, add or remove a via. Preserve native artifacts for review even
    when original-name rules reject the export. Source files are read only.
    """
    version = backend.check()
    scratch_parent = Path.cwd() if backend.runtime == "flatpak" else None
    with tempfile.TemporaryDirectory(prefix=".kicad-stitch-", dir=scratch_parent) as tmp:
        root = Path(tmp)
        original = copy_project(source, root / "baseline")
        backend.worker("normalize", original, output=str(original))
        before = backend.drc(original, audit / "baseline-drc.json")
        proposed = copy_project(original, root / "proposed")
        proposed.write_bytes(content)
        backend.worker("normalize", proposed, output=str(proposed))
        after = backend.drc(proposed, audit / "final-drc.json")
        new, unchanged = compare_native_issues(backend, original, proposed, before, after)
        blocking, advisory = partition_new_issues(new - unchanged, [c.uuid for c in candidates], settings)
        snapshot = backend.snapshot(proposed, settings.net)
        failures, missing = final_connectivity(snapshot, candidates, settings, reference)
        # Confirm that native round-tripping kept all reviewed via identities,
        # nets and positions, rather than merely checking copper at those points.
        vias = {v["uuid"]: v for v in snapshot["existing_vias"]}
        changed_vias = [c.uuid for c in candidates if c.uuid not in vias
                        or vias[c.uuid]["net"] != settings.net
                        or abs(vias[c.uuid]["at"][0] - c.x) > 1e-5
                        or abs(vias[c.uuid]["at"][1] - c.y) > 1e-5]
        status = "failed" if blocking or failures or changed_vias else (
            "verified_with_warnings" if advisory else "verified")
        saved = copy_project(proposed, audit / "board")
        installed = proposed.read_bytes()
        records = lambda issues: [{"identity": identity, "count": count} for identity, count in issues.items()]
        verification = {"status": status, "source_board": str(source), "validated_basename": source.name,
                        "source_sha256": fingerprint(source),
                        "review_board_sha256": hashlib.sha256(content).hexdigest(),
                        "kicad_version": version, "runtime": backend.runtime,
                        "python_command": backend.python, "cli_command": backend.cli,
                        "via_count": len(candidates), "candidate_uuids": [c.uuid for c in candidates],
                        "changed_candidate_uuids": changed_vias,
                        "new_issues": records(new), "blocking_issues": records(blocking),
                        "blocking_issue_details": describe_issues(after, blocking),
                        "advisory_issues": records(advisory),
                        "unchanged_connectivity_issues": describe_issues(after, unchanged),
                        "unconnected_candidate_uuids": failures, "remaining_ground_components": missing,
                        "proposed_board": str(saved), "validated_sha256": {
                            str(saved.with_suffix(Path(path).suffix)): value
                            for path, value in fingerprint(proposed).items()}}
        report = audit / "validation.json"
        report.write_text(json.dumps(verification, indent=2) + "\n")
        if status == "failed":
            details = "; ".join(issue.get("description", issue.get("type", "DRC violation"))
                                for issue in verification["blocking_issue_details"][:3])
            if failures or changed_vias:
                details += f"; {len(set(failures + changed_vias))} reviewed via(s) failed connectivity/identity checks"
            raise BackendError(f"Original-name validation failed; nothing was applied: {details.strip('; ')}. See {report}")
        return installed, {"status": status, "report": str(report), "via_count": len(candidates)}


def run(source: Path, settings: Settings, backend: KiCad, *, output: Path | None = None):
    """Plan and validate in scratch space; publish only if requested and verified.

    Returns (Plan, final snapshot, baseline DRC, final DRC). Even a preview is validated
    by native refill/DRC. New blocking violations prevent publication; permitted
    annular-width warnings remain visible in both native and placement reports.
    """
    source = source.resolve()
    if source.suffix != ".kicad_pcb" or not source.is_file():
        raise ValueError("Input must be an existing .kicad_pcb file")
    project = source.with_suffix(".kicad_pro")
    if not project.is_file():
        raise ValueError("A sibling .kicad_pro is required so project design rules are preserved")
    check_via_dimensions(settings, project)
    hashes = fingerprint(source)
    if output is not None:
        output = output.resolve()
        if output.suffix != ".kicad_pcb" or output == source or output.exists():
            raise ValueError("Output must be a new .kicad_pcb path distinct from the source")
        if any(output.with_suffix(s).exists() for s in (".kicad_pro", ".kicad_dru")):
            raise ValueError("Output project/rules already exist; choose a new output basename")
    version = backend.check()
    # Flatpak has a private /tmp; use a visible working-directory scratch path.
    scratch_parent = Path.cwd() if backend.runtime == "flatpak" else None
    with tempfile.TemporaryDirectory(prefix=".kicad-stitch-", dir=scratch_parent) as tmp:
        root = Path(tmp)
        original = copy_project(source, root / "baseline")
        backend.worker("normalize", original, output=str(original))
        baseline_drc = backend.drc(original, root / "baseline-drc.json")
        exploratory = copy_project(original, root / "exploratory")
        backend.worker("retain", exploratory, net=settings.net, output=str(exploratory))
        backend.drc(exploratory, root / "exploratory-drc.json")
        snapshot = backend.snapshot(exploratory, settings.net)
        result = plan(snapshot, settings)
        rejected = []
        stop_reason = None
        for iteration in range(5):
            proposed = copy_project(original, root / "proposed", output.name if output else None)
            ids = backend.worker("place", proposed, net=settings.net, output=str(proposed),
                                 candidates=[asdict(c) for c in result.candidates],
                                 diameter_mm=settings.diameter_mm, drill_mm=settings.drill_mm)["uuids"]
            for candidate, uid in zip(result.candidates, ids, strict=True):
                candidate.uuid = uid
            final_drc = backend.drc(proposed, root / "final-drc.json")
            new, unchanged = compare_native_issues(backend, original, proposed, baseline_drc, final_drc)
            blocking, advisory = partition_new_issues(new - unchanged, ids, settings)
            final_snapshot = backend.snapshot(proposed, settings.net)
            failures, missing = final_connectivity(final_snapshot, result.candidates, settings,
                                                  result.parameters["reference_ground"])
            if not blocking and not failures:
                break
            implicated = set(failures)
            for identity in blocking:
                implicated.update(item[0] for item in identity[3] if item[0] in ids)
            if not implicated or iteration == 4:
                stop_reason = "no_generated_via_implicated" if not implicated else "validation_limit"
                break
            # Preserve symmetry: discard the signal's return group if either side
            # fails an effective custom rule. No one-sided return gets published.
            transition_groups = {c.reason for c in result.candidates if c.uuid in implicated and c.rule == "transition"}
            removing = [c for c in result.candidates if c.uuid in implicated
                        or (c.rule == "transition" and c.reason in transition_groups)]
            for candidate in removing:
                rejected.append({**asdict(candidate), "rejection": "native_drc_or_ground_connectivity"})
            result.candidates = [c for c in result.candidates if c not in removing]
        if rejected:
            result.diagnostics.append({"rule": "native_rejections", "count": len(rejected),
                "message": "Candidates removed after native DRC/connectivity; resulting coverage may have gaps"})
        if advisory:
            result.diagnostics.append({"rule": "annular_width_warning", "count": sum(advisory.values()),
                "message": "Native KiCad annular-width warnings retained on generated vias; project rules are unchanged",
                "radial_width_mm": (settings.diameter_mm - settings.drill_mm) / 2,
                "diameter_difference_mm": settings.diameter_mm - settings.drill_mm})
        if unchanged:
            result.diagnostics.append({"rule": "existing_unconnected_items", "count": sum(unchanged.values()),
                "message": "Changed ratsnest endpoints describe existing disconnections; native connectivity is preserved"})
        status = "failed" if blocking or failures else ("verified_with_warnings" if advisory else "verified")
        issue_records = lambda issues: [{"identity": identity, "count": count} for identity, count in issues.items()]
        result.validation = {"status": status,
                             "source_board": str(source),
                             "validated_basename": proposed.name,
                             "kicad_version": version, "runtime": backend.runtime,
                             "python_command": backend.python,
                             "cli_command": backend.cli,
                             "source_sha256": hashes,
                             "baseline_sha256": {
                                 str(source.with_suffix(Path(path).suffix)): value
                                 for path, value in fingerprint(original).items()},
                             "baseline_issue_count": sum(drc_issues(baseline_drc).values()),
                             "final_issue_count": sum(drc_issues(final_drc).values()),
                             "new_issues": issue_records(new),
                             "blocking_issues": issue_records(blocking),
                             "blocking_issue_details": describe_issues(final_drc, blocking),
                             "advisory_issues": issue_records(advisory),
                             "unchanged_connectivity_issues": describe_issues(final_drc, unchanged),
                             "unconnected_candidate_uuids": failures,
                             "rejected_candidates": rejected,
                             "validation_iterations": iteration + 1,
                             "stop_reason": stop_reason,
                             "remaining_ground_components": missing,
                             "published_board": None}
        result.validation["island_recovery"] = island_recovery(snapshot, final_snapshot, settings,
                                                               result.parameters["reference_ground"])
        result.validation["placement_quality"] = placement_quality(final_snapshot, settings,
                                                                    result.parameters["reference_ground"])
        result.validation["placement_quality"]["relocated_vias"] = sum(c.displacement_mm > 0.01 for c in result.candidates)
        if fingerprint(source) != hashes:
            raise BackendError("Source board or project changed during planning; run again")
        if output is not None and result.validation["status"] in {"verified", "verified_with_warnings"}:
            output.parent.mkdir(parents=True, exist_ok=True)
            published = []
            try:
                # Exclusive creation prevents a racing invocation overwriting files.
                # Board is published last, after its project and custom rules.
                for suffix in (".kicad_pro", ".kicad_dru", ".kicad_pcb"):
                    src = proposed.with_suffix(suffix)
                    if src.exists():
                        dst = output.with_suffix(suffix)
                        with dst.open("xb") as stream:
                            published.append(dst)
                            stream.write(src.read_bytes())
            except BaseException:
                for path in published:
                    path.unlink()
                raise
            result.validation["published_board"] = str(output)
            # Bind the report to native-validated scratch bytes, not to a later
            # read of an export that another program could already have edited.
            result.validation["published_sha256"] = {
                str(output.with_suffix(Path(path).suffix)): value
                for path, value in fingerprint(proposed).items()}
        return result, final_snapshot, baseline_drc, final_drc
