# Public design DRC/LVS qualification

This suite imports independently authored open-source designs and checks them
with the same DRC/LVS runner used by the desktop. It records source defects as
expected failures, never as clean designs. Revisions and every downloaded file
are fixed in `examples/open-projects/public-layouts-lock.json`.

| Source | Circuit | Required physical result |
|---|---|---|
| [sgherbst/sky130-hello-world](https://github.com/sgherbst/sky130-hello-world/tree/e79c1a5413b9519d99b9f7d8fe907729bbb134ce) | SKY130 HD inverter and author's defective variant | Original LVS matches; standalone full DRC reports missing well/substrate tap context. Defective variant fails LVS and DRC. |
| [w32agobot/SKY130_SAR-ADC](https://github.com/w32agobot/SKY130_SAR-ADC/tree/4ae586d7f2125ebc84be04b9db950dde013463f4) | Comparator/latch | Zero full DRC errors and strict LVS match. |
| Same SAR-ADC source | Switched-capacitor common-mode generator | Zero full DRC errors and strict LVS match, using the separately pinned HD standard-cell library. |
| [diegohernando/caravel_fulgor_opamp](https://github.com/diegohernando/caravel_fulgor_opamp/tree/1c933884cd95acffbe35a9214e43f7433b6e6380) | Miller-compensated amplifier | Original full DRC is clean; strict LVS rejects the reversed compensation-capacitor plate connections. A separate corrected schematic rotates C1 by 180 degrees and must pass. |

All three repositories use Apache-2.0. Source files and their license notices
are preserved. The amplifier correction is a separately named Studio project;
the author's original schematic remains a required failing comparison.
It is a connectivity correction, not an analog performance qualification.

## Desktop workflow

1. Import a layout and link its matching, checksummed physical PDK.
2. Choose **Verify → Physical verification → Run layout DRC / LVS only…**
   (also available in the Physical workflow panel).
3. Select a self-contained schematic SPICE reference and its top cell.
4. Review the separate DRC and LVS stages, retained engine logs and findings.

The job uses the selected Included or Custom physical tools, and can use the
private WSL runtime on Windows. The schematic reference is captured when the
job is queued. Missing tools or PDK prerequisites produce a blocked report.
DRC failures do not suppress the independent LVS check. Editing marks old
results stale; DRC findings navigate to the recorded layout coordinates.
No simulation testbench is required for this action.

The private verification stream is flattened to avoid Magic's hierarchical
array extraction defects. All mask geometry is checked by exact region XOR
before and after writing the stream. Repeated child-local labels are removed
from that private copy so they cannot short unrelated nets. Original source,
editable hierarchy and exported GDS are retained unchanged. Explicit top
pin-purpose labels must agree with the schematic. Older label-only GDS uses
the selected schematic terminal list; missing physical labels still fail.
Layouts relying on implicit, unlabeled bulk terminals need an explicit
top-level integration interface; the standalone inverter diagnostic is
therefore qualified separately from the desktop examples.

## Compatibility repairs covered

- Standard non-electrical Xschem title/launcher artwork is archived without
  applying electrical-symbol editing bounds to it.
- Legacy `[start..end]` instance arrays expand with the same bounded electrical
  rules as `[start:end]` arrays.
- Declarative standard-cell supply attributes and doubled-backslash model-name
  separators survive native migration and Xschem export/reimport.
- The explicit SKY130 varactor simulation default `VM=1` is omitted from native
  LVS emission, consistent with its model default and Magic extraction. Width,
  length, `m` and all non-unit `VM` values remain checked; simulation is unchanged.
- Stream comparison accepts equivalent array traversal reversal and unused
  singleton pitch normalization. Actual placement, pitch, multiplicity,
  geometry, labels and units must still agree.

## Reproduction

Use the locked physical adapter already produced by
`scripts/prepare_sky130_qualification.py`, and build the pinned Magic/Netgen
engines with `scripts/build_physical_engines.py`.

```sh
python scripts/fetch_sky130_reference.py --output build/public-full-pdk
python scripts/qualify_public_layouts.py \
  --source build/public-sources \
  --pdk build/physical-adapter/sky130A \
  --standard-cells build/public-full-pdk/sky130A/libs.ref/sky130_fd_sc_hd/spice/sky130_fd_sc_hd.spice \
  --xschem-libraries build/public-full-pdk/sky130A/libs.tech/xschem \
  --out build/public-layout-evidence \
  --magic "$PWD/build/physical-engines/installed/bin/magic" \
  --netgen "$PWD/build/physical-engines/installed/bin/netgen"
QT_QPA_PLATFORM=offscreen python tests/gui_public_layouts.py \
  --evidence build/public-layout-evidence \
  --pdk build/physical-adapter/sky130A \
  --out build/public-layout-desktop \
  --magic "$PWD/build/physical-engines/installed/bin/magic" \
  --netgen "$PWD/build/physical-engines/installed/bin/netgen"
```

Use `--managed` instead of custom executable arguments for the desktop probe
when the included runtime is installed. Use a fresh output directory per run.
The `public-layouts` matrix entry in the physical-qualification workflow runs
the source qualification and real Linux desktop probe continuously.

## Evidence and scope

The suite retains the exact author and native netlists, source captures,
reference/library hashes, original and rewritten streams, native projects,
full DRC findings, strict Netgen reports, source-engine identities and an
artifact manifest. It checks GDS and OASIS after an independent KLayout rewrite
without Studio sidecars, and compares migrated and reopened Xschem circuits
against the author's electrical netlist. Deliberate DRC and device-width LVS
faults must fail. The desktop probe also edits, navigates and undoes a real
physical defect.

Passing the suite means these recorded paths preserve the expected results,
including correctly rejecting defective sources. It does not mean every
source design passes DRC/LVS. These results do not qualify Cadence/OpenAccess,
other PDKs or tool versions, full-chip antenna/density checks, extracted analog
performance, or foundry signoff.
