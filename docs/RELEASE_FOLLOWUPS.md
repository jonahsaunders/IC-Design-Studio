# Release acceptance tracking

The current candidate is **0.22.0.dev25**. Automated qualification and manual
acceptance have separate completion criteria. Attach the exact source commit,
package SHA-256 and observations; a closed issue without evidence does not
qualify a platform or distribution policy.

| Gate | Tracking | Required evidence |
|---|---|---|
| Clean Windows 10/11 | [#8](https://github.com/jonahsaunders/IC-Design-Studio/issues/8) | Install without Python/EDA tools, first simulation, real PDK example, save/reopen, cancellation/recovery, paths with spaces, portable archive, upgrades, 100/150/200% and mixed-monitor scaling, keyboard/screen-reader review, uninstall preserving projects. |
| Native Ubuntu 24.04 | [#9](https://github.com/jonahsaunders/IC-Design-Studio/issues/9) | Clean archive launch, simulation and PDK workflow, settings migration, display/scaling, keyboard/accessibility and required OS runtime libraries. |
| Windows signing policy | [#10](https://github.com/jonahsaunders/IC-Design-Studio/issues/10) | Maintainer chooses signing infrastructure or explicitly accepts an unsigned engineering preview; record the decision and actual consumer installation behavior. If signed, verify signatures before final checksums. |
| Physical LAN/VPN | [#31](https://github.com/jonahsaunders/IC-Design-Studio/issues/31) | Separate physical clients, TLS trust and rejection, invitations/revocation, concurrent edits, interruption/reconnect/restart and exactly-once recovery across intended firewalls/VPNs. |

Issues #8–#10 were reopened because their earlier closures contained unchecked
acceptance lists and no completion records. Historical dev12 issue #11 and old
release evidence remain historical; they do not qualify current packages.
Some issue titles still name dev24. Keep those checks open until a record names
the candidate actually tested; do not reuse the old draft's package identity for
dev25.

Both consumer-platform checks include VGA without external network access:
all eight presets, actual sound, keyboard/Gamepad controls, hide/resume, invalid
RTL, reload, save/reopen and project switching. Use the
[native acceptance tool](NATIVE_DESKTOP_ACCEPTANCE.md) and attach its JSON,
screenshots and sanitized logs. Leave `Not run`, failed or blocked items open.

## Automated candidate gates

1. Run desktop/package, external interoperability, pinned physical, digital, VGA
   and statistical campaign workflows on the selected source commit. Inspect failures and retained
   evidence before promoting the candidate.
2. Windows installation and Windows/Linux archive execution must include passing
   frozen VGA reports with all eight presets and the same clean commit/version.
   The Windows record must also match the setup executable's name and SHA-256
   and retain all three installed DPI probe reports. Each platform requires the
   expected application, corresponding source and evidence assets.
   The statistical evidence must identify the same commit/run and complete the
   1,152-case numerical workload with crash recovery and resolved trial results.
3. Prepare a draft with matching source, applications, qualification evidence and
   checksums. Version changes on `experimental` or `main` trigger draft preparation;
   manual dispatch remains available.
4. Review the four manual gates above before public publication. A passing draft
   workflow never publishes automatically or marks manual acceptance complete.

No signing credential, signing service or unsigned-publication policy is selected
by this source change. General offline editing, managed internet hosting, macOS
qualification and broader process signoff remain separate roadmap work.
