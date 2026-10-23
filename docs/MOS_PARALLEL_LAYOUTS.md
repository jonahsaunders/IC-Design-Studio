# GF180 and IHP standard MOS parallel layouts

The standard four-terminal GF180 C/D 3.3 V and IHP SG13G2 1.2 V
transistor generators support an integer `m` from 1 through 16. Each copy
has its own channel, diffusion contacts and body contact. Metal2 connects
matching terminals. Width and length remain the dimensions of each unit;
this does not turn `m` into a shared gate-finger count.

Set the schematic device's `m`, then use **Generate linked PDK device**.
For an existing footprint, review and apply regeneration. The first unit's
terminal positions and stable shape identities are retained. Inverter
placement accounts for the entire NMOS array before placing the PMOS array.
Existing single-unit geometry and saved specifications remain unchanged.

The [execution record](validation/mos-parallel-layouts-2026-10-23.json)
contains native full DRC and strict LVS for 144 device layouts: both
polarities, all three packages, minimum/interior/maximum unit sizes, selected
multiplicities 2/3/16, and all eight rotation/reflection combinations.
Twelve additional inverter contexts cover `(mN, mP)` = `(1,1)`, `(1,3)`,
`(3,1)` and `(16,16)` on each package.

All 156 deliberate faults are detected. Device faults remove a complete unit,
open one copy's gate/drain/source via, remove all body contacts, or change
the reference count, width or gate/body mapping. Inverter faults change the
NMOS count. Setup errors do not satisfy a fault control. The IHP body-contact
fault also produces the expected native latch-up-spacing violations.

Independent readback verifies all 1,134 native transistors and 8,008
file, asset and engine bindings. All 72 previous single-unit characterization
sizes produce identical shapes, pins, roles and saved specifications after
excluding newly allocated object IDs. Source desktop checks on Windows and
Linux cover generation, undo/redo, editing `m`, regeneration and save/reopen.

Reproduce the complete native batch with the locked local engines:

```sh
python scripts/qualify_mos_parallel_layouts.py --output /path/to/new-results --magic /path/to/magic --netgen /path/to/netgen --workers 2
python tests/gui_mos_parallel.py --out /path/to/new-editor-results
```

`--pilot` selects six small device cases and three inverter contexts. It is
not the complete batch. The unit's existing geometry bounds remain unchanged:
GF180 W=0.22–10 and L=0.28–10 micrometres; IHP W=0.15–10 and L=0.13–10
micrometres, on a 5 nm grid. Fractional/out-of-range physical multiplicity and
multiple fingers per unit are rejected.

These results qualify the recorded geometry/connectivity samples. They do
not establish every layout on the grid, extracted RC or performance, mismatch,
reliability, operating envelopes or complete device-family qualification.
Every edited design still requires verification. Model and PDK bytes are
unchanged; the new application code introduces no additional third-party asset.
