# IHP LV extracted-parameter source linkage

The selected two-finger `sg13_lv_nmos` layout now has an independently checked
electrical link to a saved application native-SPICE view. Each extracted channel
retains its own width, length, junction areas, junction perimeters and positional
drain/gate/source/body connections. The two channels remain separate `ng=1`,
`m=1` calls. The original catalog device is retained as a distinct diagnostic;
its default junction geometry differs from the actual extraction.

The [finite source record](validation/ihp-lv-extracted-linkage-source-2026-10-30.json)
covers one asymmetric two-finger NMOS coupon, `mos_tt` at 27 °C. Eleven actual
native Linux processes using the retained managed-runtime ngspice 42 cover DC and AC for the application view,
unaltered native extraction, literal reference and original catalog, plus
three changed-device controls. Application and native-extraction currents match
the literal reference exactly at the retained samples. All four terminal
voltages, full complex currents and current conservation pass the original
limits. The record's comparison dictionaries report normalized errors: positive
agreement must be at most 1; an injected fault must exceed 1. Catalog differences
are diagnostic. Changed width, junction area and junction perimeter are detectable.

An independent review reproduced the complete result. The reader also rejects
29 deliberately corrupted full evidence copies after their producer hashes are
recomputed, including altered input/runtime identities, wrong biases, missing or
nonfinite channels, zeroed responses, ineffective faults and retained raw data
after a failed simulation. All original evidence remains unchanged.

The verified compact archive contains 2,664 logical files in 1,245 unique objects,
including exact source, model, runtime and review records. A separate readback
restored the archived reader and its archived dependencies on Windows and
reproduced the numerical verdict without rerunning a simulator. This is an
archive portability check; actual Windows application execution remains separate.

This milestone does not change the default catalog's parameters, qualify a
complete transistor family, establish operating or reliability limits, or
provide installed acceptance. The retained layout extraction is device-level
evidence; broader geometries, polarity, conditions and parasitic extraction
remain outside this finite result.
