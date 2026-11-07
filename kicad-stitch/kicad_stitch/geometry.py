"""Polygon operations, connectivity, and bounded deterministic sampling."""
from __future__ import annotations

import math
from shapely import maximum_inscribed_circle
from shapely.geometry import GeometryCollection, Point, Polygon
from shapely.ops import unary_union


def polygons(geometry):
    if isinstance(geometry, Polygon):
        return [geometry] if not geometry.is_empty else []
    return [p for g in getattr(geometry, "geoms", []) for p in polygons(g)]


def decode(items):
    shapes = []
    for item in items:
        poly = Polygon(item["shell"], item.get("holes", []))
        if not poly.is_valid:
            raise ValueError("KiCad returned invalid polygon geometry; repair the board before stitching")
        shapes.append(poly)
    return unary_union(shapes) if shapes else GeometryCollection()


def sample_line(line, pitch, closed=False, limit=250000):
    n = max(1, math.ceil(line.length / pitch))
    if n + 1 > limit:
        raise ValueError(f"Contour sampling exceeds limit {limit}; increase pitch or max_samples")
    for i in range(n if closed else n + 1):
        yield line.interpolate(line.length * i / n)


def lattice(area, step, limit):
    if area.is_empty:
        return
    minx, miny, maxx, maxy = area.bounds
    # Global origin makes placement stable as local obstacles change.
    x0, y0 = math.ceil(minx / step), math.ceil(miny / step)
    nx, ny = math.floor(maxx / step) - x0 + 1, math.floor(maxy / step) - y0 + 1
    if nx * ny > limit:
        raise ValueError(f"Sampling needs {nx * ny} points (limit {limit}); increase pitch or max_samples")
    for ix in range(x0, x0 + nx):
        for iy in range(y0, y0 + ny):
            point = Point(ix * step, iy * step)
            if area.covers(point):
                yield point


def widest_point(area, tolerance=0.03):
    """Use GEOS's maximum-inscribed-circle search, including tiny off-grid sites."""
    area = unary_union(polygons(area))
    if area.is_empty:
        return None
    circle = maximum_inscribed_circle(area, tolerance=tolerance)
    return Point(circle.coords[0]) if not circle.is_empty else None


def grid_targets(area, pitch, pattern, limit):
    """Nominal targets cover the outline, including obstructed locations to shift."""
    if area.is_empty:
        return
    minx, miny, maxx, maxy = area.bounds
    dy = pitch * math.sqrt(3) / 2 if pattern == "staggered" else pitch
    y0, y1 = math.ceil(miny / dy), math.floor(maxy / dy)
    if (math.ceil((maxx - minx) / pitch) + 2) * (y1 - y0 + 1) > limit:
        raise ValueError("Grid targets exceed max_samples; increase pitch or budget")
    for iy in range(y0, y1 + 1):
        offset = pitch / 2 if pattern == "staggered" and iy % 2 else 0
        for ix in range(math.ceil((minx - offset) / pitch), math.floor((maxx - offset) / pitch) + 1):
            point = Point(ix * pitch + offset, iy * dy)
            if area.covers(point):
                yield point


class Connectivity:
    def __init__(self, ground, bridges, anchors=()):
        self.regions = [(layer, poly) for layer, g in ground.items() for poly in polygons(g)]
        self.parents = list(range(len(self.regions)))
        for bridge in bridges:
            self.join(self.touch(Point(bridge["at"]), bridge["layers"]))
        if not self.regions:
            raise ValueError("No ground copper found")
        if anchors:
            roots = []
            for at in anchors:
                touched = self.touch(Point(at))
                if not touched:
                    raise ValueError(f"Ground anchor {at} does not touch ground copper")
                components = {self.find(i) for i in touched}
                if len(components) != 1:
                    raise ValueError(f"Ground anchor {at} is ambiguous across layers; choose an existing plated connection")
                roots.extend(touched)
            if len({self.find(i) for i in roots}) != 1:
                raise ValueError("Ground anchors must already belong to one connected component")
            self.root = roots[0]
        else:
            areas = {}
            for i, (_, region) in enumerate(self.regions):
                root = self.find(i)
                areas[root] = areas.get(root, 0) + region.area
            self.root = max(areas, key=areas.get)

    def find(self, i):
        while i != self.parents[i]:
            self.parents[i] = self.parents[self.parents[i]]
            i = self.parents[i]
        return i

    def join(self, nodes):
        for i in nodes[1:]:
            self.parents[self.find(i)] = self.find(nodes[0])

    def touch(self, point, layers=None):
        return [i for i, (layer, poly) in enumerate(self.regions)
                if (layers is None or layer in layers) and poly.covers(point)]

    def rooted(self, i):
        return self.find(i) == self.find(self.root)

    def missing(self):
        return [i for i in range(len(self.regions)) if not self.rooted(i)]
