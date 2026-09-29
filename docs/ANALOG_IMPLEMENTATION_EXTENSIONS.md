# Process extraction, device arrays and native hierarchy

This experimental source update extends the existing analog workflow. Earlier
reference and release records still identify their original source and engines;
they do not qualify these changes or a new desktop package.

## Parameter-correct physical hierarchy

Choose **Layout → Cells and arrays → Resolve and regenerate physical variants…**
to review instance overrides as concrete physical masters. Identical effective
parameter sets reuse a master only while its source hierarchy, technology,
global parameters and generated implementation still match the recorded hashes.
Supported device footprints regenerate through the ordinary schematic-driven
layout checks. Unregenerable parameter-dependent manual geometry blocks the
proposal with an explanation.

**Place linked physical instance…** performs the same preparation before placing
the selected instance. Both actions show a preview and apply as one undoable
transaction. Layer locks are checked again when applying. A changed project
invalidates the preview. Physical ports follow regenerated terminals; parent
connections and constraints are reviewed with the geometry change.

The source API returns a candidate without changing the input:

```python
from icstudio.physical_variants import materialize

candidate, report = materialize(project, cell_id)
```

Review and commit the candidate using the normal project history. Regeneration
does not establish DRC, LVS or extracted performance; rerun those checks on the
resulting design.

## Native buses and instance arrays

Use ordered expressions such as `data[7:0]`, `data[0:7]` or
`data[7:4],data[1:0]` in supported native terminals and labels. Range direction
determines terminal order. **Schematic → Configure instance array…** declares a
compact array with explicit start and end indices. Leave the range blank to
return to a scalar instance.

An N-member array of W-bit terminals accepts either W signals, broadcast as a
group to each member, or N × W signals, divided into ordered W-bit groups. A
scalar connection cannot silently short a multi-bit terminal. Overlapping cell
ports, conflicting expanded names and width mismatches are rejected. Explicit
global nets retain their scope through electrical and physical flattening.

Compact arrays stay editable in the native project. Simulation and netlisting
expand them deterministically. Select an array and choose **Layout → Cells and
arrays → Expand linked instance array…** before placing members independently.
The review preserves ordered member connections and stable member identities.
Existing linked array placements expand at the specified pitch in parent
coordinates; unplaced arrays remain unplaced. Apply, undo and save/reopen retain
the complete operation.

The current native expression limit is 128 signals or array members. Indexed
labels provide scalar/slice connections; executable Tcl remains an external
Xschem workflow. External formats must preserve the supported semantics or reject
the handoff explicitly; native support does not establish arbitrary Xschem or
Cadence compatibility.

See [Native buses and instance arrays](NATIVE_VECTORS.md) for ordering examples,
floating-terminal behavior and exchange boundaries.

## SKY130 parallel devices

The standard supported SKY130 1.8 V MOS recipes now generate 1–16 explicit
parallel units, each retaining the supported 1–8-finger geometry. The supported
MiM capacitor and generic poly resistor recipes likewise support bounded
parallel multiplicity. Terminal rails connect actual geometry; the schematic
device and public terminal identities remain stable during regeneration.

The PDK generation and placement forms offer an explicit source/body tie for
supported MOS devices. This requires source and body to have the same schematic
net. The saved option is part of the physical specification and participates in
stale-footprint detection and regeneration. Dummies retain their explicit
schematic connections.

Existing per-unit dimension and process restrictions still apply. Review the
larger footprint and attached routes after changing multiplicity. The expanded
actual-engine coupon suite is `scripts/qualify_sky130_devices.py`; its results
apply only to the executed source, recorded dimensions and locked PDK.

The fixed upstream 3.40 µm SKY130 PNP also supports 1–16 parallel units, with
checksum-locked geometry and explicit terminal access. It requires a separately
versioned adapter with the pinned upstream emitter-area extraction rules.
See [PNP preparation and qualification](ANALOG_REFERENCE_WORKFLOW.md) for the
opt-in setup. NPN generation and bipolar RC qualification remain unsupported.

The same device operation is available from the CLI:

```sh
python -m icstudio --cli pdk-device-layout design.icproj --cell amplifier --device M1 --body-tie source --output placed.icproj
python -m icstudio --cli pdk-device-layout placed.icproj --cell amplifier --device M1 --regenerate --output regenerated.icproj
```

Initial `--x` and `--y` coordinates are integer nanometres. Regeneration preserves
the saved placement and rejects replacement coordinates. Invalid arguments or
unsupported geometry do not overwrite an existing output project.

## Process RC integrity

Process RC runs can flatten physical hierarchy in the disposable Magic workspace
before extraction, retaining top-level port labels and leaving the editable
project and original GDS untouched. Normalization accepts hierarchical node
names and unambiguous explicit aliases while retaining the original-net mapping.
Aliases that merge distinct ports or cannot be reconciled with the extraction
records fail visibly.

