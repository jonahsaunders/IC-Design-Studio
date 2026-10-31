# Mixed IHP NPN and SVaricap verification

The public IHP geometry route runs the complete main and maximal KLayout decks,
the written-oxide check, and an additional native Magic check wherever TRANS
26/0 is present. Strict extraction and LVS use the original physical layout.
The native supplement detects unrelated active or well islands inside an NPN
that the two public decks can miss.

## Large varactor recognition

The original Magic importer grows the varactor gate twice by 480 nm and clips
the result to active. That bounded operation can split a large SVaricap and
cut holes out of its buried well. The resulting native well and tap findings
are import artifacts on the retained large Nx10 mixed fixture.

The combined route now derives private recognition markers from the pinned
public gate, active, well, buried-layer and SVaricap text operands. Its complete
public rule source remains commit `5e6d592e4002946a4616f798c357f0f3c06cf3b6`.
The main deck defines whole-active and whole-well SVaricap recognition. The
maximal deck excludes SVaricap operands from NW.c1, the coincident varactor tie
from NW.f, and SVaricap ties from its latch-up operand. The main NBL.f rule
excludes findings in the recognized varactor well. Both complete public decks
continue to enforce these definitions on the original stream.

`ihp_varactor_context.py` applies those contexts only to the additional native
check. It restores written buried-well continuity within the recognized well,
uses the public varactor tie context, and scopes native NW.c1, NW.f and NBL.f
applicability. No native finding is removed from the resulting report and no
numerical rule limit changes. This supplement is not an independent replacement
for either public deck.

The private GDS uses markers 250/0 and 251/0. A collision with input layers is
an error. Missing recognition, incomplete written oxide, nonorthogonal geometry
or off-grid context receives no correction. Context may not overlap an NPN
TRANS region, including the adjacent 5 nm grid step. Native edge checks need
both lattice positions beside an edge, so the marker interval is closed by one
internal grid step on all four sides. The native script requires the tested
5 nm scale and actual imported mask hints before applying that closure.

## Preservation and provenance

Only the private native verification input contains those markers. Removing
them and rereading the stream must reproduce every cell, placement, physical
layer, label and label-presentation attribute. The source and the editable
project are unchanged. The private stream, readback, original hashes, derived
rule hashes and complete native logs are retained in the job evidence.

All native dependencies must match the preflight capture, and the modified
operands additionally require their exact pinned source hashes. Derived source
files retain upstream Apache-2.0 notices and identify the modifications.
An invalid technology section or missing include cannot pass just because Magic
prints a zero violation count and exits successfully.

## Repeatable controls

`scripts/qualify_ihp_mixed_layouts.py` checks all three NPN families paired with
small Nx1, small Nx4 and large Nx10 SVaricaps. Four rotations per pair retain
both devices, their dimensions and terminal roles through saved-project and
GDS/OASIS exchange. Each pair requires nine specific rejected controls: emitter
open, NPN multiplicity, oxide gap, missing recognition, gate short, varactor
multiplicity, substrate reference, unrelated diffusion and unrelated well.
The hosted IHP workflow runs this same recipe with the large case by default.

The October 21 execution additionally checks every mirrored rotation: 24
complete positive layouts and all 27 full-flow faults pass. Separate native
controls cover 24 valid layouts and 48 unrelated-diffusion/well faults. On each
host, independent readback verifies 4,200 artifact bindings and 117 private
streams, including full text presentation after removing only the two private
markers. Five actual Windows-to-Linux handoffs accept two large layouts and
detect three physical faults; all 1,074 returned files are verified.

These sampled layouts establish this integration's scope. Other mixed-device
combinations, complete electrical operating envelopes and installed-release
acceptance remain separate chunk-7 requirements.
