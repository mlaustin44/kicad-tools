"""Pure planning engine: no filesystem, KiCad process, or CLI dependencies."""
from __future__ import annotations

from collections import defaultdict
from dataclasses import replace
from fnmatch import fnmatchcase
import math

from shapely.geometry import GeometryCollection, LineString, Point, box
from shapely.ops import unary_union

from .geometry import Connectivity, decode, lattice, polygons, sample_line
from .model import Candidate, Plan, Settings, Signal


class PointIndex:
    def __init__(self, cell):
        self.cell = cell
        self.bins = defaultdict(list)

    def add(self, point, layers):
        self.bins[self.key(point)].append((point, set(layers)))

    def key(self, point):
        return (math.floor(point.x / self.cell), math.floor(point.y / self.cell))

    def nearby(self, point, distance):
        x, y = self.key(point)
        n = math.ceil(distance / self.cell)
        for ix in range(x - n, x + n + 1):
            for iy in range(y - n, y + n + 1):
                for p, layers in self.bins.get((ix, iy), ()):
                    if point.distance(p) < distance - 1e-7:
                        yield p, layers


def detect_pairs(nets):
    """KiCad suffix conventions are hints, never proof of electrical intent."""
    names = set(nets)
    pairs = []
    for net in sorted(names):
        for positive, negative in (("_P", "_N"), ("+", "-"), ("_DP", "_DM")):
            if net.endswith(positive) and net[:-len(positive)] + negative in names:
                pairs.append((net, net[:-len(positive)] + negative))
    return pairs


def choose_pitch(settings, area, min_spacing):
    # Geometric fallback targets roughly 100 cells, bounded for ordinary boards.
    geometric = max(min_spacing, min(10.0, max(2.0, math.sqrt(area) / 10)))
    frequencies = [f for f in (settings.max_frequency_hz,
                               0.5e9 / settings.rise_time_ns if settings.rise_time_ns else None) if f]
    electrical = (299792458000 / (max(frequencies) * math.sqrt(settings.epsilon_r)
                                  * settings.wavelength_divisor)) if frequencies else None
    desired = settings.pitch_mm if settings.pitch_mm is not None else geometric
    if electrical:
        desired = min(desired, electrical)
    if desired < min_spacing:
        raise ValueError(f"Requested pitch {desired:.3f} mm is below legal via spacing {min_spacing:.3f} mm")
    return desired, {"pitch_mm": desired, "geometric_pitch_mm": geometric,
                     "electrical_pitch_limit_mm": electrical,
                     "frequency_hz": max(frequencies) if frequencies else None,
                     "epsilon_r_assumption": settings.epsilon_r,
                     "rise_time_bandwidth_coefficient": 0.5,
                     "spacing_basis": "electrical_and_geometry" if electrical else "geometry_only"}


