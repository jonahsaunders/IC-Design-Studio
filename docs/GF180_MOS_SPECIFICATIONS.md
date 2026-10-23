# GF180 public MOS electrical specifications

This chunk-7 check compares standard GF180 C/D 3.3 V NMOS and PMOS with
published numerical current limits at W/L = 10/0.28 micrometres and 25 C.
It adds an independent numerical reference to the existing application versus
independent-deck comparisons, which use the same underlying PDK model.

The [source bundle](qualification/gf180-mos-spec-sources-v1/README.md) retains
unmodified public sources from revision
`de3240d7529a6970437ac3344820aaae7839f215`, their origin/hashes and Apache-2.0
license. The project license does not replace the upstream license.

## Measurement and acceptance

[`qualify_gf180_mos_specs.py`](../scripts/qualify_gf180_mos_specs.py) runs all
five process selections: nominal, ss, ff, sf and fs. Each case has separate
application and independently written circuits, positive and negative gate
sweeps, four-terminal current probes and actual terminal-voltage checks.

- Saturation current: VDS = VGS = +3.3 V for NMOS and -3.3 V for PMOS.
- Off current: VGS = 0, VDS = +3.63 V or -3.63 V, respectively.
- Source and body are grounded. Signed drain current is divided by 10 um.
- Coarse and fine gate grids use 5 mV and 2.5 mV steps.
- Wrong multiplicity, width, gate/drain connection and process corner must
  each produce a mismatch for all six probe devices. Launch or parse failures
  do not count as detected device faults.

Published current bounds are applied literally. No rounding, fitted tolerance
or typical-value matching can turn an out-of-bound result into a pass.
The application/reference numerical comparison uses 1 ppm relative and 100 fA
absolute tolerance. That absolute allowance is 0.01 pA/um at the test width;
it is not added to any published limit. Tightened solver settings and measured
current-conservation residuals are retained. Default gmin remains unchanged.

The source specifies maximum-gm threshold extraction at |VDS| = 0.05 V but
does not give a complete equation. Both the tangent intercept and its signed
VDS/2 correction are reported as diagnostics. A 0.1 mV coarse/fine convergence
check verifies the numerical calculation; **threshold is not a passed
specification requirement**.

## October 23 result

Both local hosts completed all ten cases, all 240 faulty device instances per
host and independent native-file/model-input readback. Windows ngspice 46 and
the corrected Linux ngspice 47 produced identical reported current values.
Eight cases meet the printed current limits; both ff cases retain a mismatch:

| Current density | Simulated ff | Published bound | Excursion |
| --- | ---: | ---: | ---: |
| NMOS Idsat, uA/um | 590.277446 | maximum 590 | +0.277446 (0.0470%) |
| PMOS Idsat, uA/um | -290.390199 | minimum -290 | -0.390199 (0.1346% of magnitude) |

Both C and D use the same locked transistor model. Separate direct-model
diagnostics using public subcircuit defaults also exceed those printed limits
(590.504375 and -290.465359 uA/um). Default versus tightened solver settings
leave the catalog-geometry saturation measurements unchanged. These controls
show that the discrepancy is also present without application instance
emission; they do not establish its upstream cause or justify relaxing a limit.
The printed precision may be relevant, but no rounding policy is assumed.

See the [execution record](validation/gf180-mos-specifications-2026-10-23.json)
for exact sources, engines, raw-data audits, initial failures and archive IDs.
The 47 affected tests pass on both hosts. The first Windows test attempt hit
sandbox temporary-file permissions; an ordinary-user retry passes unchanged
tests without administrator access.

## Reproduction

From the repository root with its Python dependencies and a compatible local
ngspice executable:

```text
python scripts/qualify_gf180_mos_specs.py --ngspice /path/to/ngspice --output /new/output/directory --workers 2
```

`--pilot` selects the nominal case for both variants. The output must be new.
Exit 0 means the selected current checks pass; exit 2 means execution and fault
controls completed but a published bound differs; exit 1 means incomplete or
invalid execution. Read `execution_status` separately from
`specification_status`. Every result keeps `qualified: false` and
`chunk_complete: false`.

This is one geometry and temperature for two models. It does not qualify full
device envelopes, other transistor types, statistical accuracy, reliability,
silicon correlation, physical layouts or an installed release. Device statuses
and the chunk-7 completion gate remain unchanged. The strict mismatch must
remain visible in any future automation; exit 2 must not be converted into a
qualification pass.
