# Grid and drawing — 0.22.0.dev9

## Grid controls

Open **View → Grid Settings**, or click the **Grid** button below the canvas. Layout settings include:

- **Snap to grid** on/off. The same toggle is available in the View menu and drawing options. Grid snapping starts enabled.
- **Visible grid — follows zoom** (default): rectangle corners and ordinary drawing points land on the displayed lattice. Spacing adapts with zoom. Starting a rectangle, path or polygon freezes that drawing's grid until completion or cancellation, so pan/zoom cannot change its coordinates midway through a shape.
- **Fixed spacing**: enter micrometres, for example `0.05` for 50 nm. Spacing must be positive, in whole nanometres and a multiple of the active process grid. It stays fixed when zoom changes. The display may thin the visible grid at distant zoom; the footer shows both snap and visible spacing.
- Lines, dots or a hidden grid; contrast; minimum spacing on screen; major-line interval; and origin emphasis. Hiding the grid does not turn snapping off.

Preferences persist for the layout editor and named workspaces. A different process may require rounding an old fixed-step preference to a valid process-grid multiple. Changes made during an unfinished drawing apply to its next shape. Schematic placement keeps its existing 10-unit connection grid.

With snapping off, free layout geometry uses the database's 1 nm resolution. Process rules and specialized operations still apply their own manufacturing-grid requirements. The **Objects on/off** control separately enables path/cursor-route geometry targets. Object targets can override drawing-grid spacing; their marker names the exact feature and layer. Snapping to another layer does not automatically create a via.

## Rectangles

Choose a layer, select **Rectangle**, and either drag between opposite corners or click the two corners. A first click keeps the rectangle preview active while you choose the second corner. Escape cancels. Zero-area and rejected rectangles remain editable. Default snapping places both corners on the visible grid.

## Paths

1. Choose the layer, path width and optional net in the drawing options.
2. Select **Path** and click its starting point.
3. Move the pointer to preview the path at its actual width. Click to place intermediate endpoints/bends.
4. **Double-click the final endpoint** to create the path. Alternatively, press **Enter while pointing at the endpoint** to include that preview endpoint and finish.

**Finish** in the options completes at the last clicked point; it enables after enough points have been placed. An incomplete finish request keeps the draft and tells you what is missing. Enter with only a start point and a distinct pointer position now creates the previewed path.

In Manhattan mode, **Tab** or **Flip bend** switches horizontal/vertical bend order. **Backspace** or **Undo point** removes the last click and its automatically inserted bend. **Free angle** allows direct segments. **Escape** cancels the draft. Middle-button or Space-drag pans without changing placed points. The stronger stroke marks placed segments; the faint stroke and dashed centerline show the unplaced pointer segment.

A failed rule, locked-layer, invalid-net or document commit keeps the path draft and displays a reason in the drawing instructions. Fix the setting and finish again. Geometry enters the ordinary history transaction; undo/redo retains its exact coordinates and identity. Successful recovery and worker writes still use the existing durable-save routines.

## Validation and scope

`python -m unittest discover -s tests` runs the unit/integration suite. `python tests/gui_grid_paths.py --out build/gui-grid-paths` drives actual Qt mouse/key events and the complete Studio window, including rectangle snap/unsnap, pan/zoom, path preview/finish, Tab routing through the main window's event filters, invalid-input retention, document commits and exact undo/redo. Narrow-window control wrapping and both themes have screenshot coverage.

The earlier gesture, geometry-cache and pipeline tests remain available. `python scripts/check_layout_storage.py --out build/storage` exercises real fsync, recovery roundtrip and previous-snapshot fallback. Current reports accompany this handoff. Older dev7/dev8 benchmark numbers remain historical; this build does not establish a native-display performance comparison with another editor. Native Windows/macOS and external process qualification still require their own runs.
