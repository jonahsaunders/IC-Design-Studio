# VGA Playground in the digital flow

Open **Digital flow → More → VGA Playground**. The native RTL editor stays on
the left and the interactive VGA display appears on the right. You can also
select **VGA Playground** in the digital result-view selector.

Choose **Stripes, Music, Rings, Logo, Conway, Checkers, Drop, or Gamepad**, then
click **Create RTL cell**. Studio creates a new cell in the current project with
the original Verilog, data and license notices, plus a two-frame smoke-test
testbench. Existing cells remain available in the cell selector. Creating a
preset is undoable; ordinary project saves include all its sources.

Edit the native working copy to recompile the preview after a short pause.
**Apply sources**, saving, undo, simulation, synthesis and flow export retain
their normal behavior. The preview uses working-copy RTL; it is independent of
the selected historical run. Syntax errors appear over the display and never
leave an older simulation running under new source. Use **Reload preview** if
the web renderer stops; source text remains owned by Studio.

The display supports `ui_in` bits 0–7, reset, audio and the upstream keyboard /
on-screen Gamepad PMOD controls. Click the preview before using its keyboard
shortcuts. Audio starts only when enabled. Leaving the result view or digital
workspace pauses rendering and audio. Return to resume the simulation.

## Supported interface

Use the Tiny Tapeout ports `clk`, `rst_n`, `ena`, `ui_in[7:0]`, `uo_out[7:0]`,
`uio_in[7:0]`, `uio_out[7:0]`, and `uio_oe[7:0]`. The clock is 25.175 MHz.
The TinyVGA output mapping is
`{hsync, B[0], G[0], R[0], vsync, B[1], G[1], R[1]}`; audio uses bit 7 of
`uio_out` when its output enable is asserted. Active-high and active-low sync
are detected by the upstream simulator.

Studio passes the selected top module, nested RTL/include paths, include
directories, preprocessor definitions and embedded memory data to the preview.
Testbenches and SDC files are excluded. The simulator uses the upstream
Verilator-to-WebAssembly pipeline and its supported RTL subset. A visual
preview is not a synthesis, timing, formal or physical signoff result. Run those
stages through the existing digital flow. The generated testbench captures two
frames; it is a smoke test, not an assertion of a design's functional correctness.

## Source setup and desktop packaging

Install the Python requirements, including matching PySide6 Essentials and
Addons 6.8.3. Install git and Node.js 22.12+ (or 24), then run:

```sh
python scripts/build_vga_playground.py
```

This downloads the upstream commit pinned in `icstudio/digital_vga.py`, installs
its locked npm dependencies, checks TypeScript, and builds under
`build/vga-playground/dist`. `--source /path/to/vga-playground` can use a local
clone; the exact pinned commit is archived, independent of working-tree edits.
Use `--test` to also run the upstream simulator tests.

On Linux, Qt WebEngine also needs the normal Qt graphics libraries plus
`libxtst6`, `libxkbfile1`, `libnss3`, and ALSA (`libasound2t64` on Ubuntu 24.04).
The desktop build workflow installs these and builds the preview. `package.py`
requires and bundles the generated assets and Qt WebEngine runtime. Source
launches without built assets show setup guidance when the preview is opened.

After building, previewing requires no internet connection, Node.js, external
browser or native HDL tool installation. An ephemeral server serves only built
assets on `127.0.0.1`; RTL stays in the application and is passed directly to its
private web renderer. Remote requests and navigation are blocked. The server is
stopped on project teardown and application exit.

## Upstream and attribution

Based on [Tiny Tapeout VGA Playground](https://github.com/TinyTapeout/vga-playground),
commit `3e3c77e46ae7bd51609f680851aabb81a30564a6`. The Studio adapter replaces the
web editor with the native editor and extends compilation to accept nested
source paths, include directories and defines. The upstream simulator, presets,
input controls and VGA decoding remain the basis of the preview.

The build includes the adapted source as `vga-playground-source.zip`, its GPL
license, upstream attribution, preset notices, and npm dependency licenses.
See [third-party notices](../THIRD_PARTY_NOTICES.md) for component source links.
