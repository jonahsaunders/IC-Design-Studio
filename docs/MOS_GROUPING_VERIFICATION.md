# MOS finger and physical-copy verification

The ordinary layout checker and saved-testbench flow now check standard GF180
C/D 3.3 V and IHP LV/HV MOS finger grouping separately from native LVS. The public
comparison setup merges equivalent devices and ignores `nf`/`ng`, so native LVS
can pass a schematic with the wrong finger count or physical-copy grouping.

The added check reads actual diffusion and gate masks, locates every native
channel inside one complete channel polygon, and associates each diffusion group
with its model, gate, body and drain/source pair. It compares that group with the
captured schematic's W, L, finger count and multiplicity. Equal total width,
channel counts or global group counts cannot substitute for the correct groups
on each net. Retained native node correspondence handles renamed internal nets;
ambiguous correspondence is not accepted.

`mos_grouping` has its own result and evidence. A failed grouping check leaves
the actual native LVS result unchanged and fails application acceptance. The
saved-testbench path stops before capacitance extraction and post-layout
simulation. Its failure receipt still verifies the captured source, native
outputs, added proof, tools and reviewed package dependencies. Unsupported
expressions, hierarchy or model interfaces display `NOT_CHECKED` with the reason.

The implementation authenticates the reviewed package content, model definitions
and native technology dependencies. Native positions and dimensions use the
retained extraction scale, independently checked against the engine's output
scale, following the [Magic extraction format](https://opencircuitdesign.com/magic/manpages/ext_manpage.html).
The public rule decks and comparison rules are unchanged.

This closes a reproduced application acceptance gap. It does not establish full
MOS operating envelopes, calibrated extraction, electrical accuracy, statistical
or reliability applicability, installed acceptance, or complete-family status.
Earlier geometry receipts retain their original runner-only grouping checks.
