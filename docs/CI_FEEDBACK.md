# Source feedback and selected acceptance candidates

Pull requests and merge-queue groups run **Fast source feedback** on Windows and
Linux. The default checkout tests GitHub's synthetic merge commit, preserving
compatibility with the proposed base. The lane compiles application, script and
test Python sources before installing dependencies, then runs focused editing,
PDK, runtime, physical-interface and release-contract tests plus the menu,
project-hub and five-model SKY130 resistor editor and multiplicity GUI smoke
checks, plus the complete finite 60-case IHP resistor editor lifecycle. The IHP
source check includes registry installation, both terminal-access choices,
rotations, save/reopen, regeneration and legacy recovery. Its complete evidence
inventory is checked again after the child exits; the template and legacy
assets are included in the source identity. This is source GUI evidence; the
separate installed gate requires fresh managed native jobs.
The lane has no path filter, so documentation-only
PRs also report its stable aggregate check, **PR feedback**.

After the first hosted run passed on October 23, `main` was configured to require
**PR feedback** from GitHub Actions, with an up-to-date base and the default
administrator bypass. The [configuration receipt](validation/chunk7-integration-feedback-2026-10-23.json)
records the exact policy readback. A workflow file alone cannot configure that
requirement. Source feedback is not packaged desktop acceptance, native physical
qualification or foundry signoff.

Expensive desktop and qualification workflows run for version tags, selected
manual candidates, or as reusable gates of release preparation. They no longer
start independent copies on both branch pushes and pull requests. The included
digital-runtime workflow remains reusable or manually selectable. Each manual
workflow requires `candidate_sha`: the full lowercase 40-character commit of
the selected branch or tag. The early candidate check compares that input with
the immutable event commit and the actual checkout. If the branch advanced,
dispatch again with the intended matching ref and SHA; stale evidence is never
silently relabelled as the new candidate.

For example, obtain the exact current commit and launch a reviewed integration
candidate (GitHub CLI commands shown for an existing authenticated checkout):

```text
git rev-parse HEAD
gh workflow run build-desktop.yml --ref experimental -f candidate_sha=FULL_COMMIT_SHA
gh workflow run reference-compatibility.yml --ref experimental -f candidate_sha=FULL_COMMIT_SHA
gh workflow run ihp-inductor-qualification.yml --ref experimental -f candidate_sha=FULL_COMMIT_SHA
```

**Prepare desktop release** is explicitly dispatched with the same candidate
input and its existing `publish_release` choice. It still runs every existing
desktop, interoperability, physical, digital, VGA, statistical and reference
gate, then verifies current-commit evidence before draft/public publishing. Its
manual publication policy is unchanged. IHP coil qualification remains a
separate candidate suite; this change does not invent a new release gate or
claim that suite is covered by release preparation. Successful development
feedback cannot replace fresh release acceptance.

Each feedback artifact retains the checked-out commit, Python/workflow/dependency
source hashes, stage return codes,
elapsed time, first-failure time when applicable, logs and GUI results. Stage
timings exclude dependency installation and queue time. Use GitHub run/job
creation and start timestamps for those additional measurements. Compare time
to first useful failure and time to close a device family's remaining gates;
smaller test counts alone do not establish faster qualification or completion.

To reproduce the source lane locally, install `requirements.txt` and run
`python scripts/ci_feedback.py`. Native external engines are deliberately outside
this lane; the selected acceptance workflows retain their existing commands,
fault controls, raw evidence and release gates.

For local Windows runs, use a short, writable temporary directory and the
ordinary user account. The junction-protection fixtures require the ability to
create junctions; a restricted sandbox can block them even when file creation
works. Check temporary write/cleanup and those fixture prerequisites before
launching the full lane. Do not skip the protection tests or request Windows
administrator privileges. Preserve environment failures separately from the
subsequent unchanged-source acceptance.

The [October 23 local integration check](validation/ci-feedback-integration-2026-10-23.json)
passes 211 focused tests on each host (14 Windows skips, two Linux skips),
release-document validation and both GUI probes. Final elapsed times are
67.3 seconds on Windows and 33.9 seconds on Linux, excluding environment setup.
These are local observations, not hosted CI timings. An earlier Linux run used
the Windows-mounted checkout: its test stage took 262 seconds, compared with
6.2 seconds from a verified Linux-local source copy. Use native Linux storage
for WSL test checkouts; retain source identities when copying, and remove
redundant copies after verified evidence retention. The earlier overall run
remains invalid because the LI auditor changed while it was running.

The first hosted run on integration candidate `43a04bb` passes on GitHub's actual
PR merge commit. Linux completes in 1:35 and Windows in 2:29 including setup;
the aggregate passes at 4:07 after a 91-second queue wait. The feedback commands
themselves take 54.0 and 80.9 seconds respectively. Both hosts discover 211 tests
(two Linux skips, 13 Windows skips); all required stages pass, and downloaded
artifacts match all 1,328 checkpoint source hashes. These timings are one observation,
not a measured long-term speedup or full acceptance. Merge-queue execution and
the new native shared-toolchain producer/consumers remain separate verification.

