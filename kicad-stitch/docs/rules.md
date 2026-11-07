# Placement rules and research record

Research reviewed November 2026. This document distinguishes what was read from
references identified for later review. Numerical defaults below are engineering
choices unless a source and its applicability are explicitly stated. A passed
KiCad DRC checks the enabled board rules; it does not establish signal integrity,
antenna performance, EMC compliance, isolation in dB or IPC compliance.

## Source-to-rule mapping

| Rule / concern | Source and review status | Implemented consequence | Classification / limits |
| --- | --- | --- | --- |
| Manufacturability: drill, annular ring, clearance, holes and edge spacing | Existing `.kicad_pro` and `.kicad_dru`; [KiCad 10 DRC documentation](https://docs.kicad.org/10.0/en/cli/cli.html#pcb-drc), reviewed | Check diameter/drill minima before planning; evaluate annular width natively; screen geometry conservatively; run native refill/DRC with original rules | Block new issues except explicitly reported annular-width warning advisories on generated vias. Project severities, exclusions and ignored checks retain their semantics |
| Ground continuity | [KiCad zone documentation](https://docs.kicad.org/10.0/en/pcbnew/pcbnew.html); [ViaStitcher README](https://github.com/weirdgyn/viastitcher), reviewed | Use filled copper rather than zone outlines; require at least two ground landing layers; distinguish spacing exclusion from electrical coverage; graph regions and plated bridges; verify again after normal refill | Electrical connectivity requirement, not a guarantee of low RF impedance |
| Differential transitions and reference paths | TI, [High-Speed Interface Layout Guidelines, SPRAAR7J](https://www.ti.com/lit/an/spraar7j/spraar7j.pdf), §2.4 and Fig. 2-11, reviewed | Prioritize symmetric return vias near paired transition vias; leave an obstructed pair unresolved instead of moving just one side; continuous fencing is opt-in | Vendor guidance supports proximity/symmetry. TI's 200 mil maximum applies to that guidance, not a universal tool default. Actual reference-layer changes and power-to-ground reference transitions are not inferred |
| Antenna radiator protection | Infineon, [AN91445, Antenna Design and RF Layout Guidelines](https://www.infineon.com/assets/row/public/documents/cross-divisions/42/infineon-an91445-antenna-design-and-rf-layout-guidelines-applicationnotes-en.pdf), §12, reviewed; TI, [CC3135/CC3235 layout guidelines](https://www.ti.com/lit/ug/swru536/swru536.pdf), antenna placement guidance | Explicit net/component targets; honor board and footprint rule areas and all-pass coordinate exclusions; require manufacturer-specific radiator exclusions | Manufacturer geometry takes priority. A net name cannot establish a safe fence offset or keepout boundary |
| Wavelength-limited stitching and fence pitch | [Altium's stitching/shielding documentation](https://www.altium.com/documentation/altium-designer/pcb/via-stitching-via-shielding), reviewed; cites Armstrong and discusses empirical guidance | Optional maximum significant frequency, dielectric assumption and configurable wavelength divisor; record the resulting pitch bound | Heuristic, not an IPC mandate or a guaranteed shield. Real propagation depends on stackup, field geometry and frequency |
| Separate edge/fence and interior density | [JLC's via-stitching guidance](https://jlcpcb.com/blog/via-stitching), reviewed; [Centola/Makharashvili, IEEE SCV EMC 2019](https://ewh.ieee.org/r6/scv/emc/archive/2019/032019Federico.pdf), slides 8–13, reviewed | Independent pitches; optional λ/10 interior and λ/20 fence/edge bounds; bounded local relocation; measure remaining physical fence intervals | Fabricator heuristics and a simulation-based presentation support role-specific rules, not a universal ratio or proof of EMC performance. The presentation also highlights apertures and limits of edge stitching alone |
| Return current and shared impedance | Analog Devices, [MT-031, Grounding Data Converters and Solving the Mystery of AGND and DGND](https://www.analog.com/media/en/training-seminars/tutorials/MT-031.pdf), reviewed | Ground continuity is evaluated against a chosen reference component; preserve net boundaries and device-specific grounding decisions; avoid treating arbitrary additional copper as automatically beneficial | General grounding context. Automatic capacitor-ground or thermal-via placement is outside this tool's current passes |
| Whole-board density and large unstitched pours | ViaStitcher, above; [RF-tools-KiCAD](https://github.com/easyw/RF-tools-KiCAD), fence implementation inspected | Generate bounded grid samples; supplement uncovered sites per contacted layer; use route-bundle envelope geometry for fences | Geometric coverage heuristic; no claimed published optimum for the board-size density formula |
| Fingers / peninsulas | Local geometric rule motivated by continuity and stub/return-path concerns in the references above | Morphological opening highlights narrow features; require elongated shape; stitch legal portions and report blocked features | Shape heuristic. No source is claimed to standardize its neck-width or aspect-ratio defaults; this is not an antenna or resonance solver |

## Numerical rules actually used

### Via and hole clearance

Through vias cross every enabled copper layer. Obstacles are therefore combined
across those layers before planning. All existing tracks/pads/vias, mechanical
holes, component bodies and protected outer-layer fills are avoided. Existing
ground tracks/pads are still protected against drilling through them.

Internal power-zone fill is mutable by default: native refill creates antipads
around accepted through vias, as described in [JLC's over-stitching discussion](https://jlcpcb.com/blog/via-stitching).
`zone_policy = "avoid"` restores all-zone exclusion; `"antipads"` also permits
outer-layer antipads. Keepouts remain hard constraints. This does not authorize
shorts or lost power-net connections; native regression checks still apply.

The candidate-center margin around copper is:

```text
via_radius + max(configured_clearance, project_global_clearance) + 0.01 mm
```

The 0.01 mm guard covers the adapter's 0.005 mm polygonization tolerance and
rounding. Full landing copper on at least two distinct layers is screened by
inward-buffering ground polygons by `via_radius + 0.01 mm`. Same-net via spacing
also respects configured center spacing and global hole-to-hole minima.
Holes use both copper-to-hole and drill-to-drill constraints. Native DRC evaluates
effective custom/netclass rules afterward; these approximations do not replace it.

### Radial annular width versus via diameter allowance

KiCad's radial annular width is `(D - d) / 2`; fab tables may instead state a
required via diameter difference `D - d`. JLC's [rigid-board capabilities](https://jlcpcb.com/capabilities/pcb-capabilities)
explicitly describe the latter for via sizing. A 0.5/0.3 mm or 0.6/0.4 mm via
therefore has a 0.1 mm radial ring, not 0.2 mm. PTH pad annular-ring specifications
must also be distinguished from the via diameter allowance.

The tool does not reinterpret `min_via_annular_width` as a diameter difference or
change project rules. It defers that check to native DRC so ignored/warning/custom
rule settings take effect. With `allow_annular_width_warnings = true` (default),
new native annular-width **warnings** whose items are exclusively newly generated
vias remain visible as `advisory_issues`; status is `verified_with_warnings`.
Errors, warnings on existing items and every other new rule violation remain
blocking. Strict mode (`false`) rejects new annular-width warnings as well.

### Existing board errors and changed ratsnest endpoints

Baseline errors do not require cleanup before stitching. KiCad's native
[`GetConnectedItems`](https://docs.kicad.org/doxygen/classCONNECTIVITY__DATA.html)
API provides the connected routing-item clusters used to distinguish an existing
disconnection from a different ratsnest representative after refill. For affected
nets, each original non-zone component must remain contained in one final
component. This allows repairs that merge components, while catching any lost
connection even if a separate repair keeps the total component count unchanged.
Only edges between known endpoints that were already disconnected, on a net with
baseline unconnected errors, can be accepted this way. Unknown or zone-only
endpoints are not waived. Raw native DRC reports are retained for audit.

### Automatic pitch

With board material area `A` in mm², the geometric target is:

```text
p_geometry = max(minimum_via_spacing, clamp(sqrt(A) / 10, 2 mm, 10 mm))
```

This targets roughly 100 cells on an ordinary board and is explicitly a local
density default. It is not presented as an electrically optimal grid.

When significant frequency or 10–90% rise time is provided:

```text
f_edge = 0.5 / rise_time_seconds
f_design = max(user_max_significant_frequency, f_edge)  # supplied inputs only
lambda_mm = 299792458000 / (f_design * sqrt(epsilon_r))
p_grid_limit = lambda_mm / grid_wavelength_divisor  # default divisor 10
p_fence_limit = lambda_mm / wavelength_divisor     # default divisor 20
p_grid = min(grid_pitch_mm_or_legacy_pitch_or_p_geometry, p_grid_limit)
p_edge = min(perimeter_pitch_mm_or_max(minimum_spacing, p_grid/2), p_fence_limit)
```

`0.5/tr` is a chosen digital edge bandwidth proxy. It does not identify a sharp
spectral cutoff. The separate default divisors are informed by the fabricator
and shielding guidance above; they are not mandatory design standards. The
default `epsilon_r=4.3` is a configurable
bulk-dielectric assumption, not a measured stackup or calculated microstrip
effective permittivity. All three assumptions appear in the JSON report.

For a 2.4 GHz significant frequency and εr=4.3, λ/10 is approximately 6.02 mm and
λ/20 is 3.01 mm. For a 0.1 ns rise time, the edge proxy is 5 GHz and those limits
are approximately 2.89 mm and 1.45 mm. A requested pitch below legal spacing is rejected; it is never silently
relaxed while claiming to satisfy the electrical target.

Explicit per-signal pitch can request a denser fence. It must not exceed the
applicable board electrical bound, and actual obstacles can still create gaps.

Without frequency inputs, the default edge target is half the interior target,
the signal-fence target inherits the edge target, and the finger target is the
smaller of edge pitch and twice the configured neck width. Legal minimum spacing
still applies. These are explicitly local geometric-density choices, not
electrically optimized defaults. Each role has its own explicit pitch override.

### Connectivity and missing islands

Native KiCad temporarily retains otherwise removed ground islands on a scratch
copy. The planner unions same-layer ground zones/tracks/pads into regions and
joins regions only through existing plated pads/vias or accepted proposed vias.
Overlap at the same XY across two layers alone does not connect them.

The default reference is the existing connected component with the largest
aggregate copper area. Explicit anchors must already identify one connected
component. Repair grows outward from that reference through legal cross-layer
overlaps, including multi-step connections. Two floating regions stitched only
to one another do not satisfy the reference-ground requirement.

The final board uses the original zone policies. After native refill, every
accepted via must land on ground copper on two layers and reach the same
reference component. Through-via pads are omitted from the landing model so a
via cannot demonstrate its own contact. A void caused by a keepout, conflicting
net, higher-priority pour or insufficient copper width is not recoverable merely
by adding a via; it stays unresolved.

Spacing exclusions are subtracted from the legal overlap before selecting a
site. GEOS's [maximum-inscribed-circle search](https://shapely.readthedocs.io/en/stable/reference/shapely.maximum_inscribed_circle.html)
finds small off-grid remainders that centroid/lattice sampling can miss. The final
audit intersects each exploratory island with surviving reference-connected
copper, distinguishing recovery from removal by the normal fill policy. Narrow
landings, absent layer overlap, copper/component/keepout clearance, signal offset
and spacing/budget limits are reported separately.

### Perimeter and signal paths

Perimeter targets are equally spaced along an inward offset of actual Edge.Cuts,
including internal cutouts and concave outlines. The target center offset is at
least the specified edge clearance plus via radius. Around an obstacle the planner
intersects the contour with legal geometry and moves to a nearby legal station.
If necessary it searches a bounded inward band. Local movement is limited by
`search_radius_mm` and half the role's pitch. These are engineering search bounds,
not published electrical constants. Actual remaining contour intervals are
measured and gaps above 1.25 times the target pitch are reported; that 25% audit
allowance is a geometric reporting tolerance, not an electrical relaxation of λ/20.

Signal fences follow the buffered envelope of all selected routes per layer.
The chosen offset means **track centerline to via center**, not copper-edge gap.
For net-assigned pads and custom copper shapes, including footprint-based PCB
antennas, it is measured from the copper boundary instead.
Bundling both pair members prevents a fence down the gap between them. That
offset also protects the signal corridor from other placement passes. Differential
transition matching uses two selected nets (recognized suffixes or explicit
`differential = true`), matching via spans and nearby XY
positions; net suffixes and proximity are hints that must be reviewed. The tool
does not know the exact intended stackup reference or solve the resulting
transmission-line impedance.

At transitions the pair can rotate together about its midpoint and move outward
in bounded increments, preserving symmetry. Signal fences can move along their
offset boundary and outward into legal sites. Reports retain desired positions
and measured displacement, and list nearby ground contacts for each transition.
Existing return contacts and inability to fit another symmetric pair require
review rather than an assumption that every transition must receive two new vias.

### Fingers and coverage

A morphological opening at half `neck_width_mm` removes narrow appendages.
Elongated removed areas with aspect ratio ≥3 and area ≥`diameter_mm²` are flagged.
Only reference-connected copper is evaluated here; floating regions are handled
by the island pass and its recovery/removal audit.
The algorithm works from distal tips along the feature's long axis and uses a
separate finger pitch. An existing via counts only if it contacts that feature
on the relevant layer; a nearby via across a slot does not serve it.

Interior targets use a square or staggered lattice only as nominal positions.
Local legal polygons and spacing exclusions determine actual placement, bounded
by `search_radius_mm` (default half the interior pitch). Continuous per-layer
polygon subtraction then finds uncovered legal pockets, with maximum-inscribed
centers as supplemental targets. Nominal coverage radius is `p/sqrt(2)` for square
and `p/sqrt(3)` for staggered patterns, with 0.1 mm geometric audit tolerance.
The final native board is re-audited after any candidate rejection. This measures
Euclidean geometric coverage; it does not prove return-path inductance or EMC
performance. Curved or wide poorly connected peninsulas can evade the finger
classifier. Features too
narrow to accommodate a legal through via are reported; rerouting, removing
copper or changing the stackup can be the appropriate remedy.

## Books, papers, presentations and standards

These are useful foundations and follow-up references, with access limits stated.

| Reference | Relevance | What was reviewed here |
| --- | --- | --- |
| Henry W. Ott, [Electromagnetic Compatibility Engineering](https://www.wiley.com/en-us/electromagnetic-compatibility-engineering-p-9781118210659); [Ch. 16, PCB Layout and Stackup](https://onlinelibrary.wiley.com/doi/10.1002/9780470508510.ch16) | Grounding, planes, stackup and EMC | Publisher information/chapter listing, not full book text; no numerical default attributed to an unseen passage |
| Eric Bogatin, [Signal and Power Integrity—Simplified, 3rd ed.](https://www.pearson.com/en-us/subject-catalog/p/signal-and-power-integrity---simplified/P200000000140?view=educator) | Return paths, bandwidth, interconnects and plane behavior | Publisher description and available contents, not full book text |
| Howard Johnson and Martin Graham, [High-Speed Digital Design: A Handbook of Black Magic](https://highspeeddigitaldesign.com/books/bookHSDD.html) | Returning signal current and via parasitics | Author's indexed overview identifies the relevant material; full chapters not reviewed |
| Keith Armstrong, [PCB design and layout techniques for lowest-cost EMC compliance, and signal integrity](https://www.emcstandards.co.uk/files/pcb_layout_techniques_for_low-cost_emc_iee_review_august__october_1999.pdf), IEE articles, 1999 | Primary engineering background for plane bonding and EMC-oriented layout | Located author paper; detailed numerical attribution should be checked against its exact section before elevating a heuristic to a rule |
| Eric Bogatin, [Signal Integrity of Sockets—Simplified, BiTS 2005 tutorial](https://www.testconx.org/archive/archive2005/bits2005_tutorial_bogatin.pdf) | Presentation discussing current distributions and loop inductance | Located presentation/available extract; useful conceptual context rather than a universal via-spacing table |
| IPC-2221 / IPC-2222 | Generic and rigid-board design | Identified through [IPC's reference list](https://www.ipc.org/media/4923/download); full standards not accessed |
| IPC-2141 / IPC-2251 / IPC-2252 | Controlled impedance, high-speed and RF/microwave design | Identified through the same IPC list; no clause-level compliance claim |

## Existing software and reuse decision

- [ViaStitcher](https://github.com/weirdgyn/viastitcher): MIT-licensed repository;
  its documented per-island and per-layer contact checks, minimum spacing, and
  adaptive fill are directly relevant prior work. The current implementation
  uses independent code; future selective reuse should pin a revision and retain
  its license/attribution.
- [RF-tools-KiCAD via fence generator](https://github.com/easyw/RF-tools-KiCAD/tree/master/via_fence_generator):
  inspected path-offsetting, bend handling and spacing concepts. The inspected
  `viafence.py` has a GPLv3 header. No source is copied into this Apache-2.0 repo.
- [KiCad native geometry and fill](https://docs.kicad.org/doxygen-python-10.0/):
  reused as the runtime authority for outlines, pads, tracks, hole geometry and
  copper fills. Fractured fill polygons are restored with native `Unfracture()`
  before conversion, preserving holes without speculative polygon repair.
- [Shapely](https://shapely.readthedocs.io/): used for polygon offsets, unions,
  intersections, maximum-inscribed-circle placement, continuous coverage, line
  sampling and shape classification. No additional skeleton
  library is necessary for this first classifier. A medial-axis/graph analysis
  and an external field solver would be useful extensions for more complete
  peninsula detection and electrical evaluation.

Future work should include explicit reference layers and interface presets
validated against device guidelines, stackup-derived
electrical inputs, and regression boards with simulation/measurement results.
