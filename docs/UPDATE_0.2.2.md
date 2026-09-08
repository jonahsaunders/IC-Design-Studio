# IC Design Studio 0.2.2 — component symbol refinement

The schematic canvas, placement preview, component outline, and device browser now use slimmer resistor, capacitor, and voltage-source artwork.

- **Resistor:** the rectangular body is replaced by a US-style zigzag. The schematic body is 14 units wide, down from 24.
- **Capacitor:** plates are 32 units wide, down from 48, with a tighter 10-unit gap.
- **Voltage source:** the circle is 40 units across, down from 52, with smaller plus and minus marks.
- **Stroke weight:** these three schematic symbols use 1.5-pixel cosmetic strokes, down from 2; browser icons use finer strokes too.
- **Selection:** each of these components gets a compact, lightly tinted outline fitted to its width instead of the previous large square.

Dark mode remains the default. The electrical terminals retain their exact positions, and selection hit areas remain generous. Existing circuits keep their connections, values, and file format. The simulation engine is unchanged.

## Update on Windows

1. Close IC Design Studio.
2. Extract `IC-Design-Studio-0.2.2-Source.zip` into a new folder.
3. Double-click `launch-windows.bat` inside the extracted application folder.
4. Open your saved `.icproj` using File → Open project.

The launcher uses an installed 64-bit Python 3.12 and installs the pinned dependencies on first launch. The source package includes the previous platform-aware native-library fix and uses the Python solver when a compatible native core is absent. A Windows executable is not included.

The Linux archive contains a standalone executable with its runtime for Ubuntu 24.04 x86_64 / glibc 2.39 or newer. Keep the extracted `_internal` folder beside the executable.

## Verification

The existing native interaction check passed, including placement, selection, drag, pin wiring, and a completed RC analysis. The actual component and browser renderings were reviewed in dark and light mode; canvas symbols were also reviewed at all four rotations. The rebuilt standalone Linux executable also passed offscreen startup and clean exit. See `TEST_REPORT.md` for the validation record and `RELEASE_STATUS.md` for the engineering preview's remaining product limits.
