"""Generate native KiCad integration fixtures; execute with KiCad's Python."""
import json
from pathlib import Path
import sys

import pcbnew as p


def create(directory):
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    board = p.BOARD()
    board.SetCopperLayerCount(4)
    gnd = p.NETINFO_ITEM(board, "GND")
    sig = p.NETINFO_ITEM(board, "SIGNAL")
    board.Add(gnd)
    board.Add(sig)

    def point(x, y):
        return p.VECTOR2I(p.FromMM(x), p.FromMM(y))

    def rect(x1, y1, x2, y2):
        for a, b in (((x1, y1), (x2, y1)), ((x2, y1), (x2, y2)),
                     ((x2, y2), (x1, y2)), ((x1, y2), (x1, y1))):
            line = p.PCB_SHAPE(board)
            line.SetShape(p.SHAPE_T_SEGMENT)
            line.SetStart(point(*a))
            line.SetEnd(point(*b))
            line.SetLayer(p.Edge_Cuts)
            line.SetWidth(p.FromMM(0.05))
            board.Add(line)

    rect(0, 0, 40, 30)
    rect(17, 12, 23, 18)
    for l in (p.F_Cu, p.In1_Cu, p.In2_Cu, p.B_Cu):
        zone = p.ZONE(board)
        zone.SetLayer(l)
        zone.SetNet(gnd)
        zone.SetLocalClearance(p.FromMM(0.2))
        zone.SetMinThickness(p.FromMM(0.2))
        zone.SetIslandRemovalMode(p.ISLAND_REMOVAL_MODE_ALWAYS)
        poly = zone.Outline()
        poly.NewOutline()
        for x, y in ((0, 0), (40, 0), (40, 30), (0, 30)):
            poly.Append(p.FromMM(x), p.FromMM(y))
        board.Add(zone)
    # One plated GND pad anchors the left-hand plane, with an initial stitch.
    fp = p.FOOTPRINT(board)
    fp.SetReference("J1")
    fp.SetPosition(point(5, 5))
    pad = p.PAD(fp)
    pad.SetNumber("1")
    pad.SetAttribute(p.PAD_ATTRIB_PTH)
    pad.SetShape(p.PAD_SHAPE_CIRCLE)
    pad.SetPosition(point(5, 5))
    pad.SetSize(point(1.5, 1.5))
    pad.SetDrillSize(point(0.8, 0.8))
    pad.SetLayerSet(p.LSET.AllCuMask())
    pad.SetNet(gnd)
    fp.Add(pad)
    board.Add(fp)
    # Top signal barrier splits the top pour. Its right-hand ground is removed
    # by normal island filtering, but retained for exploratory fill.
    for start_y, end_y in ((0.5, 11.5), (18.5, 29.5)):
        track = p.PCB_TRACK(board)
        track.SetStart(point(20, start_y))
        track.SetEnd(point(20, end_y))
        track.SetLayer(p.F_Cu)
        track.SetWidth(p.FromMM(0.5))
        track.SetNet(sig)
        board.Add(track)
    path = directory / "sample.kicad_pcb"
    p.SaveBoard(str(path), board)
    path.with_suffix(".kicad_pro").write_text(json.dumps({"meta": {"filename": "sample.kicad_pro", "version": 1},
        "board": {"design_settings": {"rules": {"min_clearance": 0.2, "min_copper_edge_clearance": 0.25,
            "min_via_diameter": 0.5, "min_through_hole_diameter": 0.25, "min_via_annular_width": 0.1}}}}))
    return path


if __name__ == "__main__":
    print(create(sys.argv[1]))
