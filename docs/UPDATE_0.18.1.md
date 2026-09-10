# IC Design Studio 0.18.1 — simulation startup fixes

This patch fixes the two reported 0.18.0 startup failures.

## Upgrade

Extract the new Windows ZIP into its own folder and run `ICDesignStudio.exe`. Open your existing `.icproj` or `.sch` and press F5. Existing projects do not need conversion or manual library-path edits. Start a new run to use the corrected deck generation; earlier failed entries remain in the history.

For source use, extract the entire Source ZIP and install its Python requirements as described in README. This source download includes Windows ngspice in `icstudio/assets/runtime/ngspice`. Keep that directory with the source. The native Windows app additionally includes Python and Qt, so it needs no separate Python installation.

## Changes

- Model includes and library statements use relative ASCII filenames. ngspice 42 was splitting the previously quoted absolute `.lib` paths at spaces, including the space in the application's own `IC Design Studio` data directory. Both top-level and nested model references are rewritten. Source files with identical text but different dependencies remain distinct.
- The simulator starts in the run directory and receives `input.cir` as a relative argument. SPICE exports retain their model references when moved together to another folder.
- The Windows app and distributed source package include `ngspice.exe`, its OpenMP DLL, its license and a minimal `spinit`. The child simulator gets the packaged initializer location without changing the application's global environment. This scalar-device runtime does not preload optional external code-model plugins.
- Runtime discovery accepts `ngspice_con.exe`, quoted configured paths, `ICSTUDIO_NGSPICE`, and common Windows installation locations. A saved path into an older app's bundled runtime migrates to the current bundle. Custom external executable choices remain supported.

The `spinit` message was a separate startup warning. The fatal failure in the reported log was the truncated model-library filename.

## Validation scope

The original failure was reproduced with ngspice 42 in a directory containing spaces. The corrected path is checked with actual ngspice execution, nested libraries, model filenames containing spaces, a non-ASCII parent directory, an executable directory containing spaces, and relocation of an exported deck. The supplied GF180 circuit is also exercised with a shortened diagnostic analysis program through the GUI worker. The complete 144-case characterization from 0.18.0 is not repeated for this path-only fix.

Native Windows execution has not been performed in this environment. Windows package contents, runtime dependencies and discovery are checked separately; these do not replace an execution test on Windows.

The ngspice 42 startup-file behavior is documented in its [official manual](https://ngspice.sourceforge.io/docs/ngspice-42-manual.pdf), sections 16.5 and 16.7.1.
