"""Native KiCad worker. Run with KiCad's Python, never import into the planner.

The JSON protocol isolates the deprecated SWIG API. This file deliberately uses
only the standard library and pcbnew so it also runs inside the KiCad Flatpak.
All dimensions crossing the boundary are millimetres.
"""
import json
import math
import sys

import pcbnew as p


def xy(v):
    return [p.ToMM(v.x), p.ToMM(v.y)]


def chain(c):
    return [xy(c.CPoint(i)) for i in range(c.PointCount())]


def polygons(poly):
    # Filled zones are fractured (holes joined by zero-width slits). Restore
    # explicit rings using KiCad itself, rather than healing shapes heuristically.
    poly = p.SHAPE_POLY_SET(poly)
    # Unfracture expects slit-connected contours. Calling it directly on explicit
    # holes can discard them in KiCad 10, so normalize those first.
    if any(poly.HoleCount(i) for i in range(poly.OutlineCount())):
        poly.Fracture()
    poly.Unfracture()
    return [{"shell": chain(poly.Outline(i)),
             "holes": [chain(poly.Hole(i, j)) for j in range(poly.HoleCount(i))]}
            for i in range(poly.OutlineCount())]


def shape(item, layer):
    poly = p.SHAPE_POLY_SET()
    item.TransformShapeToPolygon(poly, layer, 0, p.FromMM(0.005), p.ERROR_OUTSIDE)
    return polygons(poly)


def arc_points(item):
    a, m, b = (xy(v) for v in (item.GetStart(), item.GetMid(), item.GetEnd()))
    ax, ay = a
    mx, my = m
    bx, by = b
    d = 2 * (ax * (my - by) + mx * (by - ay) + bx * (ay - my))
    if abs(d) < 1e-12:
        return [a, b]
    aa, mm, bb = ax * ax + ay * ay, mx * mx + my * my, bx * bx + by * by
    cx = (aa * (my - by) + mm * (by - ay) + bb * (ay - my)) / d
    cy = (aa * (bx - mx) + mm * (ax - bx) + bb * (mx - ax)) / d
    angles = [math.atan2(y - cy, x - cx) for x, y in (a, m, b)]
    sweep = (angles[2] - angles[0]) % math.tau
    if (angles[1] - angles[0]) % math.tau > sweep:
        sweep -= math.tau
    radius = math.hypot(ax - cx, ay - cy)
    # Sagitta below 5 um, with a bounded angular step for small arcs.
    step = min(0.1, 2 * math.acos(max(-1, 1 - 0.005 / max(radius, 0.005))))
    n = max(2, math.ceil(abs(sweep) / step))
    return [[cx + radius * math.cos(angles[0] + sweep * i / n),
             cy + radius * math.sin(angles[0] + sweep * i / n)] for i in range(n + 1)]


def snapshot(board, net):
    layers = [l for l in board.GetEnabledLayers().CuStack()]
    outline = p.SHAPE_POLY_SET()
    if not board.GetBoardPolygonOutlines(outline, False):
        raise ValueError("Board needs a closed, valid Edge.Cuts outline")
    data = {"version": p.Version(), "outline": polygons(outline),
            "layers": [board.GetLayerName(l) for l in layers],
            "ground": {}, "obstacles": [], "bridges": [], "tracks": [], "signal_copper": [],
            "footprints": [], "existing_vias": [], "nets": [], "rules": {}}
    data["nets"] = [str(n) for n in board.GetNetsByName()]
    if net not in data["nets"]:
        raise ValueError("Ground net not found: " + net)
    ds = board.GetDesignSettings()
    for name in ("m_MinClearance", "m_CopperEdgeClearance", "m_HoleClearance",
                 "m_HoleToHoleMin", "m_ViasMinSize", "m_ViasMinAnnularWidth"):
        data["rules"][name] = p.ToMM(getattr(ds, name))

    for l in layers:
        name = board.GetLayerName(l)
        data["ground"][name] = []
        for zone in board.Zones():
            if not zone.IsOnLayer(l):
                continue
            if zone.GetIsRuleArea():
                if zone.GetDoNotAllowVias() or zone.GetDoNotAllowCopperPour():
                    data["obstacles"].append({"kind": "keepout", "polygons": polygons(zone.Outline())})
            else:
                polys = polygons(zone.GetFilledPolysList(l))
                if zone.GetNetname() == net:
                    data["ground"][name].extend(polys)
                else:
                    data["obstacles"].append({"kind": "zone", "polygons": polys,
                                              "net": zone.GetNetname(), "layer": name,
                                              "internal": l not in (p.F_Cu, p.B_Cu)})

    for fp in board.Footprints():
        # Native hull is independent of reference/value text placement.
        hull = polygons(fp.GetBoundingHull())
        yards = []
        for l in (p.F_CrtYd, p.B_CrtYd):
            yards.extend(polygons(fp.GetCourtyard(l)))
        data["footprints"].append({"reference": fp.GetReference(),
                                   "polygons": yards or hull,
                                   "nets": sorted({pad.GetNetname() for pad in fp.Pads() if pad.GetNetname()})})
        # Footprint-local rule areas carry antenna and mechanical keepouts.
        for zone in fp.Zones():
            if zone.GetIsRuleArea() and (zone.GetDoNotAllowVias() or zone.GetDoNotAllowCopperPour()):
                data["obstacles"].append({"kind": "keepout", "polygons": polygons(zone.Outline())})

    copper_items = list(board.GetPads()) + list(board.GetTracks())
    graphics = list(board.GetDrawings())
    for fp in board.Footprints():
        graphics.extend(fp.GraphicalItems())
    copper_items.extend(item for item in graphics if any(item.IsOnLayer(l) for l in layers))
    for item in copper_items:
        is_via = isinstance(item, p.PCB_VIA)
        is_pad = isinstance(item, p.PAD)
        item_net = item.GetNetname() if hasattr(item, "GetNetname") else ""
        touched = []
        for l in layers:
            if not item.IsOnLayer(l):
                continue
            polys = shape(item, l)
            if not polys:
                continue
            name = board.GetLayerName(l)
            touched.append(name)
            data["obstacles"].append({"kind": "via" if is_via else "copper", "polygons": polys,
                                      "net": item_net, "layer": name})
            if item_net == net and not is_via:
                data["ground"][name].extend(polys)
            elif item_net and not isinstance(item, p.PCB_TRACK):
                data["signal_copper"].append({"net": item_net, "layer": name, "polygons": polys})
        if is_via or is_pad:
            drill = item.GetDrillValue() if is_via else max(item.GetDrillSizeX(), item.GetDrillSizeY())
            if drill > 0:
                hole = p.SHAPE_POLY_SET()
                item.GetEffectiveHoleShape().TransformToPolygon(hole, p.FromMM(0.005), p.ERROR_OUTSIDE)
                data["obstacles"].append({"kind": "hole", "polygons": polygons(hole)})
            # Only plated through pads and actual via spans join layers.
            if drill > 0 and item_net == net and (is_via or item.GetAttribute() == p.PAD_ATTRIB_PTH):
                data["bridges"].append({"at": xy(item.GetPosition()), "layers": touched})
            if is_via:
                data["existing_vias"].append({"at": xy(item.GetPosition()), "net": item_net,
                                              "layers": touched, "uuid": item.m_Uuid.AsString()})
        if isinstance(item, p.PCB_TRACK) and not is_via:
            data["tracks"].append({"net": item_net, "layer": board.GetLayerName(item.GetLayer()),
                                   "points": arc_points(item) if isinstance(item, p.PCB_ARC)
                                   else [xy(item.GetStart()), xy(item.GetEnd())],
                                   "width": p.ToMM(item.GetWidth())})
    return data


