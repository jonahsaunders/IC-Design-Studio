# Public IHP capacitor electrode evidence

`physical-evidence.zip` is a 75,922-byte, immutable subset of the retained
[catalog-reference experiment](../../validation/ihp-cmim-catalog-reference-2026-11-02.json).
It contains twelve original files, copied byte-for-byte, plus the applicable
Apache-2.0 and project GPL-3.0 license texts. `SOURCE.json` identifies every
selected member, the upstream sources and the original archive digest.

This makes the process-control comparison reproducible from a public checkout.
It replays the selected historical 7 × 7 µm device's project, written masks,
labels, extracted circuit, native reports and ordered extractor definitions.
It establishes the selected `c0`/`PLUS`/TopMetal1 and `c1`/`MINUS`/Metal5 mapping.
The subset does not verify omitted contents of the original archive. It also
does not provide a fresh physical extraction, supplemental metal-spacing
coverage, installed acceptance, calibrated electrical limits or full-family
qualification.

Both [comparison commands](../../IHP_CMIM_PROCESS_CONTROL.md) use this archive
by default. Their source contract pins its bytes and manifest; the reader
checks the original physical evidence and source dependencies before and after
the native comparison. The explicit `--physical-archive` option also accepts
the exact original audited archive. Arbitrary layouts, modified evidence and
otherwise equivalent ZIP repacks are rejected; the option is not a generic
layout-import interface.

The three retained LVS files keep the original IHP copyright and license
headers. Their source lock is
[the public LVS bundle](../../../icstudio/assets/physical/ihp_klayout_lvs/SOURCE.json).
The generated layout's pinned public Magic source is recorded in
[the application reference fixture](../../../icstudio/assets/qualification/ihp-cmim-reference/SOURCE.json).
No model coefficient, public rule or acceptance limit was changed to construct
this subset.
