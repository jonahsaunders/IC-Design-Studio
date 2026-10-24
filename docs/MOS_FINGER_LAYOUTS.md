# GF180 and IHP shared MOS fingers

The standard four-terminal GF180 C/D 3.3 V and IHP SG13G2 1.2 V
generators support 1–8 shared-diffusion gate fingers. Use `nf` for GF180
or `ng` for IHP. `W` remains the total width of one complete device;
each physical channel is `W / fingers` wide. `m` independently repeats
the complete contacted device 1–16 times.

Set these schematic parameters and choose **Generate linked PDK device**.
For existing geometry, review and apply regeneration. The four terminal IDs
survive editing, regeneration and save/reopen. Inverter placement accounts
for both devices' complete finger rows and parallel arrays.

| Process | Total W | L | Minimum W per finger |
| --- | --- | --- | --- |
| GF180 C/D | 0.22–10 µm | 0.28–10 µm | 0.22 µm |
| IHP SG13G2 | 0.15–10 µm | 0.13–10 µm | 0.15 µm |

Dimensions and per-finger width must lie on the 5 nm grid. Finger and copy
counts must be integers. Incompatible parameter emission is rejected.
One-finger geometry retains the earlier behavior: 216 sampled combinations
of width, length and multiplicity compare identically with the parent code,
excluding newly allocated object IDs.

The [execution record](validation/mos-finger-layouts-2026-10-23.json) covers
144 device layouts in all eight rotation/reflection combinations and twelve
mixed-finger inverter contexts. All pass full native DRC and strict LVS.
GDS/OASIS round trips preserve the device geometry. Both source desktops
pass generation, undo/redo, parameter editing, regeneration and save/reopen.

Native LVS ignores `nf`/`ng` and merges electrically equivalent devices.
The qualification runner therefore also reads every native channel's model,
four terminals and dimensions, then independently checks the exported masks
for the intended diffusion groups and fingers per group. These added checks
are part of this runner; an ordinary native LVS pass alone does not establish
the same physical grouping.

All 222 deliberately faulty cases are detected:

- 126 produce native LVS mismatches.
- 36 lose or merge an extracted top-level port. Completed native extraction,
  the actual changed ports and retained geometry establish these failures;
  setup errors do not satisfy the controls.
- 30 wrong-finger references pass native LVS but fail exact channel readback.
- 30 electrically equivalent wrong-grouping references pass native LVS and
  channel readback but fail the exported diffusion-group check.

Independent audit checks 7,182 channels in both native netlists and exported
masks, plus 10,098 file, PDK and engine bindings. Reproduce the batch with:

```sh
python scripts/qualify_mos_finger_layouts.py --output /path/to/new-results --magic /path/to/magic --netgen /path/to/netgen --workers 2
python tests/gui_mos_fingers.py --out /path/to/new-editor-results
```

`--pilot` selects six small devices and three inverter contexts with 72
fault controls. The recorded archive restore reproduces this pilot and the
58 affected tests using the exact final source.

This is sampled geometry and connectivity evidence. Complete operating
envelopes, unsampled geometry, extracted RC and performance, mismatch,
reliability, other device families and final installed acceptance remain
open. The native tools and PDK assets are unchanged. All added code is
project code; this change imports no additional third-party asset.
