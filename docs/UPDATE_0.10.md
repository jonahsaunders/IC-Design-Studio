# IC Design Studio 0.10.0 — analog physical workflow

This release connects editable analog schematics to native physical geometry,
independent engine verification and saved characterization comparisons. It keeps
schema 1, existing project identities, saved benches, PDK locks and undo history.

## Create and verify a SKY130 mirror

1. Link the supplied SKY130A PDK revision in **Tools → PDK manager**.
2. Choose **File → New PDK current mirror**, then open its circuit cell.
3. Choose **Design → Generate current mirror layout** and review the generated
   geometry before applying it. The two standard 1.8 V NMOS devices have equal W/L,
   one finger each, the same orientation, explicit source/body contacts and three
   named circuit ports. Corresponding device terminals share an alignment axis.
4. Use **Check linked layout and show connections**. Edit the shapes and routes
   directly; **Undo** restores a complete operation.
5. Select the saved OP or DC bench and choose **Verify layout**. The worker runs
   the exact fixture through schematic simulation, full Magic DRC, extraction,
   Netgen LVS, capacitance extraction and post-layout ngspice simulation.
6. Inspect the measurement comparison table. Choose a voltage or source-current
   probe and **Overlay before / after** to compare both implementations.

The mirror is a bounded 1:1 recipe. Its model/W/L checks and actual footprint
comparison detect changed dimensions, unequal shapes, differing orientation and
broken alignment. Matching constraints describe geometry; they do not establish
foundry mismatch statistics or layout-dependent device-model effects. Regeneration
replaces this recipe's geometry, contacts, routes and ports after review.

## Compare a complete saved study

In **Configure saved-bench characterization**, select **Schematic and post-layout**.
The setting travels with the project. Parameter sweeps, PVT cases and declared
component-tolerance studies retain their existing input rules and 500-case limit.

Each case independently requires schematic measurement limits, full DRC, unique
LVS without property errors, capacitance extraction and post-layout limits. This
can take substantially longer than schematic-only simulation. Cases with failed
stages remain visible; any failed or blocked case makes the complete study fail.
Available schematic results remain inspectable when extraction or LVS fails.

The table shows schematic → post-layout values and their delta. Select up to four
rows for eight traces with **Both implementations**, or eight rows for one
implementation. Every trace retains its own sampled coordinates. Source-current
sign remains positive from a voltage source's + terminal to its − terminal. CSV
includes both values, statuses, deltas and failure details.

Saved waveforms are checked against their recorded checksum and project, fixture
and design identity. Edits make earlier results stale; undo advances revision and
still requires a fresh run. Cancellation does not publish a completed result.

## Layout editing

- **Place via** supports clicking on the canvas or entering exact coordinates.
  It places the cut and both conductor enclosures together. Escape exits repeated
  placement. SKY130 supports local interconnect–M1 and M1–M2; GF180 supports M1–M2.
  All three layers must be unlocked. A single undo removes the complete stack.
- **Stretch path segment** moves a horizontal segment in Y or a vertical segment
  in X. **Stretch path with mouse** previews a perpendicular drag. Connected bends
  follow; collapsed segments, diagonals and off-grid offsets are rejected.
- **Align layout selection** keeps the first selected object fixed. It supports
  edges and center axes. Select complete generated devices or via stacks; complete
  device terminals move with their footprint. Exact off-grid alignment is rejected.
- Existing complete-cell transforms can move all geometry, labels and ports
  together. Partial route edits retain stationary port/terminal markers. Parent
  routes do not follow child-interface changes automatically.

After an endpoint or placement edit, check connectivity. Open-net findings include
the net name, disconnected-group count and dashed guides. Geometry/terminal checks
assist editing; independent extraction and LVS remain the physical gate.

## Navigate DRC and LVS findings

Choose **View findings** in the physical workflow, or double-click its DRC/LVS
stage. Click a finding to open its cell and highlight its geometry, device or net.
Magic findings retain per-cell coordinates and the actual extraction scale.
Netgen JSON supplies full device/property names; supported names map back to the
native schematic hierarchy. Unknown identities remain visible in the raw evidence
without being assigned to a guessed object. Stale findings cannot navigate a
changed design. Viewing or waiving a finding does not change the engine result.
The LVS gate also requires equivalent connected pin lists. A unique device match
with a disconnected or automatically altered port is rejected; the missing-body
contact negative control exercises this case with real GF180 extraction.

## GF180 physical subset

Link the supplied GF180MCU C revision and choose **File → New GF180 3.3 V inverter**.
Review **Generate inverter layout**, then run its saved transient bench. Its
fixture uses a 3.3 V supply, editable input source and 10 fF load, with delay and
settled output-voltage limits. The saved load study compares 5, 10 and 20 fF.

| Contract | Supported subset |
|---|---|
| Models | Standard four-terminal `nfet_03v3`, `pfet_03v3` |
| Width | 1–10 µm |
| Length | 0.28–2 µm |
| Grid | 5 nm |
| Fingers / multiplicity | `nf = m = mult = 1` |
| Body contacts | NMOS substrate tap; PMOS contacted N-well |
| Native recipes | Individual MOS and CMOS inverter |
| Drawing / port labels | Actual process datatypes 0 / 10 |

The adapter adds its explicit native layer table to the project when generating
geometry. Layer mappings and conservative contacts derive from the supplied
locked Magic technology assets. No PDK package files or model bindings are
rewritten. Physical inputs must be present in the lock and match their hashes.
Other voltage families, passives, RF devices, multifinger GF180, GF180 mirrors and
GF180 rings are outside this geometry subset.

## Automation

```sh
python main.py --cli mirror-layout mirror.icproj --cell current_mirror --output mirror-layout.icproj
python main.py --cli inverter-layout inverter.icproj --cell gf180_inverter --output inverter-layout.icproj
python main.py --cli characterize mirror-layout.icproj --testbench current_mirror_dc --compare-layout --magic /path/to/magic --netgen /path/to/netgen --ngspice /path/to/ngspice --output new-comparison-directory
```

The existing `verify` command runs one saved bench through the complete physical
flow. New verification directories must be empty. Inspect `report.json`,
`navigation.json`, per-case directories and the actual engine logs/decks.

## Verification and platform scope

The handoff's final release results identify executed core tests, native GUI
suites, new process/circuit cases, negative controls, original hierarchy and
interchange regressions, and packaged-application probes. Intermediate failed
investigations remain separate from the authoritative final matrix.

Linux x86_64 packaging targets Ubuntu 24.04 / glibc 2.39 or newer. Python, Qt and
KLayout are bundled; Magic, Netgen and ngspice remain configured external tools.
See **LINUX_SETUP.md** for launch and dependency checks. Fresh-profile tests with
development Python/loader settings removed are distinct from a fresh-OS
installation. The build host forbids new OS/container namespaces; no separate
clean-machine installation or Windows installer execution is claimed.

Extraction includes capacitance, not distributed interconnect resistance. The
analog recipes and new GF180 subset are engineering fixtures, not fabrication
signoff. Physical differential-pair recipes, IHP physical support, broader device
families and foundry statistical mismatch qualification remain future work.
