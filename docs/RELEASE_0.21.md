# IC Design Studio 0.21.0

**Release theme: a clear first step into open circuit design.** Engineering preview; prepared for a GitHub prerelease.

## New in this version

- **Start here / example gallery:** six searchable, guided projects with expected outcomes, engine prerequisites and an Open a copy action. Independent project identities keep their run histories separate. The gallery appears after recovery handling on normal startup and can be disabled or reopened from File.
- **Open PDK setup:** bounded discovery under `PDK_ROOT`, Ciel and common installation directories; support for selecting a variant, a parent folder or an extracted package collection; background checks and batch registration; per-package errors; and a direct New project with this PDK action.
- **Clearer readiness:** placeable/indexed symbol counts, common corners, IHP OSDI requirements and physical capability summaries. Registration and simulation qualification remain separate states.
- **Portable PDK assets:** managed installations keep upstream notices and IHP compilation sources. Installed packages use their local copied assets even if exported from a folder registration elsewhere.
- **GitHub materials:** redesigned README with actual desktop captures, first-run and PDK guides, example walkthroughs, a prioritized roadmap, contribution guidance, issue/PR templates, tag-triggered build artifacts and a release-material checker.

## Fixes

- Native circuits without a separate label list now derive initial waveform probes from their device nets instead of failing to open.
- Layer All / None / Solo controls dispatch correctly alongside the command that opens the Layers panel.
- PDK installation rechecks copied assets to detect a source change during installation.
- Startup completes recovery review before opening the gallery; explicitly opening a project bypasses the automatic welcome/recovery sequence.
- Linux CI explicitly stages ngspice into its package. CI retains native-analysis and new-user acceptance evidence.

## Included examples

RC low-pass, native divider, inverter with teaching layout, native RC comparison, reusable hierarchical divider and common-centroid resistors. Five have short saved simulations; the placement example is explored without a simulator. The supplied long user circuit is not part of this release's smoke tests.

## Optional PDK adapter collection

Pinned SKY130A, GF180MCUC and IHP SG13G2 subsets are reindexed with the current adapters. The collection contains 71/74, 20/22 and 35/45 placeable/indexed symbols respectively, along with locks, notices and available provenance. IHP Verilog-A sources are included; compatible OSDI compilation and runtime execution are still required. These packages are not complete foundry PDKs.

## Validation

The release's accompanying `IC-Design-Studio-0.21.0-Validation.json` records executed checks and exact package limitations. It is the authoritative summary for the prepared artifacts. Native Qt screenshots are captured on the Linux test host; they are not Windows execution evidence.

The new-user acceptance exercises all six gallery entries, runs the five saved simulations through actual workers, checks the native divider's 0.5 V result, preserves example files, registers checksummed packages and creates a linked project. Core tests cover independent example identities, bounded multi-variant discovery, malformed packages, common corners, OSDI requirements and portable installation. The broader native-workflow gate runs graphical OP, transient, DC, AC and noise plus sensitivity, bounded search and reviewed exchange through ngspice.

The Windows portable build is assembled from pinned Windows runtimes and checked for manifest hashes and PE dependencies. It has **not been executed on Windows in this workspace**. The repository includes Windows execution gates for maintainers to run before promotion. KLayout CLI, full process DRC/LVS, target-platform IHP OSDI and manufacturing qualification are not established by the new gallery/package tests. macOS remains unqualified.

## Upgrade and first run

Extract the new Windows portable package into a new folder and launch `ICDesignStudio.exe`. Use the startup gallery to run a small example before opening a larger design. The matching source and clean GitHub repository archives are available separately; see [Downloads](DOWNLOADS.md).

Existing projects keep their explicit PDK revision links. Registering a new companion package does not silently upgrade old projects. Use the revision-migration controls when changing an existing design's process data. Keep backups before intentionally migrating project formats or PDK revisions.

## Next priorities

Fresh-machine release qualification, stronger native editing and hierarchy, reproducible PDK device/corner evidence, deeper physical verification and extraction, and richer simulation studies. See the [roadmap](ROADMAP.md) for scope and acceptance criteria. Advanced periodic/RF analyses, automatic PDK downloads and unrestricted process support remain future work.
