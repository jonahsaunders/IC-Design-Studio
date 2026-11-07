# Chunk 7 public sources and reuse review

Reviewed November 6, 2026 against application baseline `b8372151`. The user
requested material that can be included with appropriate copyright permission.
The [source inventory](validation/chunk7-licensed-source-review-2026-11-06.json)
records pinned versions, file identities, license basis and applicability.
The [PDK review](validation/chunk7-public-source-review-2026-11-06.json) separately
records the inspected model directories and changes. This is a bounded search,
not proof that no other source exists.

## Reusable material found

| Source | Permission and provenance | What it can support |
| --- | --- | --- |
| [IHP L2n0 two-die reference](IHP_L2N0_REFERENCE.md) | Eight original IHP files under Apache-2.0, pinned at `943983786b04351feb20e33e8d3d76c0e0d87cce`; license and notices retained. | A newly retained two-turn coil measurement/layout reference. Independent source/import arithmetic passes; one-port discrepancies, uncertainty and substrate applicability remain explicit. No catalog binding or fresh solver result is implied. |
| [gds2openEMS measured L6n2 study](https://github.com/VolkerMuehlhaus/gds2openEMS/tree/74e612e819e77bc38c92e19c1143049528e0c147/more_examples/measured_vs_simulated/more_accurate_models_L6n2) | GPL version 3; original license and notices already retained in `tests/fixtures/ihp-measured-coil-v1`. | Geometry-specific measured calibration and solver comparison. All ten retained files have identical Git blob identities at the current upstream revision; this adds no new measurement coverage. |
| [Current SG13G2 electromagnetic stackups](https://github.com/VolkerMuehlhaus/gds2openEMS/tree/74e612e819e77bc38c92e19c1143049528e0c147/XML_stackup/latest/IHP) | Same GPL project; root license and `pyproject.toml` explicitly state the license. Both SG13G2 XML files are pinned in the inventory. | Future field-solver inputs. They are not compact device models or operating/reliability specifications. |
| [500 pH CPU/GPU inductor example](https://github.com/VolkerMuehlhaus/gds2openEMS/tree/74e612e819e77bc38c92e19c1143049528e0c147/more_examples/gpu_test/ind500p) | GPL project source; preserve the license and per-file notices when importing a selected subset. | A source layout and two-port solver comparison. A center tap in its geometry does not establish a measured three-terminal catalog model. |
| [IHP Open PDK](https://github.com/IHP-GmbH/IHP-Open-PDK/tree/5e6d592e4002946a4616f798c357f0f3c06cf3b6) | Apache-2.0 for the inspected IHP-authored files, with original notices. Third-party compact-model directories require their own license review. | Existing process, layout and simulation inputs. The inspected bondpad file remains an empty placeholder; no replacement coil model was established. |
| [SKY130 primitive sources](https://github.com/fossi-foundation/skywater-pdk-libs-sky130_fd_pr/tree/29b55153fd9f4badef05a02667184b81789d1f61) | Apache-2.0 source notices. | The available `_nhv` VPP model and its physical views can be studied, but no authoritative equivalence to the unavailable unsuffixed binding was established. |

The repository already includes a stronger [measured-coil implementation and
October 21 reproduction](IHP_MEASURED_COIL_REFERENCE.md). A fresh examination of
the current upstream data reproduces its numerical observations; it must not
be presented as a new calibration source or a newly completed solver run.
Duplicate data and a redundant reader were therefore not added.

The newer stackups require a deliberate integration review. In particular,
SUBGND moves from layer 210 to 250, its conductor representation changes to a
PEC sheet, and thickness conventions differ. Replacing the retained 200 µm
fixture would change the experiment. The CPU/GPU example compares simulated
responses; it supplies neither measurement uncertainty nor an arbitrary-geometry
or three-terminal accuracy bound. These sources are indexed for future use,
without changing application packages or historical evidence.

The additional [SemiMod/DMT measurement importer](https://gitlab.com/dmt-development/ihp_sg13g2_compact_models/-/blob/8608d27eef5a4832af22d9eb64c7f97fc096c6e3/create_dutlib/create_dut_lib.py)
has an explicit GPL-3.0-or-later notice, Copyright 2023 SemiMod. Its exact license,
README and source hashes are recorded in the inventory. It processes measurements
downloaded from IHP's existing `libs.doc/meas` tree; it is not a separate
measurement campaign. HBT data are assigned to T300K, and MOS temperatures come
from filenames. It adds no new full-temperature or reliability definition.
The helper is reusable with its notices, but its moving-branch download and
in-place data rearrangement need adaptation before integration with this
repository's immutable evidence workflow. It was inspected, not executed.
Third-party PSP Verilog-A code is outside this selected-file license review.

IHP's [measurement-data request #1284](https://github.com/IHP-GmbH/IHP-Open-PDK/issues/1284)
is still open with no comments or data attachments at this review. It requests
inductor/capacitor measurements, documentation and test structures; it does not
provide those inputs. The [latest documentation branch](https://github.com/IHP-GmbH/IHP-Open-PDK-docs/tree/9aff7327f8191a6fe3e590ed9a668a0ca2a35c25)
adds device and electromagnetic guidance, but its process-specification files
are unchanged from the already-reviewed main revision. The published voltage
conditions and interconnect-current estimates retain their stated applicability;
they do not define a complete device operating or reliability envelope. Its MOM
development notes explicitly distinguish development results from replacements
for delivered capacitor symbols. These findings are recorded as source leads,
without importing issue content or changing model bindings.

## Remaining definitions

The [complete SKY130 release inventory](SKY130_RELEASE_INVENTORY.md) and
[GF180/IHP interface inventory](UPSTREAM_SEMANTIC_INVENTORY.md) retain generated
declaration facts, fingerprints and exact source/notice identities. The
[independent content review](validation/chunk7-source-inventory-provenance-2026-11-07.json)
checks the final reports and 20 notice identities. No model bodies, source prose
or generator implementations are imported by these inventories. Mixed upstream
licenses remain separate; identifying a source does not grant blanket reuse
permission or establish a missing device model.

The [SKY130 VPP history review](validation/chunk7-vpp-history-review-2026-11-07.json)
checks three original 2020 snapshots and the current model/layout declarations.
The `_nhv` simulation model has four terminals; its layout CDL exposes three
and connects the model body to C1. None of those historical snapshots supplies
the missing unsuffixed model file. This leaves device identity and terminal
semantics unresolved; a four-pin model declaration alone does not establish
equivalence to the missing catalog entry. No model or alias is imported.

The separate [binding-semantic review](validation/chunk7-required-binding-semantics-2026-11-07.json)
also checks the original Xschem symbol and its 2023 interface change. The
unsuffixed name was already present upstream in 2020; the later edit does not
establish an alias to `_nhv`. The available model's declared body terminal is
unused internally, while its physical CDL and current symbol expose different
three-terminal interfaces. Current open-pdks rename filters supply no missing
model equivalence. These exact-source findings prevent a misleading substitution;
they provide no new electrical qualification.

The November 7 [GDSFactory source review](validation/chunk7-gdsfactory-source-review-2026-11-07.json)
also checks five exact files at revision `fc668efa7708bab1a539f019b272f8dd439b3b6d`
under its Apache-2.0 license. Its `ihp_inductor_rl` and SAX models are reusable
series R-L approximations, with values supplied by the caller. The `inductor3`
function still produces two-port behavior; it does not establish the catalog's
center-tap and substrate response. The bondpad remains an empty subcircuit.
Its documented RF material constants have no defined frequency-validity band or
temperature dependence. These examples do not resolve the missing bindings or
full envelopes, and no new model is imported into the application.

The four required unavailable bindings remain IHP `bondpad`, `inductor`,
`inductor3`, and the unsuffixed SKY130 VPP device. IHP's
[upstream discussion](https://github.com/IHP-GmbH/IHP-Open-PDK/issues/685#issuecomment-5778961368)
also distinguishes available symbols from released lumped models. Layout-only
pad/coil examples, an empty subcircuit, or a similarly named model cannot close
those requirements. The inspected sources also do not resolve all required
operating, reliability, statistical applicability or measurement-uncertainty
definitions. No undisclosed manufacturing data, unlicensed issue attachment or
all-rights-reserved presentation was incorporated.

For the next source import, keep its exact revision, raw file identities,
license and author notices; review the target device identity and terminal
semantics; then define the relevant limits before running qualification.
Existing gates and the matrix remain unchanged. Chunk 7 stays approximately
74% complete, low confidence (55–82%), an engineering estimate rather than
verified full acceptance.
