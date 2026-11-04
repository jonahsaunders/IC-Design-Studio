# Declared GF180 dummy-fill patterns

The supplemental checker verifies written dummy polygons against an explicit
staggered-array recipe. It checks the complete array phase, including when
blockages remove different sites. A passing pattern check does not establish
empty-field coverage, global or local density, boundary acceptance, connectivity
or post-fill electrical performance.

## Recipe and adjacent metal layers

Use schema 1 and `alternating-stagger-v1`. Each actual dummy layer needs an
`origin_nm` coordinate pair on the 5 nm grid and a `stagger_sign` pair with each
value either `1` or `-1`. Supported names are `comp`, `poly` and `m1` through
`m5`. The checker fixes the square dimensions, pitch and stagger from the
[pinned manual and figures](../examples/gf180-fill-pattern-lock.json).

For metal, the recipe uses 2 micrometre squares, 3.2 micrometre pitch and
0.5 micrometre alternating stagger in each direction. It keeps the drawing
space separate from the smaller Euclidean spacing used by DRC.

For two consecutive metal layers, the checker recognizes a translation of
exactly 500 nm along either axis, in either direction. This is one explicit
implementation of the manual's DM.9 offset. All four periodic phases must
translate together; matching only the origins or remaining polygons cannot
establish the relationship. Each layer's actual polygons must first pass its
declared recipe. Translated origins, negative array indices, cardinal rotations
and reflections are supported.

```json
{
  "schema": 1,
  "recipe": "alternating-stagger-v1",
  "layers": {
    "m1": {"origin_nm": [1600, 1600], "stagger_sign": [1, 1]},
    "m2": {"origin_nm": [2100, 1600], "stagger_sign": [1, 1]}
  }
}
```

The example declares a positive-x 500 nm offset. It does not place fill or
approve those coordinates for a particular design. Independent clearances and
the original footprint still apply.

Exact replicas fail even when their occupied sites differ. Other nonreplicated
arrangements, including diagonal translations, stay explicitly unqualified by
this selected recipe. A 495 nm or 505 nm shift cannot receive its axial-offset
pass. This does not classify every alternative arrangement as a foundry
violation or infer unspecified tolerances.

## Evidence and remaining gates

The [adjacent-pattern checkpoint](validation/gf180-adjacent-patterns-2026-10-09.json)
records written-GDS controls on Windows and Linux and replays the six retained
C/D counter, UART and APB filled layouts. Those references contain only Metal1
dummy squares; their 104 implemented checks and incomplete coverage are
unchanged. They cannot establish adjacent-layer behavior themselves, which is
covered by the separate written coupons and fault controls.

The checker continues to return an incomplete qualification result even when
all implemented checks pass. Complete fill acceptance and the later PDK gates
remain in the [qualification plan](PDK_QUALIFICATION_PLAN.md). Declared chip
boundaries have their [own source-bound format](GF180_FILL_BOUNDARIES.md).
