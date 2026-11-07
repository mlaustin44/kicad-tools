"""Dependency-free SVG preview for reports and future GUI overlays."""
from html import escape

from .geometry import decode


COLORS = {"island": "#e69f00", "transition": "#cc79a7", "perimeter": "#56b4e9",
          "signal_fence": "#d55e00", "finger": "#f0e442", "grid": "#009e73", "coverage": "#ffffff"}


def svg(snapshot, result, settings):
    bounds = decode(snapshot["outline"]).bounds
    x, y, right, bottom = bounds
    parts = [f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="{x-2} {y-2} {right-x+4} {bottom-y+4}" width="1200" role="img">',
             f'<title>Ground stitching preview: {escape(result.validation["status"])}</title>',
             '<rect x="-100000" y="-100000" width="200000" height="200000" fill="#141923"/>']

    def paths(polys, color, opacity, stroke="none"):
        for poly in polys:
            rings = [poly["shell"], *poly.get("holes", [])]
            d = " ".join("M " + " L ".join(f"{px},{py}" for px, py in ring) + " Z" for ring in rings)
            parts.append(f'<path d="{d}" fill="{color}" fill-opacity="{opacity}" fill-rule="evenodd" stroke="{stroke}" stroke-width="0.08"/>')

    paths(snapshot["outline"], "#252e3c", 1, "#afbdcf")
    for polys in snapshot["ground"].values():
        paths(polys, "#33875c", 0.15)
    for obstacle in snapshot["obstacles"]:
        paths(obstacle["polygons"], "#ad7dba" if obstacle["kind"] == "keepout" else "#c47d7d", 0.3)
    for fp in snapshot["footprints"]:
        paths(fp["polygons"], "#8190a5", 0.4)
    generated = {c.uuid for c in result.candidates if c.uuid}
    for via in snapshot["existing_vias"]:
        if via.get("uuid") in generated:
            continue
        vx, vy = via["at"]
        parts.append(f'<circle cx="{vx}" cy="{vy}" r="0.2" fill="#aab6c7"><title>Existing via: {escape(via["net"])}</title></circle>')
    for candidate in result.candidates:
        title = escape(f"{candidate.rule}: {candidate.reason}; {candidate.x}, {candidate.y} mm; {', '.join(candidate.layers)}; target shift {candidate.displacement_mm:.3f} mm")
        parts.append(f'<circle cx="{candidate.x}" cy="{candidate.y}" r="{settings.diameter_mm/2}" fill="{COLORS[candidate.rule]}"><title>{title}</title></circle>')
        parts.append(f'<circle cx="{candidate.x}" cy="{candidate.y}" r="{settings.drill_mm/2}" fill="#141923"/>')
    for rejected in result.validation.get("rejected_candidates", []):
        rx, ry = rejected["x"], rejected["y"]
        title = escape(f'Rejected {rejected["rule"]}: {rejected["rejection"]}')
        parts.append(f'<path d="M {rx-.25},{ry-.25} L {rx+.25},{ry+.25} M {rx-.25},{ry+.25} L {rx+.25},{ry-.25}" stroke="#ff7474" stroke-width="0.08"><title>{title}</title></path>')
    parts.append("</svg>")
    return "\n".join(parts)
