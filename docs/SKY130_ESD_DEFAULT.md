# Corrected ESD binding in the bundled SKY130 candidate

The experimental source candidate now offers
`sky130_fd_pr/nfet_g5v0d10v5_nvt_esd.sym` through the normal Project Hub and
device library. Package revision `5dda725c94efe3c2` binds the exact public
`sky130_fd_pr__esd_nfet_05v0_nvt` model, using the upstream symbol correction
described in the [source contract](SKY130_ESD_NVT_BINDING.md). Both upstream
license texts, model bytes and source hashes remain included.

This is a partial simulation binding awaiting fresh default-path installed
acceptance on Windows and Linux. It does not establish ESD robustness, a
protection rating, physical layout support, reliability or complete device
qualification. The finite supported geometry is W=10 µm, nf=1 and
L=0.9, 2 or 4 µm; those bin centers are not continuous process limits.

## Saved projects and package identities

Existing projects keep their exact revision and model references. The retained
predecessor manifest is `b26f7f28e659ddc1`, SHA-256
`840f7af802b07346650c50a5967e532a4cb1716623cf0c9d6fd6c58eaf35fcbe`.
Historical tests reconstruct its exact asset set, checking every original byte.
The optional package `ac43172dd991a7a5` remains a separately tested identity.
Neither a saved project nor an old acceptance record silently moves to the
new default candidate. The general package rebuilder recognizes both exact
current and predecessor inputs, rebuilds the complete new default, and rejects
changed assets before reconstructing historical packages. The
[compatibility repair](validation/chunk7-default-reconstruction-repair-2026-10-29.json)
passes on both hosts, including the original bipolar, fixed-geometry, varactor,
resistor and four-terminal capacitor recipes.

The new candidate manifest SHA-256 is
`125cde7c313ee18a05a7ec5c280d514b99aea521d6b39476e44f486ae494153b`.
Its source inventory contains 288 partial devices, five unavailable bindings
and nine utilities. The previously accepted source baseline retains its
287 partial / six unavailable / nine utility inventory. Inventory availability
is separate from acceptance of the changed default and from family completion.

## Required default-path acceptance

The producer selects the actual bundled package in the Project Hub, creates
a project, places six ESD devices through the library and inspector, saves and
reopens them, and runs all nineteen electrical conditions. The original saved
two-capacitor project must retain its predecessor lock and exports.

An independent reader binds the actual shipped manifest and collection to the
captured empty Hub project, selected registry and all staged model files. It
executes nineteen literal references and checks all 98 native executions,
four-terminal currents, application vectors and 360 faulty device instances.
An optional-package result cannot satisfy the default-selection contract.

Both desktop release paths retain the optional gate and require the separate
default gate:

```text
python scripts/qualify_installed_sky130_esd.py --executable PATH_TO_DESKTOP --expected-commit FULL_COMMIT_SHA --bundled-default --out NEW_EVIDENCE_DIRECTORY
```

Source execution remains explicitly marked as development evidence. The
[progress tracker](QUALIFICATION_PROGRESS.md) records the latest independently
reviewed results and outstanding installed gates.
