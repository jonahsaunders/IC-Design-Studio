# IHP bipolar layout verification

The [execution record](validation/ihp-bipolar-layouts-2026-10-17.json) adds
ten sampled `pnpMPA` layouts with zero full Magic DRC findings, public KLayout
extraction and strict Netgen LVS. All 35 deliberate faults are detected.
This closes the sampled PNP extraction gap; chunk 7 remains in progress.

## Use and reproduce

For an IHP project, choose **Verify → Physical verification → Verify IHP layout
with KLayout extraction…** and select a self-contained schematic reference.
The ordinary DRC/LVS action continues to use Magic extraction. Both routes
retain the exact project, original GDS, reference, source identities and logs.
The included Linux/WSL backend transfers and verifies the additional rule bundle.

```sh
python scripts/qualify_ihp_pnp_layouts.py --output /new/pnp-results --magic /path/to/magic --netgen /path/to/netgen --klayout /path/to/klayout --workers 4
```

The five W/L pairs are 2/0.7, 2/5, 10/0.7, 2/7 and 7/2 micrometres.
Each passes at 0 and 90 degrees, with save/reopen and independent GDS/OASIS
exchange preserving every mask and electrical annotation. The reference uses
collector/base/emitter order and independently calculated emitter area/perimeter.
Negative controls remove contacts from each terminal, short collector/emitter,
reverse the reference polarity, or alter reference area or perimeter by 20%.
The short also crosses the base ring; it is not claimed as an isolated two-net
short. Independent readback checks all 45 native and 45 comparison netlists,
all mask changes, extracted geometry and fault locations.

## Why a second extraction route is needed

The bundled public Magic input deck recognizes PNP devices through a small
deep-nwell heuristic. Larger sampled shapes disappear from its extracted
circuit even when DRC passes. The original failing runs remain in the evidence.
This does not justify changing the expected schematic or suppressing a check.

The additional [public IHP runset](https://github.com/IHP-GmbH/IHP-Open-PDK/tree/5e6d592e4002946a4616f798c357f0f3c06cf3b6/ihp-sg13g2/libs.tech/klayout/tech/lvs)
recognizes PNP emitter, base and collector from the process masks. Studio retains
its unmodified files, original copyright headers, Apache-2.0 license and exact
hash inventory [with the bundle](../icstudio/assets/physical/ihp_klayout_lvs/README.md).
The project's adapter remains GPL-3.0 code. No private source or remote checking
service is used.

Studio explicitly disables comparison alignment, simplification, combining,
purging and implicit net connections during extraction. An early exploratory
run of the upstream comparison emitted a match after dropping unmatched NPN
circuitry. That result is retained as a failure, not acceptance. Studio checks
the unfiltered extracted circuit, rejects empty output and missing interfaces,
then requires strict Netgen device/property/port matching.

Two recorded interoperability conversions are required. The private engine
input duplicates IHP datatype-2 pin text onto datatype 25, which the public
KLayout runset reads. Original pin text, coordinates, masks and user exports
remain intact. The native BJT `Q` instance prefix becomes `X` for the same public
IHP subcircuit model, terminal order and parameter text expected by Netgen.
No extracted number is adjusted. Unknown BJT interfaces and duplicate converted
instance names are rejected; raw output is always retained.

## Validation and remaining work

Forty focused regression tests pass on Windows and Linux. The source desktop
action is exercised on both hosts; a captured choice executes through a staged
local backend and its returned evidence is verified. Fourteen representative
default-route MOS, resistor and MIM layouts pass across SKY130, GF180 C/D and IHP.
These are source/runtime checks, not acceptance of the previously installed
desktop executable. Earlier digital production-gate source bytes remain
preserved separately and retain their original scope.

The NPN/HBT pilot still exposes generator terminal, recognition, dimension and
DRC failures. This PNP batch does not qualify those devices, continuous geometry
or operating ranges, thermal/RF/statistical behavior, complete-chip rules or
manufacturing signoff. The remaining device families and installed release
acceptance continue to block completion of chunk 7.
