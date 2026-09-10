# IC Design Studio 0.14 — a workspace for drawing

Both editors now have clear line grids. The crowded Design menu has become a short set of cell/project commands, with separate Schematic, Layout, Route, Simulate and Verify menus. A Draw / Edit / Review strip exposes frequent operations as named buttons. Window is the place to arrange panels, save a workspace, or recover the default layout.

## Start here

1. Open a project. Schematic and Layout tabs switch editors; Linked views shows both.
2. Use **Draw → Component** to open the device library, or **Draw → Wire** to connect pins. In Layout, use Rectangle, Polygon, Path, Via or Cell. Commands show a preview; click to place and use Esc to cancel. Undo remains Ctrl+Z.
3. Click **Grid** at the bottom of the canvas to choose Lines, Dots or Hidden, adjust contrast/spacing and emphasize the origin. Settings are separate for schematic and layout. **Ctrl+Shift+G** toggles the active editor's visible grid.
4. Use **Window → Configure windows** or the **Workspace** toolbar button to show/hide and position Project, Inspector and Results. Drag panel titles to dock them; use the arrow button or double-click the title to float/redock.
5. Choose Schematic, Layout, Simulation or Review presets. Save a named arrangement after customizing it. **Window → Reset workspace** returns to the schematic workspace. **Ctrl+Shift+F** temporarily focuses the canvas.

## Grids that mean something

The visible grid starts from the same lattice used by placement: 10 schematic units, or the active technology's layout grid in nanometres. As you zoom out, the renderer displays whole multiples of that lattice. It does not move existing objects or change placement precision. Every fifth visible interval is stronger, and origin axes provide orientation when panning through negative coordinates.

The footer distinguishes **Grid** (the displayed interval) from **Snap** (the actual placement interval). Hiding the grid leaves snapping and electrical hotspots intact. Physical layout continues to obey the technology grid. Appearance preferences are saved on this computer and included in named workspaces; the project schema and PDK locks remain unchanged.

## Where commands live

| Menu | Purpose |
|---|---|
| File | Open/save, imports, exports and example designs |
| Edit | Undo/redo, duplicate, rotate, delete and command search |
| View | Zoom, fit, theme, grid and editor selection |
| Design | Cells, hierarchy entry point and project settings |
| Schematic | Placement, capture editing, symbols and annotations |
| Layout | Drawing, geometry editing, physical cells and generation |
| Route | Vias, physical terminals, routing and wire repair |
| Simulate | Runs, saved testbenches, noise and studies |
| Verify | Electrical/geometry checks, cross-probe and physical verification |
| Tools | Engine configuration, keyboard profiles and technology management |
| Window | Panels, saved workspaces, presets, focus and linked-view arrangement |
| Help | Searchable help, shortcuts, workspace guide and release information |

Menus use at most one submenu level. Specialized imports, symbols and geometry remain grouped; common commands are directly reachable. Duplicate entries for electrical checking and cross-probing have been consolidated. The complete original command set remains available. Ctrl+K searches the new categories and the original actions retain their keyboard bindings.

Draw contains everyday creation tools, Edit contains transformations, and Review contains inspection/checking tools. The strip changes with the active editor, including when you click between linked canvases. Labels remain visible in compact windows; controls wrap when necessary. Tool options appear only when relevant, and right-click menus expose a short list of local actions. Results views scroll within their panel so large tables and toolbars cannot cover the Inspector.

## Workspaces and recovery

Panels can dock on any edge, float, resize, or form tabbed groups using Qt's native docking. Lock panel positions when the arrangement is comfortable. Schematic/Layout presets hide Results; Simulation shows analysis settings and waveforms; Review shows linked editors and checks. Linked views can be side by side or stacked. Named workspaces store dock state, split orientation/sizes, selected panel tabs, command tab, grid appearance, filters and keyboard profile. The last arrangement is restored after a normal close. Previous 0.13 workspace records remain readable. UI settings remain separate from design transactions. An invalid property draft blocks a workspace change until it is corrected or reset.

The three existing panel groups remain intact: Project contains Project / Devices / Layers; Inspector contains Properties / Analysis; Results contains the result views. Individual tabs are not independent floating windows. This release adds configurable panel groups, not an arbitrary multi-document window manager.

## Interaction principles

Visible placement grids, context-specific commands, saved panel arrangements and direct manipulation support predictable engineering work. The grid footer distinguishes visible spacing from electrical snapping. Neutral backgrounds and a restrained accent keep circuit geometry prominent. Labeled controls, clear cancellation and editable numeric fields make actions discoverable and reversible.

## Verification and remaining evaluation

The new native Qt driver (`tests/gui_overhaul.py`) covers command preservation/menu depth, raster grid alignment, negative pan offsets, extreme zooms, unchanged snapping, grid controls/shortcuts, actual placement and drawing, Undo, floating/docking, panel locks, reset, named/legacy/session restoration, invalid drafts, linked-editor focus and compact ribbon/result bounds. Screenshots use actual example designs in both themes. Existing model and native editing suites are retained. Executed results are recorded in the handoff's current verification directory.

Tests run offscreen on the build host. They do not establish physical display, multi-monitor, assistive-technology or fresh-Windows acceptance. A useful human evaluation is to ask experienced and occasional designers to place/connect a component, repair a wire, draw/inspect geometry, compare views, float a panel, save a workspace and recover it. Record discovery errors, unintended commands, lost drafts and requests for help. The engineering limits in the earlier capability matrix continue to apply.