The supported device classes are MOS, MOS/resistor/capacitor subcircuits and
native numeric or modeled `devres`, `devcap` and `devcaprev` devices. Native
physical R/C devices receive stable extraction identities, so rebuilding
parasitic capacitance cannot delete a designed capacitor or misclassify a
modeled resistor as a wire. A known Magic omission of primitive device headers
in `.res.ext` is repaired only from the matching original device record; both
raw files and the repair are retained.

Normalization verifies each device terminal against its original net, checks
the exported ordered terminal inventory, and checks every wire resistor. It
restores the original resistance at 17 significant digits, including removal
of Magic's identified 0.5 milliohm export bias. A pre-resistance device-only
export binds model names, values and every emitted parameter. If splitting a
shared net changes Magic's junction area/perimeter allocation, those fields
are restored only from an unambiguous reference matched on model, ordered
contracted terminals and all other parameters. Dimensions and multiplicities
cannot be restored through this exception. Ambiguous or unsupported mappings
fail visibly.

`extracted.spice` retains the complete verified RC graph. `electrical.spice`
omits only resistor-only components with no port, physical device terminal or
capacitor connection. `electrical.spice.islands.json` records every omission and
both file hashes. Saved-bench process-RC simulations use this electrical deck;
no artificial leakage resistors are introduced. The original GDS, raw engine
export, device reference and normalization report remain available.

Use **Process distributed RC** in the saved physical testbench. The source
entry point is `icstudio.silicon_flow.magic_script` with commands from
`icstudio.external_tools.extraction_commands('rc')`. An explicit substrate
reference and a complete connected resistance mapping are still required;
unsupported extraction records, aliased distinct ports, ambiguous parameter
references and excessive capacitance expansion remain errors. The capacitance
distribution is an area-weighted lumped approximation, not a spatial field
solution or fabrication signoff.

The primitive-resistor regression includes strict Magic DRC, Netgen LVS and
an independent ngspice comparison of schematic, contracted and extracted
terminal resistance:

```sh
python scripts/qualify_rc_primitives.py --pdk /path/to/locked-sky130-adapter --magic /path/to/magic --netgen /path/to/netgen --ngspice /path/to/ngspice --out build/primitive-rc
```

## Bounded floating-fill capacitance

`icstudio.fill_capacitance.from_ext(path, floating_nodes)` reads authoritative
full-precision ground and mutual capacitance from a flat Magic `.ext` file and
computes the zero-charge floating-conductor Schur complement. The result
retains fill-to-fill paths and the shielding already present in the extracted
matrix. It includes the input file digest, original capacitances, reduced
ground/mutual values, component membership, solve residuals and numerical
limits. It never grounds a floating tile or substitutes invented coefficients.

```python
from icstudio.fill_capacitance import from_ext

reduced = from_ext("fill_control.ext", ["FLOATING"])
effective_ground_capacitance = reduced["ground_f"]["SIGNAL"]
```

External ports, substrate reference nodes and physical-device terminals cannot
be declared floating fill. Ambiguous aliases, legacy terminal records,
duplicate nodes, nonpassive data, ill-conditioned matrices and connected
components beyond the declared budget are rejected. The default maximum is
256 floating nodes and 256 retained boundary nodes per coupled component.
Disconnected unobservable fill components are recorded without a solve.

`scripts/qualify_gf180_fill_coupling.py` now exercises this reduction using
actual absent/near/far metal coupons on all four GF180 metal levels and retains
`floating-reduction.json` for each coupon. The reference bandgap's existing
geometry check still requires its fill outside the pinned deck's finite
interaction range. Arbitrary near-fill layout annotation and automatic
insertion into every saved-bench deck are not implemented. This bounded
analysis assumes equipotential metal and zero initial net charge; it does not
include finite fill resistance, unextracted long-range fields or foundry
calibration.

## Validation

The [retained validation records](validation/analog_extensions/README.md) include
source regressions, actual process-engine comparisons and desktop screenshots.

Run the core regression and release checks from the repository root:

```sh
python -m unittest discover -s tests -v
python scripts/check_release.py
QT_QPA_PLATFORM=offscreen python tests/gui_physical_variants.py --out build/physical-variants
QT_QPA_PLATFORM=offscreen python tests/gui_native_vectors.py --out build/native-vectors
QT_QPA_PLATFORM=offscreen python tests/gui_sky130_devices.py --out build/sky130-devices-ui
```

The desktop regression exercises review without mutation, apply-time layer locks,
electrical equivalence, regenerated port coordinates, undo/redo, save/reopen,
stale previews and linked-array materialization. It uses illustrative geometry;
actual process correctness requires the separate Magic/Netgen/ngspice runs.
Consumer-desktop acceptance, general process qualification and fabrication
signoff remain separate from source regression results.
