# IC Design Studio — desktop interface redesign

Version 0.2.0 · September 2026

## What went wrong in 0.1.0

The first interface exposed implementation capabilities without sufficiently designing the user's tasks. Its visual hierarchy, editing model, and feedback were weak. A color change alone would not resolve those problems.

The audit identified these concrete failures:

- One global toolbar mixed undo, device placement, connection mode, layout layers, simulation, and cancellation. Layout controls remained present during schematic work.
- Editor switching and active-cell navigation depended on adjacent dropdowns. Their roles were not clear at a glance.
- The inspector presented device IDs and geometry arrays directly. Common electrical values competed with position and internal metadata.
- Placing a component immediately inserted it at the viewport center, rather than allowing the user to choose its position.
- Dragging offered no movement preview. Empty-space dragging did not select a group. Right-click only cancelled an operation.
- Results occupied a large area before anything had run and extended beneath both side panels.
- Analysis settings required a modal dialog. A user had to return to it for each run.
- Property drafts could be lost when another selection rebuilt the inspector. Errors were disconnected modal messages.
- Mode changes refitted the canvas and discarded a user's chosen camera position.
- Symbols, control chrome, selection feedback, and output status did not have a coherent system of visual emphasis.

## Research and interpretation

Apple's current design principles emphasize purpose, agency, simplicity, hierarchy, and craft. The relevant lesson is to make the next useful action apparent and refine the complete interaction, including its intermediate states. This is guidance for the redesign, not a claim that the app is Apple-certified or conforms to every platform convention. [1]

Apple's toolbar guidance calls for deliberate selection of commands and coherent grouping. The sidebar guidance supports visible navigation, disclosure of hierarchy, and a reliable way to hide or restore navigation when more canvas space is needed. [2, 3]

Apple's label, accessibility, and data-entry guidance informed readable labels, differentiated text emphasis, persistent names for controls, visible keyboard focus, and validation at the point of editing. Testing both light and dark appearances is necessary; those visual checks do not establish complete screen-reader support. [4, 5, 6]

Altium's environment documentation provides the more domain-specific reference. Its project navigation, editor-specific commands, dynamic Properties panel, collapsible property groups, and messages associated with design objects are useful patterns for an engineering workspace. Its panel system supports keeping frequently used information available while reclaiming design space when necessary. [7, 8]

The redesign adapts these interaction principles to a standalone Qt application for Windows/Linux. It does not copy Apple's window decorations or Altium's artwork, proprietary components, or branding. Transparency and decorative effects were not priorities: dense geometry and waveform data need stable contrast.

## Implemented design decisions

| Problem | New behavior | Reason |
|---|---|---|
| Unclear hierarchy | Project navigator on the left, editor tabs above the canvas, properties on the right | Location and editing context remain visible. |
| Overloaded toolbar | A global strip for project actions/search/run; a separate editor-specific tool strip | Commands sit near the content they affect. |
| Hidden editor navigation | Schematic, Layout, and Linked views are visible tabs with Alt+1/2/3 shortcuts | Switching is direct and the active view is explicit. |
| Uncontrolled placement | Searchable device browser, pointer preview, click-to-place, Esc cancellation | Users choose placement before committing an edit. |
| Weak direct manipulation | Rubber-band selection, additive selection, drag previews, contextual right-click menu | Selection and movement have visible intermediate states. |
| Raw property editor | Electrical/Connections groups; Position and model details behind disclosures | Frequent edits require less scanning. |
| Raw layout metadata | Micrometre position/size fields, a vertex table, named component assignments | The editor uses design concepts instead of JSON or object IDs. |
| Lost drafts | Valid drafts commit before another selection; invalid drafts retain the selection and inline error | Navigation does not silently discard an edit. Reset explicitly discards a draft. |
| Repeated analysis dialogs | Persistent Analysis tab; F5 runs the current setup | Parameters stay available during iteration. Only relevant fields are shown. |
| Empty output consuming space | Results initially collapsed; jobs and checks reveal it in the center column | The design gets more space before output exists. |
| Unstable canvas camera | Camera state is remembered per cell/view; fitted views respond to pane resizing | Switching contexts preserves orientation. |
| Poor small-window behavior | Less-used geometry tools become icon controls with names/tooltips; panels can collapse | Controls stay reachable without truncated labels. |
| Inconsistent styling | Shared neutral surfaces, restrained blue selection/action accent, original vector icons, consistent spacing and focus borders | The workspace has one visual vocabulary. |
| Hard-to-find commands | Searchable command palette with menu context, shortcuts, Up/Down, Enter and Esc | Infrequent actions remain accessible without filling the toolbar. |
| Unclear plotting scale | Engineering units, explicit axis units, legible trace colors, stable colors when traces are hidden | Small-circuit results are easier to read and compare. |

