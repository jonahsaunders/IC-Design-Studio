# Native Windows and Ubuntu acceptance

Use the exact dev25 installer/portable archive whose source commit passed the
desktop, interoperability, physical, digital, VGA and statistical workflows. The
[dev25 handoff](DEV25_ACCEPTANCE_HANDOFF.md) identifies the existing draft and
package digests; later experimental changes require newly qualified packages. Launch without a preinstalled
Python or EDA toolchain. Keep the complete application directory together.

Run `ICDesignStudio.exe --desktop-acceptance acceptance-dev25` on Windows, or
`./ICDesignStudio --desktop-acceptance acceptance-dev25` on Ubuntu. Use a fresh
output directory for each OS/build/display configuration. Select the downloaded
installer or archive in the acceptance window so its SHA-256 is retained.

The automated part exercises the actual Qt platform. Then use the open app to
observe the following tasks. Record OS edition/build, display setup and failures
in the notes. Screenshots and a saved project make failures reproducible.

| Observation | Required behavior |
|---|---|
| Fresh install and paths with spaces | Launch and run the bundled example without preinstalled Python/EDA tools. |
| First design workflow | Find components, place a circuit, get a waveform, save, close and reopen. |
| 100%, 150%, 200% scaling | Controls, labels, focus indicators and symbol previews remain usable. Restart between OS scale configurations where required. |
| Mixed display scaling | Move the main and floating windows between differently scaled monitors; resize all edges and four corners. |
| Monitor removal and restoration | Save an arrangement on the second monitor, disconnect it, restart, and reach each title bar and resize handle. Reconnect and repeat. |
| Offline VGA Playground | With external network access unavailable, render all eight presets; check real audio output, keyboard/Gamepad controls, pause/resume, reload and save/reopen. |
| Interrupted work | Cancel a long simulation, run another, restart after interruption, and inspect the last durable design and unsent review draft. |
| Upgrade and accessibility | Upgrade from the prior candidate, preserve projects/settings, and use keyboard navigation and a screen reader on principal controls. |

Click **Save acceptance evidence**. The JSON distinguishes the automatic result
from each operator observation. Overall success requires an identified package,
a frozen build with an exact clean source commit, passing automatic checks and
all observations marked passed. `Not run`, `Blocked`, source-only execution and
missing package identity cannot become a passing package acceptance result.

Select **Consumer Windows** or **Consumer Ubuntu** and record the machine,
OS edition/build, monitors and scale factors. The current form assigns stable
identities to every required observation. Hosted runners, omitted or duplicate
observations, unknown commits and source checkouts cannot satisfy this gate.
After both physical-machine sessions, check the observations against the release
commit and independently hash the actual packages:

```sh
python scripts/check_consumer_acceptance.py --commit FULL_SOURCE_COMMIT \
  --windows windows/desktop-acceptance.json --windows-package ICDesignStudio-Setup.exe \
  --ubuntu ubuntu/desktop-acceptance.json --ubuntu-package ICDesignStudio-linux.tar.gz
```

Exit code zero requires both platforms to pass for these exact bytes. This
check does not create missing human observations or change the separate signing
and physical-network acceptance requirements.

This workspace cannot supply physical Windows/Ubuntu or mixed-monitor evidence.
The corresponding [Windows](https://github.com/jonahsaunders/IC-Design-Studio/issues/8)
and [Ubuntu](https://github.com/jonahsaunders/IC-Design-Studio/issues/9) acceptance
issues remain open until actual records are attached. A hosted Windows Server
probe and Linux offscreen/Xvfb execution remain distinct evidence.
