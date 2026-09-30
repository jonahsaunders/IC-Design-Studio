# Student Hub

Open **File → Student Hub** or choose **Student Hub** in the example gallery.
Four learning paths contain six lessons each. A further four milestones build
one advanced sensor-acquisition project. Every lesson has a prediction, a
workspace task, a measured or structural checkpoint, and a written reflection:
**28 lessons and 112 steps** in total.

![Four learning paths in the native Student Hub](images/student-hub.png)

## Learn beside the real editor

1. Choose **Continue learning**, or select a path and a lesson.
2. **Start lesson** creates an independent, saved project. Existing work goes
   through the normal save/discard/cancel flow before another document opens.
3. The **Student lesson guide** stays beside the schematic, layout or RTL editor.
   Follow the current instruction, edit the real design, and use **Run lesson**.
4. **Results** opens the existing waveform or digital/mixed-signal workspace.
   **Check this step** evaluates the current design and captured evidence. Read
   the result, then choose **Next step** when ready.
5. Write your reasoning in the reflection field. Draft notes save automatically;
   **Record reflection** adds the note to the learning record.
6. **Save work** preserves circuit/RTL edits. **Resume lesson** reopens that file
   next time. The four advanced milestones share one project and retain earlier
   repairs.

The guide can be reopened from **View → Lesson guide**. **Student Hub**
returns to the progression map. Use **Cancel lesson runs** to stop only the jobs
launched for that lesson project. Duplicate submissions are blocked while a run
is queued, running or stopping. A failed simulator run does not earn credit.

The Hub adapts to a narrow window. **More → Text size** enlarges text up to 200%
in both the Hub and guide; scrolling keeps controls reachable. Use **Cmd+F** on
macOS or **Ctrl+F** on Windows/Linux to search the current path. Return in search
focuses the lesson list; Return on a lesson opens it. Tab navigates controls.

**More → Locate lesson project** reconnects a moved file after checking its
project identity. **More → Reload progress** recovers changes saved by another
window; if both windows edited the same reflection, choose which version to keep
or cancel to preserve the unsaved draft. A failed draft save blocks dismissal or
app exit until the draft can be preserved. **Export learning record** saves the
current lesson's circuit/RTL edits before exporting; cancelling Save cancels export.

See the [two-pass interface audit](STUDENT_HUB_AUDIT.md) for findings, validation,
and the remaining native macOS acceptance work.

![The lesson guide beside the editable schematic and real waveforms](images/student-lesson.png)

## Four paths

| Path | Progression | Final outcome |
| --- | --- | --- |
| Foundations | First RC transient → nets/ground → parameter edits and Undo → hierarchy → loading/debugging → layout and reproducibility | A saved, measured circuit and a learning record |
| Analog | Loaded divider → RC bandwidth → current mirror → differential pair → five-transistor amplifier → matching and layout review | Measured bias and gain, with a physical implementation review |
| Digital | Truth tables → enabled counter → one-cycle handshake → PWM → fixed-point averaging → serial transmitter | Independently checked synchronous RTL and serial framing |
| Mixed Signal | Bridge thresholds → acquisition/hold → quantization → timing repair → DAC-weight repair → repeated conversions | A working SAR converter with explicit analog/digital timing |

The first three Foundations lessons unlock Analog and Digital. Mixed Signal
requires the bandwidth and counter lessons. Completing all four paths unlocks
the advanced project for progression credit. All lessons remain available for
preview and **Practice lesson**: practice checks give feedback but do not bypass
prerequisite credit. Estimates are per lesson, not deadlines.

Knowledge questions check the selected answer. Circuit checkpoints inspect
specific properties or numerical results. Structural layout checks establish only
that the lesson geometry exists. Reflections are **recorded, not automatically
assessed for correctness**. Their wording asks learners to state observations,
reasoning and limitations for instructor or peer review.

## Engines and models

