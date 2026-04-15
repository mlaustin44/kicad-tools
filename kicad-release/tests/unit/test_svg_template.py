"""Unit tests for SVG template substitution."""
from __future__ import annotations
import pytest
from lxml import etree
from release_generator.svg_template import (
    SvgTemplate, Region, substitute_text_placeholders, find_regions
)


SVG_NS = "http://www.w3.org/2000/svg"
NSMAP = {"svg": SVG_NS}


def _svg_with(body: str) -> bytes:
    return f'<?xml version="1.0"?><svg xmlns="{SVG_NS}" width="100" height="100">{body}</svg>'.encode()


def test_substitute_simple_placeholder():
    src = _svg_with('<text>{{REV}}</text>')
    out = substitute_text_placeholders(src, {"REV": "3.2"})
    root = etree.fromstring(out)
    text_el = root.find("svg:text", NSMAP)
    assert text_el.text == "3.2"


def test_substitute_in_tspan():
    src = _svg_with('<text><tspan>Rev: {{REV}}</tspan></text>')
    out = substitute_text_placeholders(src, {"REV": "3.2"})
    root = etree.fromstring(out)
    tspan = root.find("svg:text/svg:tspan", NSMAP)
    assert tspan.text == "Rev: 3.2"


def test_missing_placeholder_left_alone_with_warning(capsys):
    src = _svg_with('<text>{{UNKNOWN}}</text>')
    out = substitute_text_placeholders(src, {"REV": "3.2"})
    root = etree.fromstring(out)
    text_el = root.find("svg:text", NSMAP)
    assert text_el.text == "{{UNKNOWN}}"
    captured = capsys.readouterr().out
    assert "UNKNOWN" in captured


def test_find_named_region_rect():
    src = _svg_with(
        '<rect id="board-view" x="10" y="20" width="40" height="30"/>'
        '<rect id="other" x="0" y="0" width="5" height="5"/>'
    )
    regions = find_regions(src, ids=["board-view", "drill-table"])
    assert "board-view" in regions
    assert "drill-table" not in regions
    r = regions["board-view"]
    assert (r.x, r.y, r.width, r.height) == (10.0, 20.0, 40.0, 30.0)


def test_region_rect_removed_when_replaced():
    src = _svg_with('<rect id="board-view" x="0" y="0" width="50" height="50"/>')
    tpl = SvgTemplate(src)
    tpl.replace_region("board-view",
                       etree.Element(f"{{{SVG_NS}}}g", id="content"))
    out = tpl.serialize()
    root = etree.fromstring(out)
    assert root.find('svg:rect[@id="board-view"]', NSMAP) is None
    assert root.find('svg:g[@id="content"]', NSMAP) is not None
