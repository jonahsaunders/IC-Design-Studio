# IHP inductor physical interfaces

The IHP KLayout verification option accepts explicit physical references for
`inductor` (two winding terminals and substrate) and `inductor3` (two ends,
center tap and substrate). Their simulation catalog entries remain unavailable:
this work supplies no inductance, loss, noise or frequency-dependent model.
Chunk 7 remains incomplete.

The public CDL format uses an `L` prefix with three or four terminals. A normal
SPICE inductor parser treats only two of those tokens as terminals. Studio now
converts the explicit physical record to an `X` comparison primitive, preserving
every terminal and W, S, D, turn count and multiplicity. Omitted multiplicity is
one; non-unit multiplicity is retained. Unknown, missing, duplicate, nonfinite
or unresolved parameters are rejected. No device is replaced by an ideal coil.

For the selected one-turn fixture, an independent reference is:

```spice
.subckt coil_coupon A B S
L1 A B S inductor w=2u s=2.1u d=25.35u nr_r=1 m=1
.ends coil_coupon
```

The center-tapped fixture orders its terminals A, C, B, S. Its public derived
D parameter is 25.85 µm: the 38.05 µm outer span minus two widths per turn and
two minimum spacings between turns. Independent mask measurements confirm
2 µm width, two turns and 2.1 µm minimum spacing. Its literal horizontal inner
opening is 25.84 µm because that cross-section's spacing is 2.105 µm; D is the
extractor's derived parameter, not that opening. The upstream sample reference
says 25.35 µm and uses a 5% geometry tolerance. That reference is retained as
source material. Studio preserves the public derived D value and does not add
the upstream tolerance.

## Recognition, wiring and comparison

The existing **Verify IHP layout with KLayout extraction…** action retains
the IND LA/LB/LC annotations and the `inductor2*`/`inductor3*` recognition text
through its private flattened stream. Ordinary child-local electrical labels
are still removed before flattening so they cannot become global connections.
Recognition annotations alone cannot satisfy the schematic's electrical ports.

A private, recorded correction to the pinned public extractor assigns native
terminal roles from those annotations under rotation. It does not assign the
annotation strings to electrical nets. Actual metal leads and conductor labels
establish the electrical port names. Every marked coil must survive unfiltered
native extraction. The source bundle remains byte-identical to its upstream
commit; each private correction is hashed and described beside the native run.

An independent wire check joins only TopMetal1, TopVia2 and TopMetal2 within
each IND marker. Every winding must be one physically connected conductor, with
its required role markers on the correct metal. Missing crossings, broken
winding segments, ambiguous annotations and unaccounted device markers fail
before the abstract device extractor can union the two metals. Fill and slit
purposes inside a winding remain unsupported by this supplemental check.

Full native Magic DRC and strict Netgen comparison remain required. DRC failures
are retained even when device comparison succeeds. These block checks do not
establish complete process, density, antenna, EM or fabrication acceptance.

## Reproducible fixtures

The original Apache-2.0 IHP layouts, reference netlists, license and source lock
are retained in `icstudio/assets/qualification/ihp-inductors`. They come from
[IHP's pinned public inductor regression](https://github.com/IHP-GmbH/IHP-Open-PDK/tree/5e6d592e4002946a4616f798c357f0f3c06cf3b6/ihp-sg13g2/libs.tech/klayout/tech/lvs/testing/testcases/unit/ind_devices).

The qualifier selects one complete coil from each source, adds terminal leads
and a separately contacted substrate, and records the crop and additions.
It explicitly removes decorative multiline dimension captions while preserving
all device recognition. The center-tapped source has a bridge with two edges
10 nm away from 45 degrees. Two vertices move 10 nm horizontally to make those
edges exactly 45 degrees without changing the crossing's horizontal boundaries.
The original and modified coordinates are recorded. Early failing geometries
and failed attempts remain in the execution evidence.

```text
python scripts/qualify_ihp_inductor_layouts.py --sources icstudio/assets/qualification/ihp-inductors --magic MAGIC --netgen NETGEN --klayout KLAYOUT --output build/ihp-coils
```

The script exercises four rotations of each fixture and deliberate winding,
crossing, lead, recognition, terminal, substrate and parameter faults. It also
checks GDS/OASIS mask and label preservation. Results describe these written
fixtures, not every legal winding geometry or the electrical operating envelope.

An added bridge between two turns originally passed both public DRC and native
device comparison: W/S/D/NR_R remained unchanged. The retained failing control
motivates a separate winding topology check. The two metal surfaces and their
contacted overlap islands must form a connected conductor tree. A contact array
within one overlap island counts as one junction, so redundant vias do not
create a false short report. A bridge that creates an independent conductive
loop fails this check even when the public device parameters still match.

OASIS export now refuses text it would otherwise replace with asterisks,
including multiline or non-ASCII text. It leaves an existing destination
untouched and directs the user to GDS or a text edit. Text appearance metadata
does not override the actual electrical text stored in a stream.

## October 19 execution

All eight positive layouts (both fixtures in four rotations) pass full native
DRC and strict LVS. All 28 deliberate faults are detected at the expected
extraction or comparison stage. Independent readback audits 44 native and
comparison netlists and 156 positive export layer pairs. Sixty-one focused tests
and both source desktop checks pass on each operating system. Nine Windows
staged-backend cases verify receipt of 486 files; the final two specifically
exercise the nominal center-tapped coil and the previously missed turn short.
Six prior native PNP/NPN/tap cases also pass after the extractor corrections.
Eight final gate tests pass per host after the runner is hardened to require
specific native findings and completed DRC. Tool crashes and missing evidence
cannot count as detected design faults.

The [execution record](validation/ihp-inductor-physical-2026-10-19.json) binds
these results to their sources, retained failures and recoverable evidence.
The native regression workflow repeats all 36 physical cases. These checks do
not provide an electrical coil model, continuous geometry qualification or
installed-release acceptance, and the unavailable catalog entries stay visible.
