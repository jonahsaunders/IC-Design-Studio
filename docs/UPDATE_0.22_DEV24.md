# IC Design Studio 0.22.0.dev24 — packaged VGA qualification

This engineering preview brings together the recent analog workspace, digital
implementation flow and offline VGA Playground. Source implementation and
successful package qualification are separate states; consult the candidate's
exact-commit Actions runs and [release status](RELEASE_STATUS.md).

## Included workflows

- The [analog workspace](ANALOG_WORKSPACE.md) and [optimizer](ANALOG_OPTIMIZER.md)
  provide guided experiments, device characterization and sizing, constrained
  searches, sensitivity, staged verification and recoverable saved work.
- The [digital workspace](DIGITAL_WORKSPACE.md) connects project-owned RTL,
  simulation, synthesis, equivalence, timing and implementation. The included
  toolchain uses native Linux execution or a private Windows WSL 2 installation.
- The [VGA Playground](VGA_PLAYGROUND.md) renders eight Tiny Tapeout presets in
  a private embedded Qt WebEngine view. Sources remain in the native project;
  previewing after installation requires no Node.js, browser or internet access.
  Keyboard/Gamepad inputs and opt-in audio are included. A visual preview does
  not replace functional assertions, synthesis, timing or physical verification.

## Fixes and release qualification

The characterization dialog's plot selector no longer shadows Qt's inherited
`metric()` method. This fixes the identical Windows/Linux failure in guided
analog acceptance. Existing desktop checks also exercise the renamed selector.

`--vga-test OUTPUT` executes the same native renderer qualification from source
or a frozen application and writes `vga-test.json`, preset screenshots and a
round-trip project. It covers all eight rendered presets, pointer and keyboard
controls, opt-in Web Audio and pause behavior, invalid-source recovery, reload,
cell switching, save/reopen and server teardown. Actual speaker quality and
physical display behavior still require human observation.

The Windows installer and both extracted distribution archives run this probe.
External HTTP(S) access is pointed at an unavailable proxy while loopback remains
available. Frozen execution must use bundled assets and a clean source identity.
Release assembly rejects missing, stale, source-only or incomplete VGA evidence.

Draft preparation now requires desktop, external interoperability, physical,
digital implementation and VGA workflows on the selected commit. Digital and
VGA evidence archives accompany the desktop reports and checksums. Release notes
are selected from the application version. Draft creation never publishes a
release automatically.

## Local source validation

The [local validation record](validation/experimental-dev24.json) records 849 core
tests (31 environment skips), both analog GUI regressions, 94 simulator tests,
the eight-preset source probe and release-evidence rejection cases. Local VGA
execution uses offscreen software rendering and does not qualify packaged
Windows/Linux assets. Hosted checks must pass for their own exact commit.

## Acceptance still required

The previous closures of consumer-platform/signing issues did not include
completed checklists or attached observations. They are reopened for dev24:

- [Windows 10/11 installation, upgrades and accessibility — #8](https://github.com/jonahsaunders/IC-Design-Studio/issues/8)
- [Ubuntu desktop, display and accessibility — #9](https://github.com/jonahsaunders/IC-Design-Studio/issues/9)
- [Signing or explicit unsigned-preview policy — #10](https://github.com/jonahsaunders/IC-Design-Studio/issues/10)
- [Physical LAN/VPN collaboration — #31](https://github.com/jonahsaunders/IC-Design-Studio/issues/31)

Use [native acceptance](NATIVE_DESKTOP_ACCEPTANCE.md) on the exact candidate
packages. No physical consumer-device, mixed-monitor, audible-output, LAN/VPN,
signing or macOS result is inferred from hosted tests. No public release is
authorized by an automated draft.

The remaining process roadmap includes HVI source-to-GDS conversion warnings,
broader detector PVT/transient/extracted simulation, measured recovery and
responsiveness improvements, and general offline design editing.