class Planner:
    def __init__(self, snapshot: dict, settings: Settings):
        self.data, self.s = snapshot, settings
        self.result = Plan()
        self.outline = decode(snapshot["outline"])
        self.ground = {l: decode(g) for l, g in snapshot["ground"].items()}
        self.graph = Connectivity(self.ground, snapshot["bridges"], settings.anchors_mm)
        self.radius = settings.diameter_mm / 2
        rules = snapshot.get("rules", {})
        clearance = max(settings.clearance_mm, rules.get("m_MinClearance", 0))
        self.spacing = max(settings.min_spacing_mm, settings.diameter_mm + clearance,
                           settings.drill_mm + rules.get("m_HoleToHoleMin", 0))
        self.pitch, self.result.parameters = choose_pitch(settings, self.outline.area, self.spacing)
        self.result.parameters.update({"min_spacing_mm": self.spacing,
                                       "root_selection": "explicit_anchor" if settings.anchors_mm else "largest_connected_copper_area",
                                       "settings": settings.to_dict()})
        root_layer, root_region = self.graph.regions[self.graph.root]
        self.result.parameters["reference_ground"] = {"layer": root_layer,
            "at": list(root_region.representative_point().coords)[0]}
        if self.result.parameters["spacing_basis"] == "geometry_only":
            self.note("spacing", "Frequency and rise time absent: pitch is a geometric density heuristic, not an EMI limit")
        self.note("root", "Ground connectivity is referenced to " + self.result.parameters["root_selection"])
        # Through vias must clear obstacles on every layer, including non-reference layers.
        obstacles = []
        for item in snapshot["obstacles"]:
            margin = self.radius + clearance + 0.01
            if item["kind"] == "hole":
                margin = max(self.radius + rules.get("m_HoleClearance", clearance),
                             settings.drill_mm / 2 + rules.get("m_HoleToHoleMin", clearance)) + 0.01
            elif item["kind"] == "keepout":
                margin = self.radius + 0.01
            obstacles.append(decode(item["polygons"]).buffer(margin))
        for fp in snapshot["footprints"]:
            obstacles.append(decode(fp["polygons"]).buffer(self.radius + settings.component_clearance_mm))
        obstacles.extend(box(*bounds).buffer(self.radius) for bounds in settings.exclusions_mm)
        edge = max(settings.edge_clearance_mm, rules.get("m_CopperEdgeClearance", 0))
        safe = self.outline.buffer(-edge - self.radius - 0.01).difference(unary_union(obstacles))
        self.eroded = {l: g.buffer(-self.radius - 0.01) for l, g in self.ground.items()}
        landing = []
        layers = list(self.eroded)
        for i, layer in enumerate(layers):
            for other in layers[i + 1:]:
                landing.append(self.eroded[layer].intersection(self.eroded[other]))
        self.legal = safe.intersection(unary_union(landing))
        self.spacing_points = PointIndex(max(self.spacing, self.pitch))
        self.coverage = PointIndex(max(self.spacing, self.pitch))
        for via in snapshot["existing_vias"]:
            point = Point(via["at"])
            self.spacing_points.add(point, via["layers"])
        for bridge in snapshot["bridges"]:
            point = Point(bridge["at"])
            touched = self.graph.touch(point, bridge["layers"])
            layers = {self.graph.regions[i][0] for i in touched}
            if len(layers) >= 2 and any(self.graph.rooted(i) for i in touched):
                self.coverage.add(point, layers)
        self.samples = 0
        self.eroded_regions = [p.buffer(-self.radius - 0.01) for _, p in self.graph.regions]
        self.signals = self.resolve_signals()
        # Protect the chosen signal-to-ground-via spacing from *all* passes.
        corridors = []
        for signal, nets in self.signals:
            for track in snapshot["tracks"]:
                if track["net"] in nets:
                    corridors.append(LineString(track["points"]).buffer(signal.offset_mm - 0.005))
            for copper in snapshot.get("signal_copper", []):
                if copper["net"] in nets:
                    corridors.append(decode(copper["polygons"]).buffer(signal.offset_mm - 0.005))
        self.legal = self.legal.difference(unary_union(corridors))

    def note(self, rule, message, **details):
        self.result.diagnostics.append({"rule": rule, "message": message, **details})

    def resolve_signals(self):
        signals = []
        for signal in self.s.signals:
            nets = {n for n in self.data["nets"] if any(fnmatchcase(n, pat) for pat in signal.nets)}
            for pattern in signal.nets:
                if not any(fnmatchcase(n, pattern) for n in self.data["nets"]):
                    raise ValueError(f"Signal {signal.name}: no net matches {pattern}")
            for pattern in signal.references:
                fps = [fp for fp in self.data["footprints"] if fnmatchcase(fp["reference"], pattern)]
                if not fps:
                    raise ValueError(f"Signal {signal.name}: no component matches {pattern}")
                for fp in fps:
                    nets.update(fp.get("nets", []))
            nets.discard(self.s.net)
            if not nets:
                raise ValueError(f"Signal {signal.name}: selection has no non-ground nets")
            if signal.differential and len(nets) != 2:
                raise ValueError(f"Signal {signal.name}: differential selection must resolve to exactly two nets")
            signals.append((signal, nets))
        if self.s.auto_pairs:
            for pair in detect_pairs(self.data["nets"]):
                self.note("pair_detection", "Detected pair by net-name convention; verify electrical intent", nets=list(pair))
                if not any(set(pair).issubset(nets) for _, nets in signals):
                    signals.append((Signal(name="/".join(pair), nets=pair,
                                           mode="fence" if self.s.pair_fences else "transitions",
                                           offset_mm=self.s.signal_offset_mm), set(pair)))
        validated = []
        for signal, nets in signals:
            pitch = signal.pitch_mm or self.pitch
            bound = self.result.parameters["electrical_pitch_limit_mm"]
            if bound and pitch > bound:
                self.note("signal_pitch", "Signal pitch reduced to board electrical bound", signal=signal.name,
                          requested_pitch_mm=pitch, effective_pitch_mm=bound)
                pitch = bound
            if pitch < self.spacing:
                raise ValueError(f"Signal {signal.name}: pitch is smaller than legal via spacing")
            validated.append((replace(signal, pitch_mm=pitch), nets))
        return validated

    def tick(self):
        self.samples += 1
        if self.samples > self.s.max_samples:
            raise ValueError("Planner exceeded max_samples; increase pitch or raise the explicit sample budget")

    def layers_at(self, point):
        return [l for l, g in self.eroded.items() if g.covers(point)]

    def can_add(self, point):
        self.tick()
        return (len(self.result.candidates) < self.s.max_vias and self.legal.covers(point)
                and not any(self.spacing_points.nearby(point, self.spacing))
                and any(self.graph.rooted(i) for i in self.graph.touch(point)))

    def add(self, point, rule, reason):
        if not self.can_add(point):
            return False
        layers = self.layers_at(point)
        self.result.candidates.append(Candidate(round(point.x, 6), round(point.y, 6), rule, reason, layers))
        self.spacing_points.add(point, layers)
        self.coverage.add(point, layers)
        self.graph.join(self.graph.touch(point, layers))
        return True

    def covered(self, point, distance, layers):
        served = set()
        for _, touched in self.coverage.nearby(point, distance):
            served.update(touched)
        return set(layers).issubset(served)

    def choices(self, area, step=None):
        for poly in sorted(polygons(area), key=lambda p: -p.area):
            yield poly.representative_point()
            if poly.covers(poly.centroid):
                yield poly.centroid
            yield from lattice(poly, step or max(self.spacing / 2, 0.25), self.s.max_samples)

    def repair_islands(self):
        while True:
            progress = False
            for i in self.graph.missing():
                layer, _ = self.graph.regions[i]
                rooted = unary_union([self.eroded_regions[j] for j, (other, _) in enumerate(self.graph.regions)
                                      if other != layer and self.graph.rooted(j)])
                overlap = self.legal.intersection(self.eroded_regions[i]).intersection(rooted)
                for point in self.choices(overlap):
                    if self.add(point, "island", f"Join disconnected ground copper on {layer} to reference component"):
                        progress = True
                        break
            if not progress:
                break

    def place_perimeter(self):
        distance = max(self.s.perimeter_offset_mm, self.radius + self.s.edge_clearance_mm + 0.02)
        inset = self.outline.buffer(-distance, join_style=2)
        for poly in polygons(inset):
            # Interior rings fence board cutouts as well as the outside edge.
            for ring in [poly.exterior, *poly.interiors]:
                for point in sample_line(ring, self.pitch, True, self.s.max_samples):
                    self.tick()
                    if self.covered(point, self.spacing, self.layers_at(point)) and self.layers_at(point):
                        continue
                    if self.add(point, "perimeter", "Even arc-length spacing along inward board offset"):
                        continue
                    # Search a limited arc around this station, preserving edge offset.
                    at = ring.project(point)
                    placed = False
                    for fraction in (0.15, -0.15, 0.3, -0.3):
                        alternate = ring.interpolate((at + fraction * self.pitch) % ring.length)
                        if self.add(alternate, "perimeter", "Shifted along perimeter to clear an obstacle"):
                            placed = True
                            break
                    if not placed:
                        self.note("perimeter_gap", "No legal via near perimeter station", at=[point.x, point.y])

    def place_signals(self):
        for signal, nets in self.signals:
            # Match differential transition vias geometrically and place an atomic,
            # symmetric pair outside them. An obstructed side is reported, not shifted.
            vias = [v for v in self.data["existing_vias"] if v["net"] in nets]
            paired = len(nets) == 2 and (signal.differential or bool(detect_pairs(nets)))
            used = set()
            for i, via in enumerate(vias):
                if i in used:
                    continue
                p = Point(via["at"])
                matches = [(p.distance(Point(v["at"])), j, v) for j, v in enumerate(vias)
                           if j not in used and v["net"] != via["net"] and set(v["layers"]) == set(via["layers"])]
                matches.sort(key=lambda v: v[0])
                match = matches[0] if paired and matches else None
                if match and len(matches) > 1 and abs(matches[1][0] - match[0]) < 0.01:
                    self.note("transition_unmatched", "Ambiguous opposite-net transition vias", at=via["at"], signal=signal.name)
                    continue
                if match and 1e-6 < match[0] <= 3.0:
                    _, j, other = match
                    q = Point(other["at"])
                    dx, dy = (q.x - p.x) / match[0], (q.y - p.y) / match[0]
                    targets = [Point(p.x - dx * signal.offset_mm, p.y - dy * signal.offset_mm),
                               Point(q.x + dx * signal.offset_mm, q.y + dy * signal.offset_mm)]
                    used.update((i, j))
                elif not paired:
                    targets = [Point(p.x - signal.offset_mm, p.y), Point(p.x + signal.offset_mm, p.y)]
                    used.add(i)
                else:
                    self.note("transition_unmatched", "No unambiguous nearby opposite-net transition via", at=via["at"], signal=signal.name)
                    continue
                if all(self.covered(t, self.spacing, self.layers_at(t)) and self.layers_at(t) for t in targets):
                    continue
                if (len(self.result.candidates) + 2 <= self.s.max_vias and all(self.can_add(t) for t in targets)
                        and targets[0].distance(targets[1]) >= self.spacing):
                    for t in targets:
                        self.add(t, "transition", f"Symmetric ground return for {signal.name}")
                else:
                    self.note("transition_gap", "Cannot place both symmetric return vias; adjust signal offset or layout", signal=signal.name, at=via["at"])
            if signal.mode != "fence":
                continue
            by_layer = defaultdict(list)
            for track in self.data["tracks"]:
                if track["net"] in nets:
                    by_layer[track["layer"]].append(LineString(track["points"]))
            for copper in self.data.get("signal_copper", []):
                if copper["net"] in nets:
                    by_layer[copper["layer"]].append(decode(copper["polygons"]))
            if not by_layer:
                self.note("signal_unrouted", "Selected signal has no routed tracks or net-assigned pad/shape copper", signal=signal.name)
            for layer, lines in by_layer.items():
                # Buffer the whole pair bundle, so no fence runs between the pair.
                envelope = unary_union(lines).buffer(signal.offset_mm, cap_style=2, join_style=2)
                for poly in polygons(envelope):
                    for ring in [poly.exterior, *poly.interiors]:
                        for point in sample_line(ring, signal.pitch_mm or self.pitch, True, self.s.max_samples):
                            self.tick()
                            if self.covered(point, self.spacing, self.layers_at(point)) and self.layers_at(point):
                                continue
                            if not self.add(point, "signal_fence", f"Outside signal bundle {signal.name} on {layer}"):
                                self.note("signal_gap", "No legal fence via at station", signal=signal.name, at=[point.x, point.y])

    def place_fingers(self):
        radius = self.s.neck_width_mm / 2
        for layer, ground in self.ground.items():
            opened = ground.buffer(-radius, join_style=2).buffer(radius, join_style=2)
            for finger in polygons(ground.difference(opened)):
                if finger.area < self.s.diameter_mm ** 2:
                    continue
                rectangle = finger.minimum_rotated_rectangle
                coords = list(rectangle.exterior.coords)
                sides = [Point(coords[i]).distance(Point(coords[i + 1])) for i in range(4)]
                if min(sides) == 0 or max(sides) / min(sides) < 3:
                    continue
                self.note("finger_detected", "Narrow elongated ground feature; geometric heuristic, not a resonance prediction",
                          layer=layer, at=list(finger.representative_point().coords)[0], area_mm2=finger.area)
                possible = self.legal.intersection(finger)
                placed = False
                for point in self.choices(possible, min(self.pitch / 2, self.spacing)):
                    self.tick()
                    if not self.covered(point, self.pitch / 2, [layer]):
                        placed |= self.add(point, "finger", f"Stitch narrow ground feature on {layer}")
                if not placed and not any(self.coverage.nearby(finger.representative_point(), self.pitch / 2)):
                    self.note("finger_unresolved", "No suitable landing site in narrow ground feature", layer=layer)

    def place_grid(self):
        for point in lattice(self.legal, self.pitch, self.s.max_samples):
            self.tick()
            if not self.covered(point, self.pitch * 0.7, self.layers_at(point)):
                self.add(point, "grid", "Board-origin grid in overlapping ground copper")
        # Half-pitch audit catches holes left by obstacles and areas between grid
        # stations. Test coverage separately on each contacted ground layer.
        gaps = 0
        for point in lattice(self.legal, self.pitch / 2, self.s.max_samples):
            self.tick()
            if not self.covered(point, self.pitch / math.sqrt(2) + 1e-6, self.layers_at(point)):
                if not self.add(point, "coverage", "Fill a sampled gap in per-layer ground stitching coverage"):
                    gaps += 1
        if gaps:
            self.note("coverage_gaps", "Sampled coverage targets blocked by spacing or via budget", count=gaps)

    def run(self):
        if self.legal.is_empty:
            self.note("no_legal_area", "No clear sites with ground landing copper on at least two layers")
        # Prioritize electrical continuity and local return paths over bulk density.
        if self.s.islands:
            self.repair_islands()
        self.place_signals()
        if self.s.perimeter:
            self.place_perimeter()
        if self.s.fingers:
            self.place_fingers()
        if self.s.grid:
            self.place_grid()
        for i in self.graph.missing():
            layer, region = self.graph.regions[i]
            self.note("island_unresolved", "Ground component still has no connection to reference; may require routing or a layout change",
                      layer=layer, at=list(region.representative_point().coords)[0], area_mm2=region.area)
        if len(self.result.candidates) >= self.s.max_vias:
            self.note("via_budget", "Reached max_vias; examine unresolved features before raising the limit")
        self.result.parameters["samples_evaluated"] = self.samples
        return self.result


def plan(snapshot: dict, settings: Settings | None = None) -> Plan:
    """Plan from a worker snapshot. Callers own preview, validation and saving."""
    return Planner(snapshot, settings or Settings()).run()
