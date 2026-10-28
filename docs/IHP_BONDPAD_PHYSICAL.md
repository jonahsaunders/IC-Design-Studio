# IHP selected square bondpad geometry

The source desktop can attach an unstacked square TM2 bondpad to an existing
explicit cell port through **Layout → Generate → Generate IHP bondpad…**.
The form previews the candidate and uses the ordinary reviewed, undoable
application change. A layer locked after preview still prevents Apply.
No electrical device or model include is added; `sg13g2_pr/bondpad.sym`
remains unavailable. This closes a selected physical-interface requirement,
not the bondpad electrical binding, full family or chunk 7.

The API is `icstudio.ihp_bondpad.install(project, cell_id, port, parameters)`.
It requires an already declared scalar cell port without a physical anchor.
The three written masks are TM2 drawing `(134,0)`, dfpad drawing `(41,0)`
and Passiv drawing `(9,0)`. Both metal and dfpad use the same rectangle;
the opening is inset by 2.1 um on every side. The ordered terminal list has
one entry, the existing port, at the supplied center on TM2; its text uses
the application's normal IHP pin purpose `(134,2)`. Save/reopen and stream
sidecars retain the initial recipe and exact source lock.

The [public PCell](https://github.com/IHP-GmbH/IHP-Open-PDK/blob/5e6d592e4002946a4616f798c357f0f3c06cf3b6/ihp-sg13g2/libs.tech/klayout/python/sg13g2_pycell_lib/ihp/bondpad_code.py)
comments that the pad has zero pins yet sets `pin#=1` and `ignore=TRUE` with
an unexplained-value comment. Its selected branch emits no pin object. The
application anchor is an explicit physical port adaptation. The public
electrical file declares `bondpad PAD` and parameters but has no elements;
it does not provide capacitance, substrate coupling, loss or pad protection.

Source originals, Apache-2.0 notices, public paths and Git-blob/SHA-256 identities
are retained in `icstudio/assets/qualification/ihp-bondpad`. They are from
IHP commit `5e6d592e4002946a4616f798c357f0f3c06cf3b6`. The source-lock SHA-256 is
`0811e348eb273f5827ff3f7ffb5fa32a7380f8ba53189a4c3004816c04661895`.
The independent source oracle executes the unchanged authenticated `genLayout`
method with a rectangle-call recording adapter and the public floor/grid
functions. This checks the selected public branch; it is not a native CNI run.

The supported class is square, TM2, stack/fill/filler-exclusion disabled,
non-flip-chip. The public Pad.i rule prohibits dfpad without TM2, so this
recipe does not offer a TM1 bondpad. Positive diameter is entered as exact
integer nanometres on the 10 nm diameter grid; center coordinates use 5 nm.
Height/width quota follows the public square branch. The application rejects
quotas that would invoke the public 10 um fallback or silently round a radius.
The 2.1 um opening inset must leave a positive opening. Coordinates must fit the
existing signed 32-bit stream format. These are explicit representation and
source-equation constraints; they are not physical validity or reliability
ratings. Other shapes, stacked vias/metals, fill, filler exclusion, flip-chip,
probe pads and alternate enclosure values require their own implementation
and acceptance. Direct geometry edits require fresh written-mask comparison.

The focused Windows and native-Linux suites each pass ten tests. Real geometry
is written for sixteen selected variants: 80 um diameter with height/width
quotas 0.5, 1 and 2, plus the next exact 80.01 um diameter at quota 1, each in
four rotations. All 32 GDS/OASIS files per host match independently recorded
public masks and the named terminal. Eleven deliberate written-layout faults
are rejected, covering changed/open metal, missing/wrong masks, a widened
opening, an extra island and changed/moved/extra/purpose-invalid port text.
Source tampering, source-domain fallback/rounding, invalid dimensions,
incompatible process/layers and duplicate or absent physical ports also fail.
An injected dirty native positive is retained and rejected by the native gate.

One actual 80 um square pad passes both complete unmodified public IHP main
and maximal geometry decks with KLayout 0.30.5: zero findings. Removing TM2
produces exactly one main-deck `Pad.i` finding. Every finding is retained;
no chip-context rule is filtered. This is one selected pad, not native DRC
acceptance of all sixteen variants. In particular, the public Pas.c check is
conditioned on sealring context, so a clean standalone coupon does not establish
that complete-chip context. Antenna, density and fabrication acceptance remain
separate. No LVS or electrical pad-model acceptance is claimed.

The original control gate rejected the native category representation
`'Pad.i'` because it compared only the bare name. That failed record and the
completed native reports are preserved. The repaired gate accepts the two exact
representations, requires a nonzero corresponding finding and requires a clean
positive. Final native readback authenticates the original reports and source
inputs without repeating unchanged DRC. Windows source-Qt execution also passes
the actual action/form/review, late layer lock, undo/redo, save/reopen and both
written-stream checks. It is source desktop evidence, not installed acceptance.

```text
python -m unittest discover -s tests -p test_ihp_bondpad.py
python scripts/qualify_ihp_bondpad.py --output NEW_DIRECTORY --klayout KLAYOUT
python tests/gui_ihp_bondpad.py --out NEW_GUI_DIRECTORY
```

Six default gaps remain exact catalog requirements: the optional SKY130 ESD
correction has not been promoted; SKY130 RF pw2dn isolation behavior, exact
fixed-layout 11p3x11p8 VPP, and IHP bondpad, inductor and inductor3 electrical
definitions remain unresolved in the default package.
This physical pad milestone changes none of those device statuses or family
completion gates. Chunk 7 remains incomplete; its engineering completion
estimate is managed in the project tracker rather than inferred from these tests.