The [subsequent focused integration](validation/chunk7-focused-integration-2026-10-23.json)
adds the selected LI reuse and MiM passive-corner/auditor checks. All 260 tests
pass on both hosts (15 Windows skips, two Linux skips), alongside release
document validation and both GUI probes. The observed local totals are 72.9
seconds on Windows and 36.6 seconds on native Linux storage; environment setup
and hosted queue time are excluded. Every checked source identity is retained.

Candidate `d38615c` subsequently passes [hosted PR feedback](validation/chunk7-focused-integration-2026-10-23.json)
in 2:24 overall on its actual merge commit. Both hosts discover 260 tests (two
Linux skips, 14 Windows skips) and pass all required stages. Source feedback
takes 53.4 seconds on Linux and 86.8 seconds on Windows; queue waits are two
and three seconds, with 37 and 44 seconds of setup before feedback. Downloaded
artifacts match all 1,336 current source bindings. This is a second measured
run, not a long-term latency guarantee or exhaustive acceptance.

The [signed-bias integration](validation/chunk7-bias-integration-2026-10-23.json)
adds the new MiM producer/auditor tests and shared-toolchain mismatch diagnostics.
It passes 293 tests per host (15 Windows skips, two Linux skips), release-document
checks and both GUI probes in 81.7 seconds on Windows and 39.0 seconds on native
Linux storage. All 1,340 source bindings match the frozen snapshot. These are
local timings; hosted queue/setup and installed acceptance remain separate.

The [October 26 capability repair](validation/chunk7-desktop-capability-repair-2026-10-26.json)
adds the exact native-layout capability test to this lane. It caught an outdated
expected list in the prior full desktop discovery; the corrected test preserves
all forged-metadata, layer and source-lock rejection checks. Only that method
is selected, with an explicit selector regression. The repaired source lane
passes 506 tests per host and all five stages; installed acceptance remains
separate.

The new repeated-cell and parallel-resistor work adds their focused producer
and independent-checker tests. A sixth stage exercises actual source Qt
multiplicity edits, attached routes, review/apply, undo/redo and save/reopen for
all five models. Native physical/electrical batches and installed delivery
remain separate acceptance gates. The historical 506-test, five-stage result
above retains its exact candidate and scope.

The [final October 26 array integration](validation/sky130-metal-parallel-source-feedback-2026-10-26.json)
passes all six stages on both hosts: 550 tests each, four Linux skips and sixteen
Windows skips. Source feedback takes 74.9 seconds on native Linux and 161.7
seconds on Windows, excluding environment preparation. All 1,386 source hashes
agree. Separate complete Linux discovery passes 3,725 tests with 61
environment-dependent skips; no installed acceptance is inferred.


The [October 26 desktop job split](validation/desktop-job-split-local-2026-10-26.json)
addresses a Windows job that reached the hosted six-hour limit during release
archive assembly. Packaging and its original 108 steps now hand the exact build
to a fresh installed-acceptance job, which preserves all 15 original remaining
steps, their native/GUI/electrical checks and timeouts. Release preparation still
requires the complete desktop workflow. Producer diagnostics and an installed
checkpoint are uploaded under separate names before the expensive later work.

The handoff validates the candidate, workflow run and attempt, host, workspace,
archive and every member before restoring into fresh destinations. It preserves
the producer's source ZIP, verifies its candidate Git sources and rejects stale
runtime readiness or prior installed acceptance. Source archive reuse does not
replace the extracted-distribution and installed-app checks. A consumer on a
later workflow attempt cannot reuse a handoff from the earlier attempt.

Local checks pass 45 tests on each host, including execution with site packages
disabled; four Windows skips cover POSIX-only link and permission controls.
Ten workflow controls and actionlint also pass. The portable release-tools lane
includes both handoff test modules without installing GUI or native dependencies.
These are synthetic archive/Git fixtures. The split still needs a successful
hosted candidate to establish actual transfer time, fresh host compatibility and
complete installed/release acceptance. The original timeout and incomplete
Windows diagnostic upload remain recorded; neither is promoted to a release pass.

The package-reconstruction checks run in a separate required
`package-contracts` stage. The eleven selected checks include the prior package
checks and the current pw2dn predecessor and reconstruction checks. A separate
required `runtime-release-contracts` stage adds the pinned Linux runtime and
release-receipt tests; the eight preceding stages remain required. Each of the
nine stages retains the 300-second deadline and failure propagation. The source
identity also covers the selected SKY130 package assets, versioned contracts and
the retained Linux runtime archive. These checks do not replace installed
acceptance or the release gates.
