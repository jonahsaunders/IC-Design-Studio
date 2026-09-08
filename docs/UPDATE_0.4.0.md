# IC Design Studio 0.4.0

This is a standalone native desktop update addressing roadmap priorities 1–4. Dark mode and the slim US-style schematic symbols remain the defaults. It is an engineering release, not the completed professional blueprint.

## 1. Direct net labels, ground and inspection

- **L** opens the net-name field. Enter a name, then click a wire, pin or empty location. Matching names connect separate conductors within the active cell.
- **G** places ground, electrically named `0`. You can place ground first and wire to its anchor afterward.
- A label attached at a wire crossing belongs to the selected wire; it does not create a junction on the other wire.
- Drag the label text or ground artwork independently of its electrical anchor. The dotted leader shows the anchor. Moving or rotating the attached component carries the anchor with its pin. Moving a wire segment carries its attached labels.
- **R / Shift+R** rotates selected labels or grounds and placement previews. **Reattach…** in Properties moves the electrical attachment. Deleting a wire/device also removes labels attached to that object; undo restores them.
- Edit a selected label in Properties. By default, renaming changes every label on the same electrical net. Clear “Rename every label on this net” to rename only its physical conductor. Giving a conductor an existing name intentionally joins that named net.
- **N** inspects a whole net. Wires and terminals highlight, and the inspector lists terminals, wire paths and the number of separate physical conductors connected by labels.
- Compact windows expose the additional tools in **More…**. All tools remain in Design and the command palette.
- Placed symbols, attachments, offsets and rotations persist through save/reopen, recovery, project folders and undo/redo. Edited Xschem imports retain electrical names but reconstruct label artwork; arbitrary Xschem symbol libraries remain unsupported.

## 2. Windows delivery

Added an Inno Setup installer definition, per-user installation, optional desktop shortcut and file association, portable ZIP creation, source/license inclusion, and a Windows build script. `build-windows.bat` builds from the source distribution with Python 3.12 and Inno Setup 6 installed.

The workflow builds on Windows and verifies the installed executable, Start menu shortcut, association command, dark workspace at 100/150/200% scaling, native rotation/undo, save/reopen, simulation worker and uninstall. Each run writes JSON evidence and screenshots. See WINDOWS_RELEASE.md.

**A Windows build and installation test have not been executed in this workspace. No Windows executable or signed installer is claimed as verified or supplied.** Signing, update distribution and broader real-machine compatibility testing remain open.

## 3. Reliability

Recovery files are isolated by application session, with a validated previous snapshot for fallback if the newest file is corrupt. Saves detect a changed original file and ask you to preserve your edits with Save As before reconciling competing versions. Project-folder manifests reopen as saveable documents.

Job status is persisted as running, complete, cancelled or failed. Saved results are checked against their immutable input and project/cell/design identity. Cancelled or interrupted results are never replayed as successful results. Switching projects while a job is active is blocked until the job stops. POSIX cancellation/timeouts terminate external engine process groups; Windows cancellation uses process-tree termination.

A rejected edit does not consume a history revision or change undo/redo state. Fault-injection regressions cover atomic file replacement and project-folder manifest publication, recovery corruption, competing saves, invalid result identity and descendant cleanup.

## 4. SKY130 reference flow

Tools → Run SKY130 inverter reference runs the installed SKY130A PDK standard-cell inverter through native schematic generation, GDS import, schematic transient simulation, Magic DRC, LVS extraction, Netgen comparison, capacitance extraction and post-layout transient simulation. The generated native project includes the two MOS devices, hierarchical testbench and imported layout.

Every stage writes an explicit pass/fail/not-run status. PDK assets are checksummed, models use explicit device bindings and units, and all tool scripts, logs, input decks and waveforms are retained. Missing dependencies and technology errors fail the flow instead of being treated as success. See SKY130_REFERENCE.md for the executed result and its exact limits.

This is one standard-cell regression. It does not qualify arbitrary layouts, other PDK device families/corners, distributed interconnect resistance, or foundry tapeout signoff.

## Verified delivery

76 core regressions and the native editing/reliability/workflow suites passed. The packaged Linux executable passed startup, dark mode at 100% and 200% scale, save/reopen, rotation/undo and background simulation. The full SKY130 reference also passed through that packaged executable: DRC 0, unique LVS match, 14 extracted capacitors, successful pre/post simulation. Windows build/installation execution is still required.

The Linux archive targets x86_64 Ubuntu 24.04 / glibc 2.39 or newer. Extract the whole folder and launch ICDesignStudio. Windows users should use the source ZIP and build-windows.bat; the Linux archive will not run on Windows.