**More → Engine setup…** in the Hub selects native local `ngspice`, `iverilog` and
`vvp` executables. Blank Icarus fields search PATH; blank ngspice uses Studio's
native discovery, including its bundled executable and `ICSTUDIO_NGSPICE`.
Earlier mixed-signal executable selections are used as defaults. Missing tools
produce a setup error; the Hub does not download engines automatically.

On Ubuntu, `sudo apt install ngspice iverilog` supplies these tools. On Windows,
select native executable paths. The Windows source launcher provisions ngspice
only; Icarus needs a separate native installation. See the
[SAR local-engine setup](MIXED_SIGNAL_SAR.md#local-engine-setup). WSL executable
paths and a Ready managed digital runtime do not configure these lesson tools.

Foundations and Analog use the included teaching solver and generic devices.
Digital uses Icarus and embedded reference testbenches. Mixed Signal and the
capstone run the actual ngspice/Icarus closed loop described in the
[SAR walkthrough](MIXED_SIGNAL_SAR.md). The managed digital container/WSL toolchain
is not the runtime for these lessons. Tool availability and successful process
startup alone are not numerical qualification.

The analog lessons deliberately introduce concepts without an external PDK.
Generic MOS results exclude body effect, subthreshold behavior and device
capacitances. The SAR comparator and switch are behavioral. The course does not
establish foundry DRC/LVS, transistor-level ADC accuracy, ENOB/SNDR or silicon
performance. Later physical work needs a selected, qualified process and its
actual decks and models.

## Advanced project: sensor acquisition system

The signal chain is an RC input filter, sample/hold, four-bit SAR, four-sample
block averager, and threshold alarm. The starter intentionally contains three
faults: an excessive filter capacitor, inverted SAR comparator interpretation,
and an incorrect averaging shift. Each milestone repairs one block and measures
its own requirements before the final system campaign.

![Four milestones in the advanced sensor-acquisition project](images/student-capstone.png)

| Requirement | Target |
| --- | --- |
| Reference / clock | 1.8 V / 1 µs |
| Input filter | 1 kΩ and 100 pF; 100 ns time constant |
| Nominal input sequence | 0.2, 0.4, 0.6, 0.8, 1.0, 1.2, 1.4, 1.6 V |
| Raw codes | 1, 3, 5, 7, 8, 10, 12, 14 |
| Completion edges | 7, 15, 23, 31, 39, 47, 55, 63 |
| Acquisition error | Less than 2 mV at the first comparison of each conversion |
| Averaging | Non-overlapping blocks of four; `(sum + 2) >> 2`, halves rounded upward |
| Averaged codes | 4 and 11 |
| Average-valid edges | 32 and 64; SAR completion is consumed on the next clock |
| Alarm | Assert when the averaged code is at least 10; nominal outputs 0 then 1 |

**Run qualification** captures four copies of the reviewed design: nominal,
below-range input, above-range input, and input changes after acquisition.
The open project is unchanged. All code, cadence, averaging, alarm, sample-count,
decision-count and acquisition requirements must pass for all four cases.
The checker uses fixed independent reference requirements; it does not infer
expected codes from the edited DAC or RTL.

The original correct reference design can be generated and independently tested
with `python scripts/verify_student_capstone.py --out build/student-capstone`.
It is separate from the intentionally faulty teaching starter. The script also
injects filter, comparator-decision, averaging and alarm faults to demonstrate
that the acceptance requirements detect them.

## Progress and evidence

Progress is stored in the application's local data directory under `student-hub`.
Project files remain normal `.icproj` documents. **Save As** followed by **Save
work** updates the lesson's resume location. If a lesson file goes missing or is
replaced by another project, the Hub reports the problem instead of resetting it.
Corrupt or concurrently changed progress is not silently overwritten.

An earned checkpoint includes its project identity/design hash and, for a run,
the captured job/result hashes, engine/environment identity and run location.
Digital and mixed-signal artifacts are revalidated using the existing job reader.
Results from earlier edits, another project, interrupted jobs or a changed
reference testbench cannot earn a numerical checkpoint. Even Undo produces a
new project revision; rerun before earning a new simulation checkpoint.

Earned steps are historical achievements, not claims about all future edits.
Updating a lesson or its grading revision requires rechecking that lesson;
unrelated application releases preserve progression. Dependent progression also
checks its prerequisites. **Export learning record** writes JSON
with progress, reflections, saved project snapshots and evidence references. Save
edits before exporting. Raw run directories are referenced, not embedded; include
them separately when sharing a complete reproducible simulation package.

## Feature map and further work

| Feature | Guided entry | Further workflow |
| --- | --- | --- |
| Schematic, properties, nets and ground | Foundations 1–3 | [Getting started](GETTING_STARTED.md) |
| Hierarchy, cells and reusable blocks | Foundations 4 | [Getting started](GETTING_STARTED.md) |
| Analysis, traces and comparison | Foundations 1–5; Analog 1–5 | [Analog workspace](ANALOG_WORKSPACE.md) |
| Bias, AC gain, specifications and closure | Analog 3–5 | [Analog closure](ANALOG_CLOSURE.md) |
| Optimization and variation studies | Analog 5 reflection | [Analog optimizer](ANALOG_OPTIMIZER.md) |
| Layout, matching and physical evidence | Foundations 6; Analog 6 | [Layout scale and collaboration](LAYOUT_SCALE_AND_COLLABORATION.md), [PDK guide](PDK_GUIDE.md) |
| RTL, testbenches and digital waveforms | Digital 1–6 | [Digital workspace](DIGITAL_WORKSPACE.md) |
| Synthesis, timing and implementation | Digital 6 extensions | [Digital flow](DIGITAL_FLOW.md) |
| Bridge timing, DACs and SAR conversion | Mixed Signal 1–6 | [Mixed-signal SAR](MIXED_SIGNAL_SAR.md) |
| Captured runs, cancellation and handoff | Every measured lesson; capstone 4 | [Project Hub](PROJECT_HUB.md) |

These links expose the broader application without treating unperformed
optimization, physical verification or implementation as completed course work.

## Developer verification

```sh
python -m unittest tests.test_student_hub -v
python scripts/verify_student_capstone.py --out build/student-capstone
QT_QPA_PLATFORM=offscreen python tests/gui_student_hub.py
```

Run from the repository root in its Python environment, with a fresh output
directory for each captured campaign. In PowerShell, set
`$env:QT_QPA_PLATFORM = 'offscreen'` before the GUI command instead of using the
POSIX assignment prefix. The capstone script also accepts `--ngspice`,
`--iverilog` and `--vvp` paths for an explicitly selected native toolchain.

The unit suite exercises all 28 starters, prerequisite cycles, persistence,
concurrent writes, stale/corrupt evidence, all twelve Foundations/Analog lessons,
six real RTL reference benches, six mixed-signal lessons and capstone fault
detection. Engine tests require installed tools or `ICSTUDIO_TEST_NGSPICE`,
`ICSTUDIO_TEST_IVERILOG` and `ICSTUDIO_TEST_VVP`. The desktop check additionally
tests save cancellation, practice without credit, shared capstone work, export,
autosaved notes and cancellation. CI uploads raw evidence directories.

## Retained execution evidence

The [capstone campaign](validation/student-hub/capstone.json) passed all four
acceptance cases and detected all four deliberately injected faults. The
[desktop record](validation/student-hub/desktop.json) records the exercised
learning workflow. [Test commands and outcomes](validation/student-hub/checks.json)
include the full suite (1,216 tests, 51 skipped), 10 focused progression/engine
tests, and the six final progression regressions, including update-stable credit
and packaged-build identity handling. The [release consistency check](validation/student-hub/release-check.json)
also passed.

Numerical and desktop evidence was executed on Linux with Qt offscreen,
Python 3.12, ngspice 42 and Icarus 12. The existing
[host runtime record](validation/mixed-signal-sar/host-runtime.json) identifies the
same underlying binaries and workspace-specific scratch-file adapter. The frozen
identity check emulates the packaged source layout; this record does not claim a
complete packaged or native Windows run. Raw captures are retained by the CI
workflow; compact reports and screenshots are committed here.
