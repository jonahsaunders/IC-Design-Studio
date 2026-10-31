# IHP SG13G2 standard 3.3 V transistor layouts

The linked-device generator supports the standard four-terminal
`sg13_hv_nmos` and `sg13_hv_pmos` views. Set the schematic dimensions and choose
**Generate linked PDK device**. Existing layouts use the same reviewed
regeneration flow; terminal identities survive editing and save/reopen.

| Parameter | Supported recipe |
| --- | --- |
| Total width W | 0.30–10 µm |
| NMOS length L | 0.45–10 µm |
| PMOS length L | 0.40–10 µm |
| Gate fingers `ng` | Integer 1–8; each channel has width W/ng, at least 0.30 µm |
| Parallel copies `m` | Integer 1–16; repeats the complete contacted device |
| Grid | 5 nm, including the divided channel width |

These are bounded generator limits, not the entire upstream PCell envelope.
They do not define temperature, bias, mismatch or reliability qualification.
The retained public model's measurement temperature does not establish a
complete temperature-validity range.

The [execution record](validation/ihp-hv-mos-layouts-2026-10-23.json) combines
168 passing valid layout checks and 158 detected faults. An independent audit
checks 5,414 channels in native netlists and exported masks. Both source editors
pass generation, editing, regeneration and save/reopen; all 56 affected tests
pass on each host. This is source-level sampled acceptance.

The original broad batch retains one failed test expectation: a removed PMOS
body contact produced both a disconnected body and public well-tap rule LU.a.
After correcting that classifier, only the affected full PMOS case was rerun.
The derived audit retains both original records and exact runner identities;
production geometry/extraction sources are identical across the two runs.
It does not claim that all cases were rerun with the revised classifier.
Independent review then tightened integrity and malformed-parameter controls.
The final checker re-audits all 158 recorded faults, including 102 ordinary
native mismatches and two deliberately aborted body extractions. All pass the
stricter checks. Thirteen focused tests include corrupted tools/assets/layouts,
ambiguous/nonfinite parameters, missing stages and altered comparison output.

The [public source bundle](qualification/ihp-hv-mos-sources-v1/README.md)
retains the exact upstream PCells, technology parameters, hashes, copyright
and Apache-2.0 license. The project keeps its existing license; upstream
files keep their original license. No private material is included.

The HV recipe uses the public implicit N+ definition, pSD where needed,
ThickGateOx on layer 44/0, and the 620 nm HV PMOS well enclosure. An explicit
nSD implant over the channel prevents standard MOS recognition in the public
KLayout extractor. The previous LV recipe remains unchanged: 378 sampled
LV dimension/finger/copy combinations match the parent geometry exactly,
excluding newly allocated object IDs. That comparison does not qualify the
legacy LV recipe in an additional extraction engine.

RF symbols are rejected by this ordinary-device generator. A shared compact
model name does not make standard and RF geometry interchangeable. The
KLayout extraction interface converts standard `rfmode=0` MOS instance
prefixes from M to X for the PDK's simulation view; it preserves every node,
model and numerical parameter. Ambiguous parameters, RF mode and duplicate
converted instance names fail closed.

Use both the full Magic flow and the selectable public IHP KLayout geometry
and extraction flow for this qualification. The public main and maximal
geometry decks remain unmodified. Magic alone misses the tested oxide
enclosure loss after its internal layer conversion; the public deck and
independent exported-mask audit detect it. Native LVS also merges equivalent
channels and ignores the intended finger grouping. The qualification runner
therefore reads every channel and diffusion group independently. These
additional grouping audits belong to the runner; an ordinary LVS pass alone
does not establish them.

Reproduce a new, fresh batch with:

```sh
python scripts/qualify_ihp_hv_mos_layouts.py --output /path/to/new-results --magic /path/to/magic --netgen /path/to/netgen --klayout /path/to/klayout --workers 4
python tests/gui_mos_fingers.py --ihp-hv --out /path/to/new-editor-results
```

`--pilot` checks four small device configurations, their fault controls and
one inverter in both engines. The default matrix includes minimum, interior
and maximum sampled geometry, all eight rotation/reflection combinations,
GDS/OASIS round trips, separately contacted multiplicity and four inverter
contexts. It retains failing engine output rather than treating a launch error
as a successful negative test. Full operating envelopes, extracted electrical
behavior, unsampled physical classes and installed release acceptance remain
separate requirements in the [family closure plan](CHUNK7_DEVICE_FAMILY_CLOSURE.md).
