# IHP `cap_cmim` minimum-boundary source pilot

This finite source experiment checks five complete, imported rectangular devices at 0° and 90° against the pinned public IHP geometry decks and strict physical comparison. It does not qualify the default Magic PCell, the full device family, an installed release, electrical accuracy or fabrication. The [execution record](validation/ihp-cmim-minimum-boundaries-2026-11-02.json) binds the raw evidence, independent review and source/runtime identities.

The pinned public table specifies a 1.14 µm minimum MIM width and 1.3 µm² minimum MIM area. Each row below was checked at both rotations. All ten completed extraction and strict LVS. The main deck reported no findings for these ten layouts; the maximal deck reported the listed findings.

| MIM dimensions (µm) | Area (µm²) | Maximal-deck result per rotation |
| --- | ---: | --- |
| 1.12 × 2 | 2.24 | One MIM.a width finding |
| 1.14 × 2 | 2.28 | Zero findings |
| 1.16 × 2 | 2.32 | Zero findings |
| 1.14 × 1.14 | 1.2996 | One MIM.f minimum-area finding |
| 1.14 × 1.16 | 1.3224 | Zero findings |

The area cases bracket the published limit; neither claims an exact 1.3 µm² geometry. Magic also passed the 1.14 × 2 and 1.16 × 2 µm layouts at 0°, with all six stages passing and zero findings. Magic results are separate from the public decks and do not establish MIM.g maximum-area coverage.

## Imported contact and physical checks

The source Magic draw procedure produced no written Vmim contact at the two initial widths. Its contact region is inset by 0.2 µm per edge; the pinned CIF output uses a 420 nm cut with its own square-grid construction. The experiment retained those missing-contact failures and explicitly added one centered 420 × 420 nm Vmim rectangle on layer 129/0 to each imported layout. The public LVS documentation identifies Vmim as an alternative to TopVia1 inside MIM. This is a declared mask modification, not unchanged PCell output; the original 2–30 µm PCell parameter-check clamp is unchanged.

Independent written-mask readback checked exact dimensions and rotation, the added contact, GDS/OASIS exchange, and ordered C1 TopMetal1 and C2 Metal5 ports. The measured minimum distance from the contact to the MIM edge is 350 nm for the 1.12 µm case, 360 nm at 1.14 µm and 370 nm at 1.16 µm. The pinned main-deck MIM.d enclosure check operates on TopVia1 layer 125/0, not Vmim 129/0; these measurements do not claim native MIM.d coverage of the inserted contact. In particular, the below-width case also has the smaller measured contact enclosure and is not an isolated width-only physical control.

Two deliberate reference faults reached completed native LVS: the wrong width failed a physical property comparison and the swapped reference failed pin matching. Two physical faults completed unfiltered native KLayout extraction but the application rejected their changed ports before Netgen LVS: removing the contact lost the C1 top port, while a bridge merged C1 and C2. A separate replay verified those exact raw nodes and the application port guard; LVS was **not run** in either case. The original producer report remains `FAIL` because its initial assertion incorrectly expected both faults to reach LVS. It has not been rewritten as a passing producer run.

An independent reader examined the original ten public cases, two Magic cases and four faults, including written masks, labels, native findings, netlists and stages. Ten in-memory corruption controls were rejected. A second independent addendum checked the two fresh fault replays and source-bound DRC/extraction copies. The recorded outputs and their exact limitations remain the authority; these selected cases do not close other contact, spacing, array, operating, reliability or extracted-electrical requirements in the [device checklist](IHP_CMIM_REQUIREMENTS.md). The separate [ordinary catalog reference repair](IHP_CMIM_LVS_REFERENCE.md) retains its own scope.

## Retention and replay

The raw pilot, separate fault replay and independent review are retained in three hash-verified archives named in the [execution record](validation/ihp-cmim-minimum-boundaries-2026-11-02.json). The original source manifest, runtime receipts, external drivers and source-recovery references are retained with them. Reproduction requires the recorded source snapshot and native tool/runtime identities, the retained external drivers and fresh output directories. This was a manual source experiment using modified imported masks; there is currently no repository CLI for this minimum-boundary selection.
