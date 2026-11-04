# IHP CMIM physical multiplicity and electrical comparison

This workflow checks one ordinary catalog `cap_cmim` instance with `m=2`
against two explicitly connected `m=1` instances and the same two-unit physical
layout. Each unit is a contacted 7 × 7 µm rectangle; both electrodes are shared,
and the selected layout is checked at 0° and 90°. This is a finite source-mode
integration check. It does not qualify arbitrary arrays, statistical behavior,
parasitic extraction, operating limits, installed applications or the complete
device family.

The public LVS documentation describes multiplicity as the number of capacitors.
The pinned public KLayout combiner documents addition of multiplicities for
equal-size capacitors on the same ordered nets. This workflow explicitly disables
that combiner during extraction. The observed two-to-one reduction occurs later
under Netgen's separately pinned comparison policy. The workflow preserves
per-unit width, length, area and perimeter and independently reads the two devices
in the unfiltered extraction before comparison combines them. A single capacitor
with twice the area is a different construction: two 7 × 7 µm units have
56 µm total perimeter, whereas one 7 × 14 µm rectangle has 42 µm perimeter.

The physical runner saves and reopens ordinary catalog projects, preserves the
original simulation X statements and exports GDS/OASIS. It runs the two unchanged
public DRC decks and the versioned metal-spacing supplement, followed by
source-pinned extraction and strict LVS. Its independent reader checks all ten selected
contexts: four positive count/reference/orientation combinations and six
deliberate faults. These include incorrect reference counts, reversed wiring,
a missing contact, incorrect reference width and an altered physical unit width.
Each failure must have the intended native cause; an engine error is not a
successful fault control. The six negative contexts use the 0° layout.

The electrical runner first requires the full physical reader to pass. It copies
the accepted ordinary schematic references and raw two-unit extraction, binding
each file to the physical reader's hash. The independent electrical reader
rechecks those copies and the full physical report's selection and outcomes.
Replaying electrical evidence alone does not replay the original physical masks
and reports; retain the physical output for its separate reader.

Six native electrical runs cover both rotations and the deterministic `cap_typ`,
`cap_bcs` and `cap_wcs` capacitor sections at 27 °C. Four routes are compared:
the ordinary `m=2` reference, the two explicit instances, models instantiated
from the actual two extracted unit records, and two literal independent series
RC branches. The pinned model gives 55 mΩ series resistance per unit. Parallel
units should therefore double capacitance and halve equivalent series resistance.
The capacitor corners scale the area coefficient; the 40 aF/µm perimeter
coefficient remains unchanged. No global process correlation is inferred.

Every run measures 100 kHz and 1 MHz and a separate numerical point with
`ωRC=1` for a single unit. The latter makes resistance scaling observable; its
frequency is not a claim of physical model validity. Five altered circuits
exercise counts one and three, the equal-area 7 × 14 µm substitution, series
wiring and doubled branch resistance. Each must match its own independently
calculated network before rejection against the intended parallel pair. The
series fault includes a stated 1 TΩ midpoint bias resistor for a defined DC
solution, also included in its analytical reference. Electrode orientation is
checked in the physical/reference contract; AC admittance of this reciprocal
two-terminal model does not establish electrode orientation.

The numerical acceptance uses relative `1e-8` checks for positive complex
admittance and high-point equivalent resistance. At the two low-frequency
points, fault-reference reactive current retains a relative `1e-8` check;
the small real component allows `8 × ulp(1/R)` plus its relative tolerance.
This is a declared finite numerical allowance for conductance subtraction,
not a universal solver-error bound or a low-frequency conductance calibration.
Wrong-resistance detection is required at the `ωRC=1` point. Other altered
circuits must differ from the intended result by more than `1e-4` relatively
at every point. Nonfinite samples and altered stimuli remain errors.
Reported relative errors use deterministic decimal magnitude calculations from
the actual binary components, preserving exact report replay across Windows and
Linux. This does not change the numerical acceptance thresholds or raw evidence.

Use the pinned repository PDK and Python KLayout 0.30.5, with explicit existing
Magic, Netgen, KLayout and ngspice paths. The pinned Magic technology requires
Magic 8.3.617 or newer; the tested physical tools are Magic 8.3.684, Netgen
1.5.300 and KLayout 0.30.5. The producer runs on native Linux.
Output folders must be new, outside the checkout, and free of symbolic links
or junctions. For the electrical producer, `--native-binary` identifies the
actual ngspice binary; it may equal `--ngspice`, or use the specifically locked
managed wrapper/binary pair. The electrical run binds resolved dynamic-library
bytes as well as the launcher and binary. The physical runner records launcher
bytes and retains the native command receipts; it does not claim a fully
hermetic toolchain.

```text
python scripts/qualify_ihp_cmim_multiplicity.py --output /absolute/physical-output --magic /path/to/magic --netgen /path/to/netgen --klayout /path/to/klayout
python scripts/check_ihp_cmim_multiplicity.py /absolute/physical-output
python scripts/qualify_ihp_cmim_multiplicity_electrical.py --physical-evidence /absolute/physical-output --out /absolute/electrical-output --ngspice /path/to/launcher --native-binary /path/to/ngspice
python scripts/check_ihp_cmim_multiplicity_electrical.py --evidence /absolute/electrical-output
```

Physical counts are distinct from positive fractional simulation multipliers.
The selected fractional physical diagnostic reached comparison and failed; the
workflow does not round fractional values or globally restrict simulation.
Nested subcircuit multipliers and statistical draws are outside this contract.
The remaining family requirements are recorded in
[IHP_CMIM_REQUIREMENTS.md](IHP_CMIM_REQUIREMENTS.md).

The [physical validation record](validation/ihp-cmim-multiplicity-physical-2026-11-03.json)
and [electrical validation record](validation/ihp-cmim-multiplicity-electrical-2026-11-03.json)
identify the exact source snapshots, independent review, both-host readback,
original failures and compact recovery archives.
