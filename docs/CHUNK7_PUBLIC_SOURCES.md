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

## Remaining definitions

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
