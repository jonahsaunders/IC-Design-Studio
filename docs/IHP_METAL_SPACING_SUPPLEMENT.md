# IHP wide-metal spacing correction

The public IHP verification route now runs a versioned supplemental check for
M2–M5 rules Mn.e and Mn.f after the two complete, unchanged public decks. The
original reports remain visible and authenticated. The supplement adds native
findings to the application's DRC result; it cannot turn an original failure
into a pass. This is a correction to selected geometry checks, not full process
or manufacturing qualification.

The defect was reproduced with two independently connected 7 × 7 µm capacitors.
Their original Metal5 plates are 8.2 µm wide, have an 8.2 µm parallel edge, and
are separated by 220 nm. The pinned rule requires 240 nm in that context, but
both unmodified public decks reported zero findings. The main deck logged that
M5.e executed. Its erode/dilate operation selects wide metal as a subset of the
original layer; default shielding prevents the separation operation from seeing
past identical overlapping shapes. The failed negative tests are retained.

KLayout documents this exact subset-shielding limitation and the `transparent`
option in its [DRC layer reference](https://klayout.de/doc/about/drc_ref_layer.html#width).
The supplement preserves the pinned layer mapping, morphology, thresholds and
parallel-length expressions and changes only this separation option. Source
definitions come from the authenticated Apache-2.0 IHP bundle at
`5e6d592e4002946a4616f798c357f0f3c06cf3b6`; upstream sources and their notices are
unchanged. Current values are 240 nm spacing for width greater than 390 nm and
parallel length greater than 1 µm, and 600 nm for width and parallel length
greater than 10 µm. The recipe does not redefine those applicability conditions.

Native regression covers 44 selected contexts across all four metals and both
rules: both rules’ distance boundaries, Mn.e width and parallel-length
boundaries, rotations, selected
45-degree geometry, wide/narrow pairs, touching/single shapes, a thin branch and
a U-shaped notch. Independent readback also checks the complete isolated
capacitor flow. These finite examples do not establish all polygon classes.

The missed 220 nm gap now reports two oppositely directed edge-pair markers for
one physical gap. Counts retain the native markers rather than claiming two
distinct defects. Legal 240/260 nm gaps remain clean. All six capacitor contexts
retain two raw extracted devices, four distinct ordered terminals and strict LVS.

Fresh results use DRC schema 2 with ordered `main`, `maximal` and `metal-spacing`
reports. The third report binds its generated recipe, original rule dependencies,
input, native command, eight rule-completion markers and raw report. Application
coverage checks and the independent installed-capacitor reader require it.
Missing or altered evidence fails. Older two-deck records retain their historical
scope and acquire no supplemental coverage. The historical MIM.g boundary reader
continues to audit its original two-deck experiment only.

The focused checks are:

```text
python -m unittest tests.test_ihp_metal_spacing tests.test_ihp_klayout_drc tests.test_layout_verification tests.test_frozen_ihp_cmim
```

The [validation record](validation/ihp-metal-spacing-supplement-2026-11-03.json)
binds the reviewed sources, original failures and retained raw evidence.

Fresh Windows/Linux installed acceptance remains separate from these reviewed
source changes and native experiments. The [device requirements](IHP_CMIM_REQUIREMENTS.md)
and [progress tracker](QUALIFICATION_PROGRESS.md) retain the open family gate.
