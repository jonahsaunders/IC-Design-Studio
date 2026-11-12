# IHP MIM.g source rule boundary

## Complete imported-device boundary — November 2, 2026

The [complete-capacitor source milestone](validation/ihp-cmim-complete-boundary-2026-11-02.json) now passes independent readback for six source-derived rectangular `cap_cmim` layouts. Each includes Metal5, TopMetal1, the full Vmim contact array and ordered physical ports; every layout preserves geometry and labels through GDS/OASIS exchange.

| Actual dimensions (µm) | Actual MIM area (µm²) | Main / maximal findings, at both rotations | Strict LVS |
| --- | --- | --- | --- |
| 75 × 74.98 | 5,623.5 | 0 / 0 | Pass |
| 75 × 75 | 5,625 | 0 / 0 | Pass |
| 75 × 75.02 | 5,626.5 | 0 / 1, exactly MIM.g | Pass |

Four native faults are detected for their physical causes: a complete 73 µm-wide capacitor passes DRC but fails the area/perimeter comparison against the 75 µm reference; missing contacts disconnect the upper terminal; a plate bridge shorts both terminals; and a reversed physical reference fails ordered-pin comparison. Ten rehashed copied-evidence controls and five additional independent written-geometry controls reject altered evidence. The independent reader checks the locked decks, original commands, unfiltered extraction, written masks, labels, contacts and exact native/reference dimensions and properties. The original exploratory outcomes remain retained separately.

The application now records MIM.g as `NOT_CHECKED` for Magic and directs the user to **Analysis > Verify IHP layout with public geometry decks**. The public route records `EXECUTED` only after validating both deck results and their identities. That is an execution statement; an above-limit layout still fails. Both actual 7 × 7 µm source-desktop routes passed six native stages with zero findings, matching current project/result identities and visible coverage text.

This recipe directly invokes the pinned public draw procedure beyond its default 2–30 µm parameter-check range. The independently measured 20 nm dimension steps are the chosen examples, not a claim that they are the closest possible legal boundaries. The physical reference follows the pinned symbol's `C`-form LVS representation with W/L/m. Its A and P values are independently derived as W × L and 2 × (W + L), matching the pinned extraction reader's source equations; this does not establish simulation-X equivalence at these sizes. The default PCell limits are unchanged. Electrical applicability, other geometry classes, operating/reliability limits, complete device-family qualification and installed acceptance remain open.

## Earlier bare-mask experiment

The existing IHP public KLayout checker was exercised through the application's checker API with three bare MIM mask polygons. Independently re-read polygon areas were 5,624.625, 5,625.000, and 5,625.375 µm², all on the 5 nm grid. The unmodified maximal deck reported MIM.g findings in counts **0, 0, and 1**, respectively. The main and maximal decks both ran for every mask. Their other findings remain in the retained native reports; these bare masks are not complete legal capacitors and this is not a zero-finding DRC or installed-release claim.

The original producer reported **FAILED** because it compared the KLayout category path without the quoting used by the report API. All six native deck results were retained. A separately versioned reader checked the exact category name and serialized path, original masks, full deck sources, commands, logs and reports, and recovered the 0/0/1 boundary result without rerunning the checker. An independent reviewer replayed it. Nine copied-evidence corruption controls rejected as expected. The failed producer and the separate readback are both retained; the producer was not relabeled as passed.

The evidence archive is `IC-Design-Studio-evidence/ihp-cmim-project-local-source-2026-10-30-v1/mim-g-source-evidence-v2.zip`, SHA-256 `06fe432399ea0edd3a5e75e776a558f3930fa948f43e43295ce3ff67263e06c7`. It includes the source and recovery scripts, full native reports, exact inputs, controls, and independent review. The prelaunch record pins 115 runtime and dependency file identities; the wrapper, executable and selected frontend binaries are retained, while dependency library bytes are not all copied into this compact archive. Actual imported or native complete-device layouts and installed application workflows remain separate requirements.
