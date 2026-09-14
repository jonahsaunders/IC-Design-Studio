# Digital workspace

Digital design now uses the main window. **Circuit workspace** restores the
schematic/layout document and its panels. Source drafts, undo, saving and the
shared job queue retain their existing project lifecycle.

## Interface

- Leading navigator: native cells, source search and compiler hierarchy.
- Central documents: **Design** for editing, **Debug** for source/results together,
  **Implement** for physical inspection. Pane widths and visibility are remembered.
- Trailing inspector: selection identity, design setup and saved cell views.
- Stage strip: synthesis, floorplan, placement, clock tree, routing, GDS and timing,
  with explicit Current/Stale/Failed/Running states.
- Read-only **Run snapshot** sources and a captured-versus-working diff prevent
  historical diagnostics from opening a different revision of the source.

Use F5 for a stage, Ctrl+Alt+1/2/3 for workspace modes, Ctrl+F/F3 to search a
source, and Ctrl+L to go to a line. The navigator and inspector can be hidden.
At smaller window sizes the inspector starts collapsed. Light and dark themes
use the application's palette, readable text, selection states and focus styles.

The layout applies Apple's guidance on a document-centered desktop experience,
shallow navigation, adjustable sidebars and consistent controls. Linked selection
and simultaneous timing/physical documents take inspiration from Altium's
continuous cross-probing. This is Studio's native Qt interface; it does not copy
either product's branding or assets.

Design references:

- [Apple: Designing for macOS](https://developer.apple.com/design/human-interface-guidelines/designing-for-macos)
- [Apple: Sidebars](https://developer.apple.com/design/human-interface-guidelines/sidebars)
- [Altium: Cross-probing and selecting](https://www.altium.com/documentation/altium-designer/sch-pcb/cross-probing-selecting)
- [Altium: Constraint Manager](https://www.altium.com/documentation/altium-designer/constraint-manager)

## Targets and constraints

**Run to placement/routing/GDS** creates a durable dependency plan, queues stages
in order, and ends with timing. **Verify block** runs lint, the saved regression
(or the default simulation), mapping, equivalence and timing. Failure, UNKNOWN
proof and INCOMPLETE timing stop the plan. Resume retains the captured project;
start a new target to include subsequent source edits. Interrupted plans survive
restart. Reuse requires compatible stage inputs, the recorded engine environment
and verified artifacts. Explicit upstream selection remains available.

The constraints dialog provides clock and I/O tables, uncertainty/transition,
driving cell, load, synthesis frontend/budget, selected library corners and editable
SDC. Generated SDC owns its file only when explicitly selected. For generated
intent, synthesis uses the minimum clock period minus uncertainty and maximum
input/output delays as a conservative ABC delay target. Conversion is ns→ps and
pF→fF. ABC's two-command driver/load file is distinct from SDC. This scalar budget
is not a full multi-clock optimizer. Manually edited SDC requires an explicit
synthesis budget when it diverges from stored structured intent.

Timing retains setup/hold paths, reported violation counts, total negative slack,
electrical checks and power estimates per selected Liberty corner. RC-corner
variation needs separately extracted SPEF; a library-corner sweep with one SPEF
does not establish multi-corner physical signoff. Comparisons exclude mismatched
constraints, tool environments and parasitic modes.

Floorplan controls cover die/core rectangles, density, threads, routing-layer
bounds, pin-edge groups, fixed macros, macro halo and advanced captured I/O,
macro-placement and PDN Tcl. These are real ORFS inputs, not display-only geometry.

## Connected inspection

Compiler netlists provide hierarchy, ports, connections and source attributes.
The logic-cone view shows a bounded neighborhood; selecting a neighbor continues
inspection. Selection identities include run, cell, module and object. Ambiguous
waveform-name matches remain explicit. Inserted cells without retained source
attributes are marked unmapped rather than assigned a guessed source line.

OpenDB supplies instance IDs, transformed bounding boxes, orientation and terminal
connectivity. Physical display uses indexed instance rectangles and batched route
paths, without the old 20,000-instance/50,000-segment display truncation. Filters,
net/instance search and placement-density bins help inspect larger blocks. Density
is occupied area per spatial bin, not a routing-congestion prediction. The DEF
route preview still caps input at 128 MiB and 500,000 segments. It displays signal
centerlines; final GDS remains the geometry used for layout/DRC inspection.

Published symbols use compiler ports with bus metadata and scalar electrical
terminals. Changed interfaces open the existing review dialog to reconcile all
instances, physical ports and affected testbenches in one undoable transaction.
The native circuit model still has a 128-scalar-terminal limit; this change does
not introduce a second, incompatible bus connectivity model.

## Waveforms and language tools

Waveforms support four-state values, aliases, binary/hex/unsigned/signed display,
saved signal sets, signal filtering, edge/value search, and two cursors (click A,
Shift-click B). Large VCDs stream into a SQLite transition index; the viewer reads
pages on demand. Limits are 2 GiB of VCD, 20 million value changes, 100,000 signal
declarations and 4,096 bits per signal. Small waveforms retain the original JSON
representation. The index is a checksummed run artifact and is included in
regression capture.

**More → Language server** starts a user-selected stdio SystemVerilog LSP server.
Enter its arguments as a JSON array. Sources are materialized into an isolated
session directory. Live diagnostics, Ctrl+Space completion and F12 definitions
operate on the working copy. The server must support UTF-16 positions and the
standard initialize/document-sync methods. Server-specific project configuration
and language coverage remain the chosen server's responsibility; no server is
downloaded or bundled by this change. The optional Yosys slang frontend requires
the matching `slang` plugin from the selected toolchain.

Protocol reference: [Language Server Protocol 3.17](https://microsoft.github.io/language-server-protocol/specifications/lsp/3.17/specification/).

## Qualification boundary

This work improves the existing open-source block-design flow. It does not add a
coupled Verilog-AMS/SPICE simulator, per-instance analog/digital view substitution,
foundry-qualified DRC/LVS/PEX decks, automatic timing-exception proofs or a
characterized macro Liberty generator. RTL-only cells remain excluded from analog
simulation unless they have a circuit implementation. Macro bundles record this
qualification scope explicitly.

Local validation covers source/constraint identity, large-trace indexing, queue
resume/cancel, historical source probing, APB functional faults, analog regression,
desktop project switching, and light/dark layout. The pinned implementation CI
also requires mapped counter/APB netlists, EQY proof and injected-fault detection,
all physical checkpoints, GDS/LEF/SPEF export, extracted timing and target reuse.
