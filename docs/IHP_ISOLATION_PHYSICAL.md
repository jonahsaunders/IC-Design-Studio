# IHP isolation-box physical checks

The IHP public KLayout route preserves all three `isolbox` terminals and the
internal body/tap connection in an isolated transistor. The
[execution record](validation/ihp-isolation-physical-2026-10-21.json) covers
selected geometry and connectivity checks on the bundled IHP revision
`cfb96b74cf33877e`. It does not qualify the complete device envelope or finish
chunk 7.

## Corrected interfaces

The public extractor writes an isolation box as a **three-terminal** `D` record:
isolated p-well, NWell and substrate. The comparison adapter preserves those
roles, converting the record to a three-terminal subcircuit instance. Reference
W/L becomes the public extractor's outer area `W*L` and perimeter `2*(W+L)`.
Native A/P is retained exactly. Unknown parameters, missing terminals, changed
source hashes and duplicate instance names are rejected.

The pinned public connectivity deck connects the isolation terminal to the
buried n-layer but omits its contacted NWell ring. Generic n-tap recognition
also excludes this ring because it overlaps diode recognition. A hash-checked
copy of the deck now retains the physical buried-region/NWell overlap and the
n-active ring's contact path. Metal connections are unchanged. The original
upstream deck and bundled package remain unchanged; the verification job records
the exact correction and both source hashes.

The private flattened verification stream also retains the public Text/0
annotations `isolbox`, `well` and `sub!`. These identify isolation and tap
devices; they are not electrical net labels. Ordinary internal conductor labels
remain local. Previously, removing a child cell's `sub!` annotation could lose
the tap resistor and collapse the MOS body connection into the source net.

## Executed coverage

All native checks use KLayout 0.30.5, the complete public IHP main and maximal
DRC decks, unfiltered public extraction and strict Netgen comparison.

| Check | Result |
| --- | --- |
| Five rectangular isolation sizes, four rotations | 20 passing layouts |
| Public three-terminal D/A/P references | 5 passing references |
| Isolation contact, terminal, recognition and geometry faults | 70 detected faults |
| Isolated transistor, internal tap and isolation box; four rotations and both reflections | 8 passing layouts |
| Mixed-circuit body, gate, tap, well and geometry faults | 10 detected faults |
| Contact-enclosure boundary, four rotations | 4 expected DRC failures and 8 passes |
| Existing 2 x 2 micrometre n-tap and p-tap paths | Both layouts and A/P references pass; 12 faults detected |
| Affected Python suites | 80 tests pass on Windows and 80 on Linux, zero skips |
| Windows staging, local Linux execution and returned artifacts | 5 cases pass their expected outcomes; 885 file receipts verified |

The five isolation sizes are 4.06 x 4.06, 6 x 6, 6 x 12, 12 x 6 and
12 x 12 micrometres. The ring width is 1.05 micrometres and PWellBlock is zero.
The 6 x 6 well, active, recognition, buried-layer and pin masks independently
match the pinned public layout. Each sample passes save/reopen and GDS/OASIS
geometry and label checks.

The boundary is specific to the selected 0.78-micrometre body contact. Its
required buried-layer enclosure is 1.24 micrometres on each side, and the
buried layer is inset 0.4 micrometres from the outer isolation edge:
`0.78 + 2*1.24 + 2*0.4 = 4.06 micrometres`. At all four rotations, 4.05 fails
exactly `nmosi.b`, while 4.06 and 4.07 pass. LVS and integrity still pass for the
below-boundary samples. This is not a universal minimum isolation-box size.

The mixed fixture comes from the pinned public `inmos` layout. Its 0.15 x 0.13
micrometre MOS channel, 0.78 x 0.78 tap and 6 x 6 isolation dimensions remain
unchanged. The fixture adds an external contacted substrate connection and
completes the NWell ring contacts, corrects the gate contact landing, and moves
the tap 0.15 micrometres inward to meet buried-layer enclosure. These fixture
changes are explicit in the generator. The unfiltered native circuit must
contain exactly the MOS, tap and isolation devices with the expected internal
body graph and every extracted geometry parameter.

## Reproduction

Use new output directories and the project's pinned native tools:

```sh
python scripts/qualify_ihp_isolation_layouts.py --workers 2 --output /path/to/new-isolation-results --magic /path/to/magic --netgen /path/to/netgen --klayout /path/to/klayout
python scripts/qualify_ihp_isolation_context.py --workers 2 --output /path/to/new-context-results --magic /path/to/magic --netgen /path/to/netgen --klayout /path/to/klayout
python -m unittest tests.test_ihp_isolation_lvs -v
```

The coil physical-qualification workflow runs the isolation pilot and the full
mixed-context suite. The full local isolation matrix and retained failures are
bound to the validation record. An independent audit on both hosts checks 48
native netlists, 10,010 artifact hashes, 528 stream-layer comparisons and the
Windows receipts. These source runs are not installed-release acceptance.

## Repeated isolated-transistor cells

The [hierarchy follow-up](validation/ihp-isolation-hierarchy-2026-10-21.json)
checks two instances of the same isolated-transistor cell. The second instance
is rotated, reflected and translated; the complete pair is checked in all four
orientations. Both devices share the physical substrate, while their NWell,
drain, gate, source and internal isolated-body connections remain separate.

All four layouts pass full public DRC and strict LVS. Unfiltered native
extraction must retain exactly six devices, two distinct internal bodies, and
all MOS, tap and isolation geometry parameters. Six incorrect references
deliberately merge the bodies, cross the tap, NWell or gate connections, or
alter the second tap/isolation geometry. All six fail native comparison while
DRC, extraction and artifact integrity remain successful.

The same check passes through Windows staging and local native execution;
the merged-body control fails as required. Both returned six-device circuits
and all 356 artifact receipts are audited. Independent audits on both hosts
verify ten raw/comparison graphs, 1,300 integrity bindings and 104 stream-layer
comparisons. Three additional unit tests per host verify repeated-cell
recognition and rejection of merged/crossed graphs. The source archive can be
restored to reproduce a valid circuit and a merged-body rejection.

```sh
python scripts/qualify_ihp_isolation_hierarchy.py --output /path/to/new-hierarchy-results --magic /path/to/magic --netgen /path/to/netgen --klayout /path/to/klayout
python -m unittest tests.test_ihp_isolation_hierarchy -v
```

This regression is also included in the coil physical-qualification workflow.
It closes the sampled repeated-cell connectivity gap; the complete device
envelope and remaining chunk-7 requirements below are unchanged.

## Sources and limits

The reference PCell, GDS, CDL and public schematic are retained under
`icstudio/assets/qualification/ihp-isolation`, with their Apache-2.0 license,
exact upstream paths, Git object identities and SHA-256 hashes. They come from
IHP-Open-PDK commit `5e6d592e4002946a4616f798c357f0f3c06cf3b6`. The project does
not relicense those upstream files or introduce a private rule package.

The archive retains the exploratory failures: lost recognition, disconnected
NWell contacts, undersized contact/enclosure, a crossed signal route, and the
missing internal tap. The final boundary and fault controls require the actual
native rule or connectivity failure; a tool crash is not a passing control.

Complete geometry/option ranges, electrical bias/temperature and reliability
envelopes, statistical behavior and final installed-release acceptance remain
open. The electrical model and default process revision are unchanged. Other
missing catalog bindings and device-family gaps still prevent chunk 7 completion.
