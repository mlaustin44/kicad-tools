"""SVG template loading and substitution.

Two mechanisms:
- Text placeholders: {{NAME}} strings inside <text>/<tspan> elements get replaced.
- Region rectangles: <rect id="NAME" x="..." y="..." width="..." height="..."/>
  defines a content area; the tool removes the rect and inserts rendered content.
"""
from __future__ import annotations
import re
from dataclasses import dataclass
from lxml import etree

SVG_NS = "http://www.w3.org/2000/svg"
NSMAP = {"svg": SVG_NS}
PLACEHOLDER_RE = re.compile(r"\{\{([A-Z][A-Z0-9_]*)\}\}")


@dataclass
class Region:
    id: str
    x: float
    y: float
    width: float
    height: float


def _walk_text_elements(root):
    """Yield every <text> and <tspan> element and direct text children."""
    for tag in ("text", "tspan"):
        for el in root.iter(f"{{{SVG_NS}}}{tag}"):
            yield el


def substitute_text_placeholders(svg_bytes: bytes, vars_: dict[str, str]) -> bytes:
    """Replace {{NAME}} strings in text/tspan element text content."""
    root = etree.fromstring(svg_bytes)
    found: set[str] = set()
    for el in _walk_text_elements(root):
        if el.text:
            def repl(m):
                key = m.group(1)
                found.add(key)
                if key in vars_:
                    return vars_[key]
                return m.group(0)  # leave alone
            new_text = PLACEHOLDER_RE.sub(repl, el.text)
            el.text = new_text
        # also scan tail text? probably not — placeholders should live inside elements.
    unknown = found - set(vars_.keys())
    for u in sorted(unknown):
        print(f"warning: SVG template references unknown placeholder {{{{{u}}}}}, "
              f"left as literal text")
    return etree.tostring(root, xml_declaration=True, encoding="utf-8")


def find_regions(svg_bytes: bytes, ids: list[str]) -> dict[str, Region]:
    """Return {id: Region} for any <rect id="..."> in the template matching ids."""
    root = etree.fromstring(svg_bytes)
    out: dict[str, Region] = {}
    for rect in root.iter(f"{{{SVG_NS}}}rect"):
        rid = rect.get("id")
        if rid and rid in ids:
            out[rid] = Region(
                id=rid,
                x=float(rect.get("x", "0")),
                y=float(rect.get("y", "0")),
                width=float(rect.get("width", "0")),
                height=float(rect.get("height", "0")),
            )
    return out


class SvgTemplate:
    """Mutable in-memory SVG template for composition."""

    def __init__(self, svg_bytes: bytes):
        self.tree = etree.fromstring(svg_bytes)

    def substitute_text(self, vars_: dict[str, str]) -> None:
        new_bytes = substitute_text_placeholders(
            etree.tostring(self.tree, xml_declaration=True, encoding="utf-8"), vars_
        )
        self.tree = etree.fromstring(new_bytes)

    def find_regions(self, ids: list[str]) -> dict[str, Region]:
        return find_regions(
            etree.tostring(self.tree, xml_declaration=True, encoding="utf-8"), ids
        )

    def replace_region(self, region_id: str, content_element) -> None:
        """Remove the rect with the given id, append the content element in its place.

        The content element's positioning is the caller's responsibility — typically
        the caller wraps content in a <g transform="translate(x,y) scale(...)"> sized
        to the region's bounding box.
        """
        for rect in self.tree.iter(f"{{{SVG_NS}}}rect"):
            if rect.get("id") == region_id:
                parent = rect.getparent()
                idx = list(parent).index(rect)
                parent.remove(rect)
                parent.insert(idx, content_element)
                return
        # Region not found — caller should have warned before calling

    def serialize(self) -> bytes:
        return etree.tostring(self.tree, xml_declaration=True, encoding="utf-8",
                              pretty_print=False)
