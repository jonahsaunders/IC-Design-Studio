# Reproducing the 0.22 qualification gates

## Dev20 external-project gate

The physical workflow runs [the pinned overvoltage regression](OPEN_PROJECTS.md)
with `--require-consistent`. Schematic import/roundtrip and layout geometry,
text and transforms must match. All 16 codes run in HSA with first-point DC
startup hints. Fresh extraction uses the checksummed upstream resistor correction
and full-circuit comparison; strict LVS must pass. Deliberate enable, child-pin
and resistor-length faults must fail. The generated native desktop testbench
also runs through the app's graphical-analysis engine. Logs and raw results are
retained on failure; CI no longer accepts `needs_attention` for this detector.

## Native hierarchy and scalar buses

The source fixture is [dual-divider.sch](../examples/native-hierarchy/dual-divider.sch),
with two instances of `stage`, each instantiating the shared parameterized `leaf`.
Each channel is a 1 kΩ shunt and 10 nF capacitor driven through a series resistor.
Baseline series resistances are 1 kΩ and 3 kΩ. The edited case changes the first
instance to 2 kΩ and the shared leaf expression from `{r}` to `{r*1.5}`; effective
resistances become 3 kΩ and 4.5 kΩ. The expected DC outputs are 0.25 V and 2/11 V.

```sh
python scripts/verify_native_hierarchy.py --require-xschem --output build/hierarchy-check
```

Install ngspice and Xschem, or supply `--ngspice` and `--xschem`. Without
`--require-xschem`, the gate still requires real ngspice and performs native
export/reimport, but does not claim independent Xschem execution. Both modes
compare OP, transient and complex AC values against an independently written
flattened deck and the analytic RC transfer functions, with a 0.2 µV absolute
error limit. Reports retain source hashes, engine details, input decks and raw
waveforms. Original source files are removed before native execution.

## Pinned physical qualification

Use Ubuntu 24.04 with ngspice and the Python requirements. The PDK requires
Magic 8.3.306 or newer; Ubuntu's Magic 8.3.105 package is too old. The workflow
builds Magic 8.3.600 and Netgen 1.5.300 from the exact upstream commits in
[the engine source lock](../examples/physical-engine-lock.json). Install the
development prerequisites listed in the physical workflow, then run:

```sh
python scripts/build_physical_engines.py --output build/physical-engines
python scripts/fetch_sky130_reference.py --physical-only --output build/qualification-pdk
python scripts/prepare_sky130_qualification.py --input build/qualification-pdk/sky130A --output build/physical-adapter/sky130A
python scripts/qualify_layout_process.py --pdk build/physical-adapter/sky130A --out build/physical-evidence --magic "$PWD/build/physical-engines/installed/bin/magic" --netgen "$PWD/build/physical-engines/installed/bin/netgen"
```

Use fresh output directories. Downloads reuse a cache but recheck every archive
hash before extraction. The two upstream archives total approximately 31 MB.
The prepared package must match [the committed qualification lock](../examples/sky130-qualification-lock.json),
including its exact manifest, model, symbol, layer and physical-deck files.
Reindexing a different PDK does not silently update this lock. Retain notices
and [the upstream archive inventory](../examples/sky130-reference-assets.json).

| Case | Required outcome |
|---|---|
| Nominal inverter | Schematic simulation, full DRC, extraction, unique connected LVS match, capacitance extraction and post-layout simulation pass |
| Narrow metal | Earlier stages pass; real DRC reports positive findings |
| Open route | DRC and extraction pass; Netgen reports an electrical mismatch |
| Changed channel length | DRC and extraction pass; Netgen reports the geometry/device mismatch |

A missing executable, changed file, storage error or failed tool startup never
counts as successful fault detection. The physical workflow retains reports,
tool versions, deck hashes, logs, layout files and waveforms on failure too.
The app's general PDK capability labels are not promoted by this one fixture.

## Release and repository gates

Every PR runs all required jobs, including documentation-only changes, so branch
checks cannot remain pending because a path filter omitted the workflow. Enable
the reviewed [main ruleset](../.github/main-ruleset.json) after the check names
have appeared in GitHub. It requires both desktop jobs, `exchange`, and `sky130`,
blocks branch deletion/force pushes and requires a PR with resolved review threads.
It does not require an additional approver for this single-maintainer repository.

An administrator can apply it with:

```sh
gh api repos/jonahsaunders/IC-Design-Studio/rulesets --method POST --input .github/main-ruleset.json
```

If a ruleset named **Verified main** already exists, update that ruleset's ID
with `PUT` instead of creating a duplicate. Repository settings are separate
from committing this configuration file; verify the active settings afterward.

After merging a verified release commit, manually run **Prepare draft preview
release** on `main`. It reruns all three gates, builds the exact downloadable
assets, verifies their shared commit and hashes, and creates a **draft
prerelease**. An existing tag/release causes creation to fail rather than replace
published assets. Review the draft and remaining machine acceptance before
publication; the workflow never publishes it automatically.

For clean-machine acceptance, retain the downloaded file hash, OS version and
display scale, then record install/extract → first waveform → real PDK simulation
→ save/reopen → cancellation/recovery → upgrade settings → uninstall. CI's
isolated application profile is useful evidence but not a complete clean OS.
Use [the focused issue drafts](RELEASE_FOLLOWUPS.md) to track these acceptance
items and the first hosted qualification separately.
