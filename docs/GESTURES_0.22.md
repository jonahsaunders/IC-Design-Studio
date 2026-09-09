# Path snapping and navigation — 0.22.0.dev8

Choose **Grid + objects** in the layout options. Both **Path** and **Route with cursor** use it; **Grid only** disables object snapping. The canvas starts with object snapping enabled.

## Object snapping

- All rectangle corners, edge midpoints and centers; polygon vertices and edges, including hole edges.
- Existing path endpoints, bends and centerline segments, including rotated or mirrored instances and regular arrays.
- Physical pins and ports. Hidden layers are excluded. Locked and unselectable visible objects remain usable as geometric references without being modified.
- A square marker identifies the exact target; its label shows the feature and layer. Anchors within six screen pixels take priority, followed by the closest feature within eight pixels. Coincident targets prefer the active layer. The tolerance stays the same on screen as you zoom.
- Targets must lie on the project manufacturing grid. Slanted edges use their nearest exact grid point; snapping never rounds a projected point away from its edge. An edge with no eligible nearby grid point falls back to ordinary grid snapping.

A snap onto another layer is a geometric reference. The path retains its selected layer and net; use the via tools or reviewed cursor-route result for a connection between layers. Snapping does not certify clearance or connectivity. Path preview and committed bend points use the same snapped coordinates.

## Panning while drawing

Use the middle mouse button, or hold Space and drag with the left button in the layout canvas. Navigation has a separate screen-space anchor. Existing model-space points and the current preview stay fixed to the design while the view moves. Move the pointer after panning to continue the preview.

A middle-button double-click cannot finish a path. Middle release cannot commit a rectangle, ruler or vertex edit. If a held left-button drawing drag is released while the middle button is still panning, that drag is cancelled; click-by-click path points remain available. Releasing Space before the left mouse button still ends the pan cleanly when the mouse is released. Escape clears the gesture and focus loss ends panning.

## Implementation and checks

Object lookup uses spatial queries for both shapes and terminals. Native hierarchy snap queries use the exact cursor window and leave the viewport cache intact, avoiding a full overview rebuild on each pointer move. No saved project schema or geometric ownership is changed.

Run `python -m unittest discover -s tests -p test_layout_snap.py` for the geometry regressions, including an exhaustive finite-grid oracle over 600 deterministic segments. Run `python tests/gui_layout_gestures.py --out build/gui-gestures` for real Qt input events, screenshots, preview/commit comparison, hidden and locked layers, transformed routes, eight-tool panning, Space navigation, interrupted gestures, schematic wires and the complete Studio snapping control.

`python scripts/benchmark_layout_snapping.py --out build/snapping.json` measures local snap lookup at 1,000 and 10,000 shapes, with the same number of terminals, for flat geometry and native arrays. It checks target correctness and cache retention. Setup, painting, edit commits and recovery are excluded; these are not frame-rate or whole-editor timings.

This source preview retains the [dev7 performance changes](STABILITY_0.22.md). Their recorded timings belong to the historical dev7 source. The host synchronized-write failure and native Windows/display qualification remain open; no new portable binary is included.