The primary design is intentionally a document workspace, not a dashboard. The circuit/layout is the main content. The UI keeps routine capabilities visible and puts secondary settings in menus or disclosures. No unimplemented PDK, extraction, or verification capability is presented as a working button merely to make the interface look complete.

## Everyday workflows

**Place and edit:** choose Place, search/select a device, choose Place component, position its preview, and click. The inspector follows the new component. Edit electrical values and connections, then Apply changes. Ctrl+Z reverses the transaction.

**Simulate and compare:** open Inspector → Analysis, choose an analysis and its relevant settings, then Run. The background job opens Results. Select traces or compare the preceding compatible run. Edit the circuit and press F5 again; earlier results show a textual stale indicator.

**Draw layout:** open Layout, choose a visible drawing layer, then choose Rectangle, Polygon, or Path. Select the resulting geometry to edit its layer, net, component association, and dimensions. The basic process qualification limits remain visible in the technology settings.

**Reclaim space:** use the Project/Inspector/Results toggles or Ctrl+1/2/3. Ctrl+Shift+F temporarily hides panels and restores their previous visibility. View → Reset workspace recovers a predictable layout.

## Verification and limits

The automated native interaction checks exercise real Qt mouse/key events for placement and cancellation, box selection, moving objects, connecting pins, invalid property drafts, analysis validation, and worker execution. Layout checks cover unit conversion, layer visibility, camera memory, panel controls, and compact windows. The existing numerical/model/geometry tests still pass. Screenshots were inspected in light and dark appearances and in 1440×900 and 1100×760 layouts.

This remains an engineering preview. The redesign does not implement the missing qualified PDKs, extraction/post-layout flow, complete physical hierarchy, production solver architecture, or signed Windows distribution. It also does not establish professional usability through expert observation: that still requires representative designers performing actual tasks on physical Windows/Linux desktops. Full assistive-technology behavior, high-DPI displays, trackpads, and X11/Wayland compatibility need that platform qualification.

A useful next evaluation is task-based: observe whether designers can open a project, place and connect a device, correct a value, run an analysis, inspect a waveform, and edit a layout shape without being told where controls are. Record wrong turns, time to first successful result, lost-edit incidents, and issues that require help. The blueprint's pilot acceptance gate remains open.

## Primary references

Reviewed for this redesign:

1. [Apple — Design principles](https://developer.apple.com/design/human-interface-guidelines/design-principles)
2. [Apple — Toolbars](https://developer.apple.com/design/human-interface-guidelines/toolbars)
3. [Apple — Sidebars](https://developer.apple.com/design/human-interface-guidelines/sidebars)
4. [Apple — Labels](https://developer.apple.com/design/human-interface-guidelines/labels)
5. [Apple — Accessibility](https://developer.apple.com/design/human-interface-guidelines/accessibility)
6. [Apple — Text fields](https://developer.apple.com/design/human-interface-guidelines/text-fields)
7. [Altium — Elements of the Environment](https://www.altium.com/documentation/altium-designer/design-environment-elements)
8. [Altium — Working with Panels](https://www.altium.com/documentation/altium-designer/working-with-panels)
9. [Altium — Modern Interface Experience](https://files.resources.altium.com/sites/default/files/uberflip_docs/file_807.pdf) (historical visual reference, not evidence of current feature status)
