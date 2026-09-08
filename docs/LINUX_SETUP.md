# Linux launch and setup checks

The packaged app targets Linux x86_64 with glibc 2.39 or newer (Ubuntu 24.04
baseline). Extract the entire app archive into a writable location. Keep
`_internal` next to `ICDesignStudio` and run `./ICDesignStudio`.

Python, PySide6 and KLayout are included. A graphical X11 or Wayland session and
the platform's graphics/font libraries are required. The bundle includes the
desktop loader libraries staged by the build; it does not replace system glibc.
If launch fails, run the executable in a terminal and inspect the loader error.
`ldd ./ICDesignStudio` and `ldd ./_internal/PySide6/Qt/plugins/platforms/libqxcb.so`
identify missing dynamic libraries. The exact Qt plugin path can be found under
`_internal` if a platform build packages it differently.

To exercise the app using a new test profile without changing your normal
projects, run:

```sh
./ICDesignStudio --release-test /absolute/path/to/new-launch-check
```

For a host without a display, add `QT_QPA_PLATFORM=offscreen` before the command.
The check opens native widgets, saves/reopens a project, runs a worker, tests
editing and writes `release-test.json` plus a desktop image. A headless pass does
not establish graphics-driver or desktop-session behavior.

Install/link a supplied PDK package using **Tools → PDK manager**. Model files
remain outside the app and must match the project's recorded lock. For physical
verification, configure actual Magic, Netgen and ngspice executables in
**Tools → Engine diagnostics & paths**. The release evidence records the exact
tested tool versions. Do not point the app at temporary wrappers from the
restricted build host; those paths are not product configuration.

After configuring the engines, create a SKY130 mirror or GF180 inverter, generate
its layout, select its saved bench and run **Verify layout**. Passing this flow
checks the installed tool/model combination with the exact saved design.

Automated packaged probes can use `ICSTUDIO_PROBE_PDK_ROOT`,
`ICSTUDIO_PROBE_MAGIC`, `ICSTUDIO_PROBE_NETGEN` and `ICSTUDIO_PROBE_NGSPICE` to
exercise both processes through the real physical comparison worker. These
variables are optional testing inputs; ordinary use configures paths in the UI.

The 0.11 handoff separates actual fresh-profile/environment launch checks from
fresh-OS installation qualification. A separate Ubuntu machine/VM and an actual
desktop session remain the final environment gate; this build host could not
start an isolated OS. Windows build definitions are retained but unexecuted.
