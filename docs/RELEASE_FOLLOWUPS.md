# Release follow-up issue drafts

These are ready-to-post issue bodies, not assertions that issues or external
acceptance checks have been completed. Attach evidence for the exact release
commit and asset hashes. Keep a failed or blocked check open.

## Qualify dev11 on clean Windows 10 and Windows 11 machines

The hosted Windows Server job does not establish consumer Windows compatibility.

- [ ] Record OS edition/build, release commit, installer/portable SHA-256 and
  display scale for each machine.
- [ ] Install without a preinstalled Python or EDA toolchain; obtain the first
  waveform using the included engine, then run a real supported PDK example.
- [ ] Save, close and reopen the project; cancel a simulation and verify that
  subsequent simulation and recovery work.
- [ ] Check 100%, 150% and 200% display scale, keyboard navigation, focus and
  a screen-reader pass through the principal controls.
- [ ] Verify shortcuts, file association, paths with spaces and the portable ZIP.
- [ ] Upgrade from the prior candidate; preserve projects and user settings.
- [ ] Uninstall and check that user projects are retained.
- [ ] Attach observations, screenshots and logs; link separate defects for any
  failed acceptance item before publishing the prerelease.

## Qualify the Linux archive on a clean Ubuntu 24.04 desktop

CI runs the extracted archive with an isolated application profile and offscreen
Qt. An interactive desktop must still be checked.

- [ ] Record OS/display environment, release commit and archive SHA-256.
- [ ] Extract the complete archive to a path with spaces on a machine without
  a preinstalled Python or EDA toolchain; launch the packaged executable.
- [ ] Obtain a waveform, run a supported real-PDK example, save/reopen and test
  cancellation/recovery.
- [ ] Review native display scaling, keyboard navigation and accessibility.
- [ ] Exercise settings migration from the prior candidate.
- [ ] Attach logs and screenshots, documenting any external runtime libraries
  required by the tested OS image.

## Decide and document Windows signing for public distribution

The candidate's Windows executables are unsigned. Signing requires a maintainer's
chosen certificate or signing service and repository secret configuration.

- [ ] Record the selected signing approach and release policy.
- [ ] If signing is adopted, sign before package execution and checksum creation;
  verify the signature on the exact downloadable installer and executable.
- [ ] If releasing an unsigned engineering preview, explicitly record that
  decision and keep the download instructions accurate.
- [ ] Retain consumer-machine installation observations for the chosen approach.

## Record the first complete dev11 qualification and draft release

The workflows and ruleset are implementation/configuration; repository settings
and successful hosted runs require separate evidence.

- [ ] Push the implementation branch and open its PR; retain the two desktop,
  `exchange` and `sky130` results for the same commit.
- [ ] Inspect the independent Xschem hierarchy results and the physical nominal,
  narrow-metal, open-route and changed-channel-length reports. A tool startup
  error must never be accepted as an expected design failure.
- [ ] Apply or update the **Verified main** ruleset once check names exist;
  inspect the active settings and merge through the required checks.
- [ ] Dispatch **Prepare draft preview release** on the merged `main` commit.
- [ ] Inspect the draft's version, commit, source archives, executable packages,
  validation records, evidence and SHA256SUMS.
- [ ] Link the consumer-platform/signing decisions above. Publish only after
  the remaining acceptance items have been reviewed.

See [the qualification guide](QUALIFICATION_0.22.md) for commands and scope,
and [release status](RELEASE_STATUS.md) for the historical hosted baseline.
