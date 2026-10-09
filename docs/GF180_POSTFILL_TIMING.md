# GF180 reference post-fill timing

The six frozen GF180-C and GF180-D counter, UART and APB candidates now pass
post-fill timing at their three captured library conditions. This closes the
reference timing experiment; **chunk 4 and process qualification remain open**.
The [retained evidence](validation/gf180-postfill-timing-2026-10-09.json) records
the inputs, controls, numerical limits and permanent archive.

## Correct physical loads and complete annotation

The APB experiment exposed an application defect: physical netlist export
removed `CORE_ANTENNACELL` masters, although their characterized input
capacitance and SPEF terminals remained in the layout. OpenSTA warned that
the antenna endpoints were missing, but positive slack alone produced PASS.

Physical export now retains antenna cells. Native exports from all six original
databases differ only by two input-only antenna instances in each APB design,
on `pwdata[2]` and `reset`. The other four netlists are byte-identical. Fresh
equivalence proofs pass for both corrected APB netlists.

Extracted timing now captures library/netlist/SDC/SPEF load diagnostics and
requires a complete parasitic-annotation report. Missing connected drivers,
partial annotation, missing reports and unresolved load warnings prevent PASS.
The engine separately records outputs with no connected net: these need no
interconnect annotation. No cell-name prefix grants an exception. Every
scenario discards its previous generated reports before execution, so a later
corner cannot borrow an earlier clean result. Per-scenario artifacts retain the
reports and diagnostics for review.

## Reference experiment

The extraction copies represent each final floating Metal1 square as an
isolated routed conductor with its exact written-GDS bounds. Independent
readback verifies all 911 counter, 2,123 UART and 2,119 APB squares per variant,
and verifies that original signal resistances and terminals remain unchanged.
The C 9K and D 11K typical extraction rules remain separate.

The floating capacitance reduction preserves coupling and substrate return.
An independent finite-resistance calculation tests 25 frequencies from
100 kHz to 50 GHz for each reference. The largest sampled error relative to
the added admittance matrix is approximately 1.26e-6, below the predeclared
1e-4 limit; all solve residuals satisfy their separate bound. Six deliberately
increased-resistance controls fail that bound. This measures the reduction
against the captured RC model, not the field accuracy of the extractor.

The native timing batch contains:

- 18 passing before-fill and 18 passing filled cases, preserving original
  constraints and checking setup, hold and electrical limits.
- 18 capacitance faults that fail timing.
- 18 removed-clock-extraction controls that retain positive slack but are
  rejected for missing annotation.
- Six omitted-antenna controls that retain positive slack but are rejected for
  unresolved extraction endpoints.

Independent Windows and Linux audits reproduce all 78 outcomes and all six
model checks. The final application source passes 1,650 unit tests with 62
environment-dependent skips, plus 34 focused tests on each operating system.
The initial sandbox-restricted suite and rejected diagnostic attempts are
retained separately from passing evidence.

## Remaining scope

These results use three Liberty conditions, one stack-specific typical
interconnect condition and explicit coupling reduction factor 1.0. They do not
establish general signal-integrity behavior, calibrated field extraction,
complete PVT coverage or foundry acceptance. Full transistor-RC waveforms are
separate experiments; no passing waveform is inferred from these timing runs.

The fill/extraction candidate still needs complete application integration and
remaining fill-coverage acceptance. The original geometry, source inputs and
running simulations are unchanged. Complete-chip boundary/scribe acceptance,
broader extraction qualification and public desktop-package acceptance retain
their separate gates in the [qualification plan](PDK_QUALIFICATION_PLAN.md).
