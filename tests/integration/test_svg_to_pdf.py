"""Integration test for SVG → PDF conversion."""
from __future__ import annotations
from release_generator.svg_to_pdf import convert


def test_simple_svg_round_trips_to_pdf(tmp_path):
    svg = tmp_path / "input.svg"
    svg.write_text("""<?xml version="1.0"?>
<svg xmlns="http://www.w3.org/2000/svg" width="100" height="100">
  <rect x="10" y="10" width="80" height="80" fill="blue"/>
  <text x="50" y="50" text-anchor="middle">Hello</text>
</svg>""")
    pdf = tmp_path / "out.pdf"
    convert(svg, pdf)
    assert pdf.exists()
    assert pdf.read_bytes()[:4] == b"%PDF"