def connectivity(board, request):
    """Stable routing-item components, independent of ratsnest endpoint choice.

    Query from non-zone items. One zone UUID can represent disconnected islands,
    so it must never be used as a common vertex to merge those islands.
    """
    if not board.BuildConnectivity():
        raise ValueError("Could not build native board connectivity")
    items = list(board.AllConnectedItems())
    requested_ids = set(request.get("item_uuids", []))
    nets = set(request.get("nets", []))
    nets.update(item.GetNetname() for item in items if item.m_Uuid.AsString() in requested_ids)
    by_id = {item.m_Uuid.AsString(): item for item in items
             if item.GetNetname() in nets and item.GetNetCode() > 0 and not isinstance(item, p.ZONE)}
    item_nets = {uid: item.GetNetname() for uid, item in by_id.items()}
    result = {"nets": {net: [] for net in sorted(nets)}, "item_nets": item_nets}
    visited = set()
    conn = board.GetConnectivity()
    for uid, item in sorted(by_id.items()):
        if uid in visited:
            continue
        net = item.GetNetname()
        component = {connected.m_Uuid.AsString() for connected in conn.GetConnectedItems(item)
                     if connected.m_Uuid.AsString() in by_id and connected.GetNetname() == net}
        component.add(uid)
        visited.update(component)
        result["nets"][net].append(sorted(component))
    return result


def main():
    request = json.load(sys.stdin)
    if not p.Version().startswith("10."):
        raise ValueError("This adapter supports KiCad 10.x; found " + p.Version())
    board = p.LoadBoard(request["board"])
    action = request["action"]
    if action == "snapshot":
        result = snapshot(board, request["net"])
    elif action == "connectivity":
        result = connectivity(board, request)
    elif action == "retain":
        for zone in board.Zones():
            if zone.GetNetname() == request["net"] and not zone.GetIsRuleArea():
                zone.SetIslandRemovalMode(p.ISLAND_REMOVAL_MODE_NEVER)
        p.SaveBoard(request["output"], board)
        result = {}
    elif action == "place":
        ids = []
        code = board.GetNetsByName()[request["net"]].GetNetCode()
        for candidate in request["candidates"]:
            via = p.PCB_VIA(board)
            via.SetPosition(p.VECTOR2I(p.FromMM(candidate["x"]), p.FromMM(candidate["y"])))
            via.SetWidth(p.FromMM(request["diameter_mm"]))
            via.SetDrill(p.FromMM(request["drill_mm"]))
            via.SetViaType(p.VIATYPE_THROUGH)
            via.SetLayerPair(p.F_Cu, p.B_Cu)
            via.SetNetCode(code)
            board.Add(via)
            ids.append(via.m_Uuid.AsString())
        p.SaveBoard(request["output"], board)
        result = {"uuids": ids}
    else:
        raise ValueError("Unknown worker action: " + action)
    json.dump(result, sys.stdout)


if __name__ == "__main__":
    main()
