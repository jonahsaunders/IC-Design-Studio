# IC Design Studio 0.23.1 — solver timing and Windows text repairs

0.23.1 is a maintenance update to the 0.23.0 desktop **engineering preview**. It
repairs the included teaching solver's transient schedule and ideal sources,
and makes the Windows desktop read its own guides and saved run logs as UTF-8.
The platform and process limits of [0.23.0](UPDATE_0.23.0.md) are unchanged.

This file describes the source at version 0.23.1. A desktop package exists only
when [release status](RELEASE_STATUS.md) records a completed release preparation
for an exact commit; until then the published downloads remain
[v0.23.0](https://github.com/jonahsaunders/IC-Design-Studio/releases/tag/v0.23.0).

## Included teaching solver

These repairs apply to the built-in solver used by the first-waveform example,
the Foundations and Analog lessons and any project without bound process models.
ngspice results are unaffected.

| Before | Now |
|---|---|
| A transient whose stop time is a whole number of steps could fail with `float division by zero`. Stop **1m** with step **10u** on the RC example was one such case. Other combinations ran but appended a duplicate final sample about 1e-18 s after the previous one, which also made `fft()` reject the result as non-uniform. | The schedule has exactly `stop/step` steps when that ratio is a whole number, every step is positive, and the last sample is at the stop time. A stop that is not a multiple of the step still ends with one shorter step. |
| Pulse edges that fall on a multiple of the period could be sampled one step late or early, so pulse widths differed from cycle to cycle. A 2 ms, 10 % pulse sampled every 10 µs was 20 or 21 samples wide depending on the cycle. | Every period has the same number of high samples. Edge timing is compared with a relative tolerance instead of a floating-point remainder. |
| A pulse with zero delay was already high at the operating point, so an RC driven by it started fully charged. The SPICE deck exported from the same project starts at the low level. | The initial condition is the level before the first edge, as in the exported `PULSE` source. The first step then rises. Pulses with a delay, including every included example, are unchanged. |
| A sine source ignored its delay except as a phase shift, and so was already moving at t = 0. | The source holds its offset until the delay, as the exported `SIN` source does. |

A result saved by an earlier version keeps its original samples. Run the
analysis again to obtain the repaired schedule. The solver's recorded source
hash changes, so exact-result reuse does not return an older result for the
same inputs.

## Windows desktop text

Windows desktop builds do not run Python in UTF-8 mode. Text read or written
without an explicit encoding therefore used the ANSI code page, while the
application writes projects, logs and guides as UTF-8.

- The included **Roadmap** and **Student Hub** guides did not open from the
  application on Windows, because those files contain characters the ANSI code
  page cannot decode. The other included guides, including Help, opened with
  corrupted punctuation and symbols.
- A completed run whose saved log could not be decoded was silently left out
  of the run history after restarting Studio. Logs containing some non-Latin
  path or file names were affected. The saved result itself was not deleted.
- Exported and imported decks, reports and tool logs read by the Windows
  application are now decoded as UTF-8, the same way as on Linux.

Source feedback sets `PYTHONUTF8=1`, which hid this difference. The new
`tests/test_text_encoding.py` checks the source directly. Forty-seven modules
whose exact bytes are bound to retained acceptance records are listed there and
not yet converted. Most read ASCII-escaped JSON or run inside the Linux runtime;
Xschem text import and the language-server working copy remain on the ANSI code
page for non-ASCII text on Windows.

Stopping a simulation, a tool run or a verification campaign on Windows now
starts `taskkill` without creating a console window.

## Verification scope

- `tests/test_teaching_solver_timing.py` compares the schedule and pulse edges
  with exact rational arithmetic over more than 1,000 stop/step pairs, checks
  the RC step response against the backward-Euler closed form, and ties the
  pulse and sine definitions to the exported SPICE source text.
- The exact previously accepted bytes of `simulation.py`, `run_manager.py`,
  `editor_workspace.py`, `build_info.py` and `__init__.py` are retained under
  `docs/validation/solver-timing-text-retained-source-2026-11-12/`. The GF180
  density reference gate still authenticates that historical source. The
  repaired source has not run that gate, and no process qualification changes.
- Hosted source feedback and the seven release gates are recorded in
  [release status](RELEASE_STATUS.md) for the exact commit they ran on. This
  file makes no claim about them.
