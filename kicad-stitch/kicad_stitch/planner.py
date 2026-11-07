"""Pure planning engine: no filesystem, KiCad process, or CLI dependencies."""
from __future__ import annotations

from collections import defaultdict
from dataclasses import replace
from fnmatch import fnmatchcase
import math

from shapely.geometry import LineString, Point, box
from shapely.ops import nearest_points, unary_union

from .geometry import Connectivity, decode, grid_targets, polygons, sample_line, widest_point
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

    def points(self):
        for entries in self.bins.values():
            yield from entries


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
    wavelength = 299792458000 / (max(frequencies) * math.sqrt(settings.epsilon_r)) if frequencies else None
    electrical = wavelength / settings.wavelength_divisor if wavelength else None
    grid_limit = wavelength / settings.grid_wavelength_divisor if wavelength else None
    desired = settings.grid_pitch_mm or settings.pitch_mm or geometric
    if grid_limit:
        desired = min(desired, grid_limit)
    if desired < min_spacing:
        raise ValueError(f"Requested pitch {desired:.3f} mm is below legal via spacing {min_spacing:.3f} mm")
    return desired, {"pitch_mm": desired, "geometric_pitch_mm": geometric,
                     "electrical_pitch_limit_mm": electrical,
                     "grid_electrical_pitch_limit_mm": grid_limit,
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
        self.initial_islands = list(self.graph.missing())
        self.radius = settings.diameter_mm / 2
        rules = snapshot.get("rules", {})
        clearance = max(settings.clearance_mm, rules.get("m_MinClearance", 0))
        self.spacing = max(settings.min_spacing_mm, settings.diameter_mm + clearance,
                           settings.drill_mm + rules.get("m_HoleToHoleMin", 0))
        self.pitch, self.result.parameters = choose_pitch(settings, self.outline.area, self.spacing)
        fence_limit = self.result.parameters["electrical_pitch_limit_mm"]
        def pass_pitch(explicit, default):
            value = explicit or max(self.spacing, default)
            if fence_limit:
                value = min(value, fence_limit)
            if value < self.spacing:
                raise ValueError("Requested fence/finger pitch is below legal via spacing")
            return value
        self.perimeter_pitch = pass_pitch(settings.perimeter_pitch_mm, self.pitch / 2)
        self.signal_pitch = pass_pitch(settings.signal_pitch_mm, self.perimeter_pitch)
        self.finger_pitch = pass_pitch(settings.finger_pitch_mm, min(self.perimeter_pitch, settings.neck_width_mm * 2))
        self.search_radius = settings.search_radius_mm or self.pitch / 2
        self.result.parameters.update({"grid_pitch_mm": self.pitch, "perimeter_pitch_mm": self.perimeter_pitch,
            "signal_pitch_mm": self.signal_pitch, "finger_pitch_mm": self.finger_pitch,
            "search_radius_mm": self.search_radius, "grid_pattern": settings.grid_pattern,
            "zone_policy": settings.zone_policy})
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
            if item["kind"] == "zone":
                internal = item.get("internal", item.get("layer", "").startswith("In"))
                if settings.zone_policy == "antipads" or (settings.zone_policy == "internal_antipads" and internal):
                    continue
            margin = self.radius + clearance + 0.01
            if item["kind"] == "hole":
                margin = max(self.radius + rules.get("m_HoleClearance", clearance),
                             settings.drill_mm / 2 + rules.get("m_HoleToHoleMin", clearance)) + 0.01
            elif item["kind"] == "keepout":
                margin = self.radius + 0.01
            geometry = decode(item["polygons"]).buffer(margin)
            obstacles.append(geometry)
        for fp in snapshot["footprints"]:
            geometry = decode(fp["polygons"]).buffer(self.radius + settings.component_clearance_mm)
            obstacles.append(geometry)
        obstacles.extend(box(*bounds).buffer(self.radius) for bounds in settings.exclusions_mm)
        edge = max(settings.edge_clearance_mm, rules.get("m_CopperEdgeClearance", 0))
        self.safe = self.outline.buffer(-edge - self.radius - 0.01).difference(unary_union(obstacles))
        self.eroded = {l: g.buffer(-self.radius - 0.01) for l, g in self.ground.items()}
        landing = []
        layers = list(self.eroded)
        for i, layer in enumerate(layers):
            for other in layers[i + 1:]:
                landing.append(self.eroded[layer].intersection(self.eroded[other]))
        self.legal = self.safe.intersection(unary_union(landing))
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
        self._rooted_mask = None
        self.signals = self.resolve_signals()
        # Protect the chosen signal-to-ground-via spacing from *all* passes.
        corridors = []
        for signal, nets in self.signals:
            for track in snapshot["tracks"]:
                if track["net"] in nets:
                    corridors.append(LineString(track["points"]).buffer(signal.offset_mm))
            for copper in snapshot.get("signal_copper", []):
                if copper["net"] in nets:
                    corridors.append(decode(copper["polygons"]).buffer(signal.offset_mm))
        self.signal_corridors = unary_union(corridors)
        self.legal = self.legal.difference(self.signal_corridors)

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
            pitch = signal.pitch_mm or self.signal_pitch
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

    def add(self, point, rule, reason, target=None):
        if not self.can_add(point):
            return False
        layers = self.layers_at(point)
        displacement = point.distance(target) if target is not None else 0.0
        self.result.candidates.append(Candidate(round(point.x, 6), round(point.y, 6), rule, reason, layers,
            target=[round(target.x, 6), round(target.y, 6)] if target is not None else None,
            displacement_mm=round(displacement, 6)))
        self.spacing_points.add(point, layers)
        self.coverage.add(point, layers)
        nodes = self.graph.touch(point, layers)
        if any(not self.graph.rooted(i) for i in nodes):
            self._rooted_mask = None
        self.graph.join(nodes)
        return True

    def covered(self, point, distance, layers):
        if not layers:
            return False
        served = set()
        for _, touched in self.coverage.nearby(point, distance):
            served.update(touched)
        return set(layers).issubset(served)

    def rooted_mask(self):
        if self._rooted_mask is None:
            self._rooted_mask = unary_union([self.eroded_regions[i] for i in range(len(self.graph.regions))
                                            if self.graph.rooted(i)])
        return self._rooted_mask

    def available(self, area, target=None, radius=None):
        area = area.intersection(self.legal).intersection(self.rooted_mask())
        if target is not None and radius is not None:
            area = area.intersection(target.buffer(radius))
        if area.is_empty:
            return area
        center = target if target is not None else area.representative_point()
        reach = radius if radius is not None else math.hypot(area.bounds[2]-area.bounds[0], area.bounds[3]-area.bounds[1])
        blocked = [p.buffer((self.spacing + 0.002) / math.cos(math.pi / 64), quad_segs=16)
                   for p, _ in self.spacing_points.nearby(center, reach + self.spacing)]
        return area.difference(unary_union(blocked)) if blocked else area

    def locate(self, target, area=None, radius=None, on_path=False):
        """Solve in the legal geometry; target points are preferences, never a snap grid."""
        area = self.legal if area is None else area
        radius = self.search_radius if radius is None else radius
        possible = self.available(area, target, radius)
        if possible.is_empty:
            return None
        if possible.covers(target) and self.can_add(target):
            return target
        if on_path:
            points = [nearest_points(target, possible)[1], possible.representative_point()]
        else:
            # Prefer a small extra clearance reserve, but do not erase tiny legal
            # pockets with a fixed secondary inset.
            interior = possible.buffer(-0.02)
            preferred = interior if not interior.is_empty else possible
            points = [nearest_points(target, preferred)[1], widest_point(possible), possible.representative_point()]
        for point in points:
            if point is not None and self.can_add(point):
                return point
        return None

    def choices(self, area):
        # Subtract spacing *before* choosing a center. A centroid and coarse
        # lattice can both miss a narrow off-grid remainder beside an old via.
        available = self.available(area)
        for poly in sorted(polygons(available), key=lambda p: -p.area):
            center = widest_point(poly)
            if center is not None:
                yield center
            yield poly.representative_point()

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
        search = min(self.search_radius, self.perimeter_pitch / 2)
        band = inset.difference(self.outline.buffer(-distance-search, join_style=2))
        rings = []
        for poly in polygons(inset):
            # Interior rings fence board cutouts as well as the outside edge.
            for ring in [poly.exterior, *poly.interiors]:
                rings.append(ring)
                for point in sample_line(ring, self.perimeter_pitch, True, self.s.max_samples):
                    self.tick()
                    if self.covered(point, self.spacing, self.layers_at(point)) and self.layers_at(point):
                        continue
                    chosen = self.locate(point, ring, search, on_path=True)
                    if chosen is None:
                        chosen = self.locate(point, band, search)
                    if chosen is not None:
                        self.add(chosen, "perimeter", "Contour target relocated locally when obstructed", target=point)
        # Audit *actual* contour coverage, rather than reporting only how many
        # nominal stations were attempted. Try to close oversized intervals.
        max_gap = 0.0
        gap_count = 0
        for ring in rings:
            for attempt in range(3):
                stations = sorted({round(ring.project(p), 6) for p, _ in self.coverage.points()
                                   if p.distance(ring) <= search + 0.01 and inset.buffer(0.01).covers(p)})
                intervals = [(a, b-a) for a, b in zip(stations, stations[1:] + [stations[0]+ring.length])] if stations else [(0, ring.length)]
                long = [(a, gap) for a, gap in intervals if gap > self.perimeter_pitch * 1.25]
                placed = False
                if attempt < 2:
                    for a, gap in long:
                        for j in range(1, max(2, math.ceil(gap/self.perimeter_pitch))):
                            point = ring.interpolate((a + gap*j/max(2, math.ceil(gap/self.perimeter_pitch))) % ring.length)
                            chosen = self.locate(point, ring, search, on_path=True)
                            if chosen is None:
                                chosen = self.locate(point, band, search)
                            if chosen is not None:
                                placed |= self.add(chosen, "perimeter", "Close a measured gap in the edge fence", target=point)
                if not placed:
                    max_gap = max(max_gap, max((gap for _, gap in intervals), default=ring.length))
                    for a, gap in long:
                        point = ring.interpolate((a + gap/2) % ring.length)
                        gap_count += 1
                        self.note("perimeter_gap", "Actual edge-fence interval exceeds target; local legal sites exhausted",
                                  at=[point.x, point.y], gap_mm=gap, target_pitch_mm=self.perimeter_pitch)
                    break
        self.result.parameters["perimeter_audit"] = {"max_contour_gap_mm": max_gap,
            "gap_count": gap_count, "gap_threshold_mm": self.perimeter_pitch * 1.25,
            "allowed_inward_shift_mm": search}

    def place_signals(self):
        for signal, nets in self.signals:
            # Match differential transition vias geometrically and place an atomic,
            # symmetric pair outside them. Relocate both together or report a gap.
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
                chosen_pair = None
                if len(self.result.candidates) + 2 <= self.s.max_vias:
                    center = Point((targets[0].x+targets[1].x)/2, (targets[0].y+targets[1].y)/2)
                    base_radius = targets[0].distance(center)
                    direction = math.atan2(targets[1].y-center.y, targets[1].x-center.x)
                    search = min(self.search_radius, signal.pitch_mm/2, 2.0)
                    alternatives = []
                    for extra in (0, 0.25, 0.5, 0.75, 1, 1.5, 2):
                        if extra > search:
                            continue
                        for angle in (0, 15, -15, 30, -30, 45, -45, 60, -60, 90):
                            theta = direction + math.radians(angle)
                            dx, dy = (base_radius+extra)*math.cos(theta), (base_radius+extra)*math.sin(theta)
                            pair = [Point(center.x-dx, center.y-dy), Point(center.x+dx, center.y+dy)]
                            shift = max(a.distance(b) for a, b in zip(pair, targets))
                            if shift <= search + 1e-7:
                                alternatives.append((shift, extra, abs(angle), pair))
                    for _, _, _, pair in sorted(alternatives, key=lambda a: a[:3]):
                        if pair[0].distance(pair[1]) >= self.spacing and all(self.can_add(t) for t in pair):
                            chosen_pair = pair
                            break
                if chosen_pair is not None:
                    for t, target in zip(chosen_pair, targets):
                        self.add(t, "transition", f"Symmetric ground return for {signal.name}; local rotation/offset search", target=target)
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
                search = min(self.search_radius, signal.pitch_mm/2)
                band = envelope.buffer(search).difference(envelope.buffer(-1e-7))
                for poly in polygons(envelope):
                    for ring in [poly.exterior, *poly.interiors]:
                        for point in sample_line(ring, signal.pitch_mm or self.pitch, True, self.s.max_samples):
                            self.tick()
                            if self.covered(point, self.spacing, self.layers_at(point)) and self.layers_at(point):
                                continue
                            chosen = self.locate(point, ring, search, on_path=True)
                            if chosen is None:
                                chosen = self.locate(point, band, search)
                            if chosen is not None:
                                self.add(chosen, "signal_fence", f"Locally adjusted outside bundle {signal.name} on {layer}", target=point)
                            else:
                                self.note("signal_gap", "No legal fence via at station", signal=signal.name, at=[point.x, point.y])

    def place_fingers(self):
        radius = self.s.neck_width_mm / 2
        for layer in self.ground:
            # Floating slivers belong to island recovery/removal, not to an
            # antenna warning on copper that will not survive normal refill.
            ground = unary_union([poly for i, (name, poly) in enumerate(self.graph.regions)
                                  if name == layer and self.graph.rooted(i)])
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
                # Work along the feature's long axis, starting at its distal tip.
                k = max(range(4), key=lambda i: sides[i])
                dx, dy = (coords[k+1][0]-coords[k][0])/sides[k], (coords[k+1][1]-coords[k][1])/sides[k]
                center = rectangle.centroid
                projected = [(x-center.x)*dx+(y-center.y)*dy for x, y in coords[:4]]
                ends = [Point(center.x+t*dx, center.y+t*dy) for t in (min(projected), max(projected))]
                if not opened.is_empty and ends[0].distance(opened) < ends[1].distance(opened):
                    ends.reverse()
                axis = LineString(ends)
                for point in sample_line(axis, self.finger_pitch, limit=self.s.max_samples):
                    self.tick()
                    served = any(layer in layers and finger.distance(p) <= self.radius+0.01
                                 for p, layers in self.coverage.nearby(point, self.finger_pitch/2))
                    if not served:
                        chosen = self.locate(point, possible, min(self.search_radius, self.finger_pitch))
                        if chosen is not None:
                            placed |= self.add(chosen, "finger", f"Stitch distal/narrow ground feature on {layer}", target=point)
                served = any(layer in layers and finger.distance(p) <= self.radius+0.01
                             for p, layers in self.coverage.points())
                if not placed and not served:
                    self.note("finger_unresolved", "No legal via landing touching the narrow feature", layer=layer,
                              at=list(finger.representative_point().coords)[0], legal_area_mm2=possible.area)

    def place_grid(self):
        radius = self.pitch / (math.sqrt(3) if self.s.grid_pattern == "staggered" else math.sqrt(2))
        for point in grid_targets(self.outline, self.pitch, self.s.grid_pattern, self.s.max_samples):
            self.tick()
            layers = self.layers_at(point)
            if len(layers) >= 2 and self.covered(point, radius, layers):
                continue
            chosen = self.locate(point)
            if chosen is not None and not self.covered(chosen, radius, self.layers_at(chosen)):
                self.add(chosen, "grid", "Nominal staggered/square cell target relocated into nearby legal copper", target=point)
        # Continuous polygon coverage, not another fixed sampling lattice. The
        # inscribed-circle center finds off-grid pockets and the largest gaps.
        for layer, landing in self.eroded.items():
            area = self.legal.intersection(landing).intersection(self.rooted_mask())
            served = unary_union([p.buffer(radius) for p, layers in self.coverage.points() if layer in layers])
            uncovered = area.difference(served)
            while not uncovered.is_empty and len(self.result.candidates) < self.s.max_vias:
                self.tick()
                target = widest_point(uncovered, tolerance=0.04)
                if target is None or target.distance(uncovered.boundary) <= 0.05:
                    break
                component = next((p for p in polygons(uncovered) if p.covers(target)), None)
                if component is None:
                    break
                chosen = self.locate(target, component)
                if chosen is None:
                    uncovered = uncovered.difference(component)
                    continue
                if self.add(chosen, "coverage", f"Close a continuous geometric coverage gap on {layer}", target=target):
                    uncovered = uncovered.difference(chosen.buffer(radius))
                else:
                    uncovered = uncovered.difference(component)
        audits = []
        for layer, landing in self.eroded.items():
            area = self.legal.intersection(landing).intersection(self.rooted_mask())
            served = unary_union([p.buffer(radius) for p, layers in self.coverage.points() if layer in layers])
            uncovered = area.difference(served)
            target = widest_point(uncovered, tolerance=0.04)
            significant = target is not None and target.distance(uncovered.boundary) > 0.05
            audits.append({"layer": layer, "uncovered_legal_area_mm2": uncovered.area,
                           "significant_gap": bool(significant),
                           "at": [target.x, target.y] if significant else None})
            if significant:
                self.note("coverage_gaps", "Legal copper remains outside the target coverage radius after spacing/budget constraints",
                          layer=layer, at=[target.x, target.y], area_mm2=uncovered.area)
        self.result.parameters["coverage_audit"] = {"radius_mm": radius, "tolerance_mm": 0.1, "layers": audits}

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
            landing = self.eroded_regions[i]
            rooted = unary_union([self.eroded_regions[j] for j, (other, _) in enumerate(self.graph.regions)
                                  if other != layer and self.graph.rooted(j)])
            overlap = landing.intersection(rooted)
            feasible = overlap.intersection(self.legal)
            if landing.is_empty:
                reason = "landing_too_narrow"
            elif overlap.is_empty:
                reason = "no_reference_overlap"
            elif not feasible.is_empty:
                reason = "via_spacing_or_budget"
            else:
                before_signals = overlap.intersection(self.safe)
                reason = "signal_offset" if not before_signals.is_empty else "copper_component_or_keepout_clearance"
            self.note("island_unresolved", "Ground component still has no connection to reference; may require routing or a layout change",
                      layer=layer, at=list(region.representative_point().coords)[0], area_mm2=region.area,
                      reason=reason, bounds=list(region.bounds), legal_landing_area_mm2=feasible.area,
                      diameter_mm=self.s.diameter_mm, clearance_mm=self.s.clearance_mm)
        if len(self.result.candidates) >= self.s.max_vias:
            self.note("via_budget", "Reached max_vias; examine unresolved features before raising the limit")
        self.result.parameters["samples_evaluated"] = self.samples
        self.result.parameters["relocated_vias"] = sum(c.displacement_mm > 0.01 for c in self.result.candidates)
        self.result.parameters["island_audit"] = {"initial_regions": len(self.initial_islands),
            "planned_connected_regions": sum(self.graph.rooted(i) for i in self.initial_islands),
            "unresolved_regions": len(self.graph.missing())}
        self.result.parameters["transition_audit"] = [
            {"net": via["net"], "at": via["at"],
             "nearest_ground_contacts": [{"at": [p.x, p.y], "distance_mm": distance, "layers": sorted(layers)}
                 for distance, p, layers in sorted(
                     [(Point(via["at"]).distance(p), p, layers) for p, layers in self.coverage.points()],
                     key=lambda item: item[0])[:2]]}
            for via in self.data["existing_vias"] if any(via["net"] in nets for _, nets in self.signals)]
        return self.result


def plan(snapshot: dict, settings: Settings | None = None) -> Plan:
    """Plan from a worker snapshot. Callers own preview, validation and saving."""
    return Planner(snapshot, settings or Settings()).run()
