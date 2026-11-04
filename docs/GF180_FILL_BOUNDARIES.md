# Declared GF180 fill boundaries

The supplemental fill checker accepts an optional `--boundary-plan` JSON file.
It checks the actual written dummy polygons against explicitly declared prime
die, scribe, frame and SLM test regions. It does not derive a scribe line from
the implementation footprint, core, layout extent or guard-ring marker.

The plan is bound to the exact GDS and a retained floorplan source. Source
hashes establish identity, not correctness or completeness of the declaration.
An independent review must still reconcile the declaration with the complete
chip, reticle and package requirements. A passing boundary report does not
qualify fill, a process, or a tapeout.

## Format

Schema 1 requires exactly these top-level fields:

| Field | Required value |
|---|---|
| `schema` | Integer `1`. |
| `gds_sha256` | SHA-256 of the exact input GDS. |
| `top` | The input's declared top cell name. |
| `floorplan_source` | Object with `file` and `sha256`. The file is read relative to the plan's directory; its bytes must match the supplied hash. |
| `regions` | Nonempty list of objects with a unique `name`, a `kind` and `bounds_nm`. |
| `scribe_boxes_nm` | Nonempty list of rectangular scribe areas, merged before checking distances. These can extend outside the layout footprint. |
| `frame_cells` | List of objects with `bounds_nm` and an explicit boolean `non_et`. Include all frame cells; only those explicitly classified as non-ET receive the DCF.7c exception. Use an empty list when there are no frame cells. |

Every rectangle is `[left, bottom, right, top]` in integer nanometres, with
positive width and height. At most 10,000 rectangles may be declared in total.
Region kinds are `prime_die`, `frame`, `slm_etest` and `slm_reliability`.
Regions must have disjoint interiors and lie inside the original fixed layout
footprint. Prime-die regions cannot overlap scribe material; frame and SLM
regions must lie inside it. Frame-cell footprints must be disjoint and wholly
inside declared frame regions. Unsupported shapes or inconsistent declarations
are rejected rather than approximated by a bounding box.

Every actual dummy COMP/poly polygon must lie wholly inside one declared
region. A polygon crossing a boundary fails coverage, including when it crosses
the common edge of two adjacent regions. It is never clipped to gain a pass.
Dummy poly outside prime die is rejected under the declared DPF.1 scope.

## Implemented distances

| Rule | Operand and minimum distance |
|---|---|
| DCF.7a | Prime-die dummy COMP to declared scribe material: 26 micrometres. |
| DPF.7 | Prime-die dummy poly to declared scribe material: 25.7 micrometres. |
| DCF.7b | Frame dummy COMP to all edges of its declared frame rectangle: 6 micrometres. |
| DCF.7c | Frame dummy COMP to declared frame-cell footprints other than non-ET: 10 micrometres. |
| DCF.7d | SLM Etest/reliability dummy COMP to all edges of its declared test rectangle: 6 micrometres. |

Separation uses Euclidean distance and explicitly detects overlap. The pinned
main table gives DCF.7a as 26 micrometres while its appendix gives 8 micrometres.
The checker records both and enforces 26, satisfying both numeric minima without
inferring a waiver. Sources are pinned in the [fill-pattern lock](../examples/gf180-fill-pattern-lock.json)
and [boundary lock](../examples/gf180-boundary-manual-lock.json).

Pass the plan alongside the fixed footprint and any drawing recipe:

```sh
python scripts/check_gf180_fill.py --gds final.gds --top chip --bounds 0 0 400 400 --variant C --boundary-plan boundary.json --output boundary-report.json
```

The coordinates above are illustrative, not a replacement for the design's
original footprint. Existing reports are never overwritten. A failed check
returns exit code 1; a passing implemented subset returns 2 with
`qualified: false`. Without a declaration, the report explicitly records
`missing_boundary_plan`. The existing counter has no accepted boundary
declaration and retains that status.

Remaining requirements include floorplan completeness, guard-ring geometry and
connectivity, reticle/package acceptance, empty-field and local-density coverage,
exclusion-edge rows, complete native checks and post-fill electrical performance.
See the [qualification plan](PDK_QUALIFICATION_PLAN.md) for the full gate.
