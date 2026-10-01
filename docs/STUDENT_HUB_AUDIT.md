# Student Hub: two-pass interface and build audit

Date: 2026-09-30. Scope: Student Hub, docked guide, project/progress persistence,
lesson-result handoff, and the failing desktop release workflow in PR #51.

This is a dated implementation/audit record. Its test totals, failures and host
observations retain their original scope; use [Student Hub](STUDENT_HUB.md) for
current behavior and engine setup, and [release status](RELEASE_STATUS.md) for
package identities. A later passing build does not rewrite this original audit.

## Review criteria

This is a cross-platform Qt desktop implementation informed by Apple's Human
Interface Guidelines, not a claim of Apple certification or a native SwiftUI UI.
The review used Apple's current [Accessibility](https://developer.apple.com/design/human-interface-guidelines/accessibility),
[Buttons](https://developer.apple.com/design/human-interface-guidelines/buttons),
[Sidebars](https://developer.apple.com/design/human-interface-guidelines/sidebars),
[Focus and selection](https://developer.apple.com/design/human-interface-guidelines/focus-and-selection),
and [Color](https://developer.apple.com/design/human-interface-guidelines/color) guidance.

Criteria: familiar navigation and keyboard behavior; restrained action hierarchy;
legible text and state indicators; adequate contrast in both appearances; text
enlargement; explicit feedback; and recoverable interactions that preserve work.
Qt retains native window decorations and standard accessible control roles.

## First pass: issues repaired

| Severity | Finding | Change and verification |
| --- | --- | --- |
| High | Reflection autosave could be lost on immediate application exit. | Flush before the Studio close chain. Injected disk-full failure blocks exit and preserves the last keystroke; successful retry persists it. |
| High | A failed save during step navigation left the selector and displayed reflection on different steps. | Restore the selector on failure; retain the draft and dirty state. Regression changes steps under an injected write failure. |
| High | Export could silently include an older saved circuit. | Flush pending editor fields and save the bound lesson before export. Save cancellation stops export. |
| Medium | Four oversized path buttons and multiple utility buttons crowded the small-window layout. | A path sidebar, lesson list and overview provide clear navigation. Narrow windows use a path picker and vertical panes. Utilities live in More. |
| Medium | Fixed type sizes, stale local theme colors and weak focus visibility. | System font family, 100–200% text controls, responsive guide, live theme updates, accessible names, and visible focus borders. |
| Medium | Return in a dialog could activate an unintended default button. | No automatic default buttons in the Hub; Return in search focuses results; explicit lesson activation opens the project. |
| Medium | The UI advanced past successful checkpoint feedback immediately. | Feedback remains on the checked step; Next step and Continue learning are explicit actions. |
| Medium | Run controls allowed duplicate submissions and gave little lifecycle feedback. | Show queued/running/stopping state and progress; disable duplicate runs; expose cancellation while active; disable unavailable results and wrong-project actions. |
| Medium | A moved project had no in-app recovery path. | Locate lesson project validates identity before relinking and preserves earned progress. |

## Second pass: additional issues repaired

| Severity | Finding | Change and verification |
| --- | --- | --- |
| High | Mixed-signal Results included runs belonging to other projects; the guide could open an older capture. | Filter by project identity and select the latest captured run for the active lesson. The real-engine GUI test inserts a foreign-project record and verifies it is absent. |
| High | An optimistic progress conflict could trap an unsaved reflection: reopening attempted the same failing save. | Reload reads fresh progress and preserves unrelated edits. Same-reflection conflicts offer Keep my draft, Use saved reflection, or Cancel. All three branches are exercised. |
| Medium | Switching projects left guide controls enabled; completion/cancellation could be associated with the wrong workspace. | Refresh binding immediately after project changes; scope jobs and feedback to the attached project and lesson. |
| Medium | Enlarged text could force a guide wider than the available panel. | Reflow actions into one column and use scrollable content. Test 420-pixel guide width at 200% text, plus 720 × 600 Hub layouts in both themes. |

The first Windows CI audit additionally exposed a headless-font setup problem:
Qt offscreen did not enumerate Windows fonts and rendered missing-glyph boxes.
The probe now loads the installed system font files, requires real glyphs, and
retains the strict no-horizontal-overflow assertion. The guide also chooses its
action columns from measured button widths and available space, including a
regression with a wider font at 100% preference. This gate now runs immediately
after dependency installation so UI regressions fail before expensive packaging.

## Build failure

The failed Windows job in [desktop release run 36720944016](https://github.com/jonahsaunders/IC-Design-Studio/actions/runs/36720944016)
stopped at **Stage verified Windows simulation engine**. An incomplete tracked
runtime correctly triggered provisioning, but the SourceForge transfer hit a
socket read timeout. The provisioning script advertised retries but attempted
only one download. Linux packaging and all six other workflow families passed
for the original Student Hub commit.

Provisioning now retries up to four times, alternates canonical and direct
SourceForge endpoints, removes partial transfers, and publishes only bytes
matching the existing pinned SHA-256. A verified archive cache reduces repeated
network dependency. Extraction, per-file verification and the Windows executable
probe remain required. Tests simulate a mid-transfer timeout, incorrect mirror
content and exhausted retries; they verify cleanup and preservation of the
previous archive. No build gate or checksum was weakened.

## Evidence and remaining acceptance

The automated second pass is [tests/gui_student_usability.py](../tests/gui_student_usability.py).
It runs the actual Qt UI and teaching solver, and is now part of desktop CI on
Linux and Windows. The real-engine lesson/capstone flow remains covered by
[tests/gui_student_hub.py](../tests/gui_student_hub.py).

Retained [audit evidence](validation/student-hub-audit) includes the usability
report, screenshots, provisioning regressions and release consistency results.
The local full suite passed **1,219 tests (51 skipped)**; the focused native-engine
Student Hub suite passed **10 tests**; the provisioning suite passed **12 tests**.
The guided desktop flow and all **10 usability/recovery scenarios** passed.
The actual pinned Windows archive downloaded, extracted and passed per-file
verification on Linux; its executable requires Windows CI for launch validation.
The sandbox's unavailable `/proc/meminfo` required a host-only py7zr memory-limit
override during that extraction, without changing the archive or application.
Measured text/accent contrast against the audited panel and selection backgrounds
ranges from **4.93:1 to 14.42:1**; state is also expressed in text.

Local visual testing uses Linux Qt offscreen. It establishes layout, keyboard
dispatch, persistence and signal behavior, not native macOS integration. Before
calling the experience fully Apple quality, run it on supported Macs with
VoiceOver, Full Keyboard Access, Increase Contrast, system appearance changes,
Retina scaling and real window-management interactions. The broader application
still uses its own light/dark palette and does not automatically adopt every
macOS accessibility appearance setting. No macOS build or VoiceOver pass is
claimed by these Linux/Windows checks.
