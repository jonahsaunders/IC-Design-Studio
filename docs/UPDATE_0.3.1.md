# IC Design Studio 0.3.1 — manual wiring and keyboard editing

This update changes the native desktop schematic editor. Dark mode remains the default. It retains the 0.3.0 study, physical-design, PDK and project workflows; it does not claim completion of the professional blueprint. See `RELEASE_STATUS.md` for the remaining scope.

## What changed

| Area | Implemented behavior |
|---|---|
| Wire placement | W starts a saved wire path. Click the start, fix each bend, and finish on a pin or existing wire. Paths can also start/end in empty space. A dashed final elbow previews the next segment. The renderer no longer invents routes from matching net names. |
| Routing control | Space or Tab flips the preview elbow. Backspace removes the previous click. Enter finishes at the last clicked point. Esc cancels the pending path; a second Esc selects. Right-click cancels and selects. Middle-drag pans while wiring. |
| Electrical connectivity | Pin contacts, wire endpoints, branches and explicit junctions determine the circuit used for simulation and exports. A bridge marks an unconnected interior crossing; a solid dot marks a junction. J at a crossing adds/removes an explicit junction. |
| Joining nets | Drawing a wire joins the complete connected networks. Ground takes precedence, otherwise the starting named conductor is preferred. The status line reports label changes. Redundant labels on the joined physical conductor are removed so deleting the joining wire does not leave an accidental invisible connection. Undo restores the whole prior state. |
| Editing paths | Click a wire to select it. Drag a segment perpendicular to itself to move it while retaining endpoints and branches through local lead segments. Delete removes the selected wire and recalculates connectivity; Ctrl+Z restores geometry and connections. Box-selection includes wires. |
| Moving devices | Moves and rotations stretch the attached terminal leads, retaining the remote bends you placed. Pins at a branch retain the branch through a local lead. Geometry changes that conflict with explicit labels are rejected with an explanation. |
| Open terminals | New and duplicated components start unconnected, including their negative/ground terminals. Open pins are hollow. Wire them or enter an explicit label in the Connections inspector. `0` means ground. Equal explicit labels intentionally connect distant conductors. Clear a label to remove that named connection. |
| Symbols | Inductors now use a continuous four-turn coil. Current sources use a circle with an arrow from the positive terminal to the negative terminal; they no longer reuse voltage-source polarity marks. Both canvas artwork and device-library icons use the slimmer visual weight. The US zigzag resistor remains. |
| Rotation | R rotates clockwise and Shift+R counterclockwise, during placement and with selected devices. A Rotate toolbar control and both inspector buttons provide mouse access. Component-list/project selection supports the same editor shortcuts. |
| Keyboard commands | Shared actions own the editor bindings, replacing overlapping old shortcuts. Menus have unique Qt mnemonics and show actual command keys. Alt+the underlined menu letter opens it; the underlined command letter invokes it. Text fields retain normal typing, including R/W/P/Delete. Help → Keyboard shortcuts and wiring (Ctrl+/) explains the controls. |
| Files and interoperability | Wire paths are saved in projects, recovery snapshots and project folders. Netlisting resolves their geometry. Xschem export writes the actual placed segments, splitting explicit junctions; the bounded package importer replaces stale wire geometry with the edited segments. Labelled Xschem segments retain their explicit remote-net semantics. |

## Quick use

1. Press **P**, choose a component, and enter placement. Press **R / Shift+R** until its orientation is right, then click to place it.
2. Press **W**. Click the first pin, click each bend you want, then click the destination pin or wire. Use Space to choose the next elbow direction.
3. Press Esc to select. Click a wire and drag its segment to reshape it. Select a device and press R to rotate it.
4. Set one explicit `0` label on each intended ground conductor in Connections. Other terminals have no automatic ground assignment.
5. Run ERC with F6 and simulation with F5. New designs need their intended ground and source configuration.

`examples/manual-wiring.icproj` is a complete wired voltage source, resistor, capacitor, inductor and current-source testbench. Its saved paths feed both the built-in simulator and ngspice.

## Existing projects

Legacy net assignments are preserved on opening. Previously inferred routes become saved paths only when the generated geometry preserves every original connection. Ambiguous drawings retain their old connections as explicit pin labels and omit the misleading inferred lines. If legacy pins physically overlap on conflicting nets, move them apart before using manual wires. These compatibility labels remain intentional connections until edited or cleared.

New wiring data uses optional fields in the existing project container. Use 0.3.1 or later to edit these paths. Explicit labels can still connect separated conductors; this is visible in Connections and on labelled pins.

## Validation

- **61 core tests passed**, including route persistence, netlist generation, branches, crossings/junctions, named-net merging, delete/undo, terminal stretching, a moved branch pin, custom/off-grid pins, legacy migration, explicit ground, conflicting labels and edited Xschem geometry.
- Native Qt input tests passed for click-by-click placement, bend reversal, Backspace/Enter/Esc, segment dragging with a branch, deletion/undo, placement/selection/outline rotation, text-field typing safety, J junction toggling, all top-level Alt-menu mnemonics, a menu command mnemonic and command-palette navigation. Full and compact dark screenshots were inspected.
- Existing native interface, usability, dark-mode/job-state and 0.3.0 workflow checks passed during this update. Those include simulation, study results, physical connectivity/extraction estimates, symbol editing and saved-run recovery.
- The manually wired RLC/current-source example ran in the built-in engine and the actual ngspice 42 executable (563 transient samples). On this restricted test host only, a temporary-file adapter redirected ngspice scratch files into a writable directory. It did not change its deck or solver and is not shipped in the application.
- The final standalone Linux build passed native startup and ran its bundled manual-wiring example (501 finite samples) without the development Python environment. Details are in `TEST_REPORT.md`.

## Start the update

**Windows source:** extract `IC-Design-Studio-0.3.1-Source.zip`, then run `launch-windows.bat`. It requires 64-bit Python 3.12; the first launch installs the pinned dependencies. This delivery does not include a Windows executable or installer, and Windows execution has not been verified here.

**Linux standalone:** extract `IC-Design-Studio-0.3.1-Linux-x86_64.tar.gz`, keep `_internal` beside `ICDesignStudio`, and run `./ICDesignStudio`. Python and Qt are included. The build targets Ubuntu 24.04 x86_64 / glibc 2.39 or newer. Other desktop, graphics and accessibility combinations remain outside the executed validation.

The broader 0.3.0 limitations, including foundry qualification, universal tool round trips and signed release delivery, remain documented in `RELEASE_STATUS.md`.
