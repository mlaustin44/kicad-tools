"""Measure actual final geometry separately from native DRC acceptance."""
import math
from collections import Counter

from shapely.geometry import Point
from shapely.ops import unary_union

from .geometry import Connectivity, decode, polygons, widest_point
from .planner import Planner, PointIndex


def rooted_graph(snapshot, settings, reference):
    ground = {layer: decode(polys) for layer, polys in snapshot["ground"].items()}
    graph = Connectivity(ground, snapshot["bridges"], settings.anchors_mm)
    nodes = graph.touch(Point(reference["at"]), [reference["layer"]])
    if nodes:
        graph.root = nodes[0]
    return ground, graph


def island_recovery(exploratory, final, settings, reference):
    _, before = rooted_graph(exploratory, settings, reference)
    final_ground, after = rooted_graph(final, settings, reference)
    connected = {layer: unary_union([poly for i, (name, poly) in enumerate(after.regions)
                                     if name == layer and after.rooted(i)]) for layer in final_ground}
    records = []
    for i in before.missing():
        layer, region = before.regions[i]
        surviving = final_ground[layer].intersection(region).area
        recovered = connected[layer].intersection(region).area
        if recovered >= region.area * 0.5:
            state = "connected"
        elif surviving < max(1e-7, region.area * 0.01):
            state = "removed_by_fill"
        elif recovered > max(1e-7, region.area * 0.01):
            state = "partially_connected"
        else:
            state = "disconnected"
        records.append({"layer": layer, "at": list(region.representative_point().coords)[0],
                        "bounds": list(region.bounds), "state": state, "original_area_mm2": region.area,
                        "surviving_area_mm2": surviving, "connected_area_mm2": recovered})
    return {"initial_regions": len(records), "counts": dict(Counter(r["state"] for r in records)), "regions": records}


def placement_quality(snapshot, settings, reference):
    """Re-audit the saved fill, including any native-rejected candidate holes."""
    planner = Planner(snapshot, settings)
    _, graph = rooted_graph(snapshot, settings, reference)
    planner.graph = graph
    planner._rooted_mask = None
    planner.coverage = PointIndex(max(planner.spacing, planner.pitch))
    for bridge in snapshot["bridges"]:
        point = Point(bridge["at"])
        touched = graph.touch(point, bridge["layers"])
        layers = {graph.regions[i][0] for i in touched}
        if len(layers) >= 2 and any(graph.rooted(i) for i in touched):
            planner.coverage.add(point, layers)
    radius = planner.pitch / (math.sqrt(3) if settings.grid_pattern == "staggered" else math.sqrt(2))
    coverage = []
    for layer, landing in (planner.eroded.items() if settings.grid else []):
        area = planner.legal.intersection(landing).intersection(planner.rooted_mask())
        served = unary_union([p.buffer(radius) for p, layers in planner.coverage.points() if layer in layers])
        uncovered = area.difference(served)
        target = widest_point(uncovered, tolerance=0.04)
        significant = target is not None and target.distance(uncovered.boundary) > 0.05
        coverage.append({"layer": layer, "uncovered_legal_area_mm2": uncovered.area,
                         "significant_gap": bool(significant), "at": [target.x, target.y] if significant else None})
    distance = max(settings.perimeter_offset_mm, planner.radius + settings.edge_clearance_mm + 0.02)
    inset = planner.outline.buffer(-distance, join_style=2)
    search = min(planner.search_radius, planner.perimeter_pitch / 2)
    gaps, max_gap = [], 0.0
    for poly in (polygons(inset) if settings.perimeter else []):
        for ring in [poly.exterior, *poly.interiors]:
            stations = sorted({round(ring.project(p), 6) for p, _ in planner.coverage.points()
                               if p.distance(ring) <= search+0.01 and inset.buffer(0.01).covers(p)})
            intervals = [(a, b-a) for a, b in zip(stations, stations[1:]+[stations[0]+ring.length])] if stations else [(0, ring.length)]
            max_gap = max(max_gap, max((gap for _, gap in intervals), default=ring.length))
            for start, gap in intervals:
                if gap > planner.perimeter_pitch * 1.25:
                    target = ring.interpolate((start+gap/2) % ring.length)
                    gaps.append({"at": [target.x, target.y], "gap_mm": gap})
    return {"grid_enabled": settings.grid, "perimeter_enabled": settings.perimeter,
            "grid_pitch_mm": planner.pitch, "perimeter_pitch_mm": planner.perimeter_pitch,
            "coverage_radius_mm": radius if settings.grid else None, "coverage_tolerance_mm": 0.1, "coverage": coverage,
            "perimeter_max_gap_mm": max_gap if settings.perimeter else None, "perimeter_gaps": gaps,
            "note": "Geometric coverage of legal sites; not an EMC or signal-integrity certification"}
