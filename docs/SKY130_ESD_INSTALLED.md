# Optional SKY130 ESD desktop workflow

The corrected `nfet_g5v0d10v5_nvt_esd.sym` binding now has a desktop acceptance
probe and an independent electrical reader. The [retained source experiment](validation/sky130-esd-gui-electrical-2026-10-28.json)
passes on Windows and native Linux. Fresh acceptance of a packaged candidate
remains required; source execution does not establish installed acceptance.

The optional package is revision `ac43172dd991a7a5`, manifest SHA-256
`5315d2d6ad7618047eeeb48a15f81f221e6f42864647208acfb65124ee5c9c7a`.
It remains separate from the bundled default `b26f7f28e659ddc1`.
Its public-source derivation and finite model bins are described in
[the binding contract](SKY130_ESD_NVT_BINDING.md). No default promotion or
ESD protection rating follows from this workflow.

## What the probe exercises

The application installs both package revisions through its real PDK manager.
It saves an edited two-MiM project before importing the optional revision,
then reopens that project and verifies its original design, exports and lock.
It places six corrected ESD devices through the device library and inspector,
using W=10 µm, nf=1, L=0.9/2/4 µm and multiplicity 1/3. Those exact saved and
reopened device records are retained in every electrical specimen.

The test harness adds explicit voltage sources without rebuilding the selected
devices. Fifteen DC conditions cover five model corners at 0/27/85 °C; four
nominal AC conditions excite each terminal separately. Each DC condition also
executes wrong-multiplicity, gate, body and length controls. The application
therefore performs 79 native executions. A separate process constructs and
executes 19 literal references through the same reviewed engine.

The independent reader verifies every source/deck, original project revision,
four-terminal current, stimulus, conservation equation and saved application
result. It rejects changes to the GUI graph, result vectors, original-path
mapping, captured inventory and execution conditions. All 360 faulty device
instances must be detected. The source runs pass all 19 conditions and 98
executions on each host with a maximum normalized application/reference error
of zero.

## Provenance and installed execution

The launcher binds a complete application source inventory to an immutable Git
candidate before launch. It selects the shipped executable, engine, initializer
and runtime support files, records the actual ELF dependency closure on Linux,
and runs native analyses with an explicit environment. The producer records
actual execution commands, timestamps, raw files and before/after identities.
Its complete output is sealed before the independent references are created in
a separate directory. The expected inputs, both inventories and launch outcome
are retained alongside the result.

Windows acceptance invokes this workflow on the executable installed by the
ordinary installation test. Linux acceptance invokes the exact frozen desktop.
The existing MiM, physical, runtime, archive and installer gates still apply.
Linux packaging now writes its own manifest after freezing, binding the reviewed
ELF executable, initializer and every adjacent support file. It no longer treats
the tracked Windows manifest as a Linux payload inventory. The ordinary Linux
staging check and corruption tests pass; fresh packaged acceptance remains open.

```text
python scripts/qualify_installed_sky130_esd.py --executable PATH_TO_DESKTOP --expected-commit FULL_COMMIT_SHA --out NEW_EVIDENCE_DIRECTORY
```

The application entry point is `--esd-acceptance`. Source runs require an
explicit `--development` flag and remain marked as development evidence.
Packaged runs reject that flag and external simulator overrides.

This finite workflow does not qualify ESD robustness, physical layout,
continuous operating or geometry ranges, reliability, the complete ESD family,
or chunk 7. The original source-only corrected-binding record remains unchanged.
