# Public IHP top-metal electromagnetic inputs

The optional profile makes public IHP material values available to the existing
local openEMS workflow. It is an input and interface integration, not an IHP
compact-device model or an electrical-accuracy qualification. Chunk 7 remains
open, and the `inductor` and `inductor3` catalog models remain unavailable.

## Exact source and interpretation

The [source inventory](../icstudio/assets/physical/ihp_em/SOURCE.json) locks the
original Apache-2.0 XML, README and license at openEMS-IHP commit
`e29417aa1e5fb97b4ebd27dd1e4fcf043f97ef63`, pinned by IHP-Open-PDK commit
`5e6d592e4002946a4616f798c357f0f3c06cf3b6`. The originals keep their own license
and notices; Studio's adapter is GPL-3.0 project code.

The adapter requires the matching IHP package source identity and exact drawing
masks. It selects TopMetal1 (126/0), TopVia2 (133/0) and TopMetal2 (134/0), keeping
their published thickness and conductivity. It preserves all five public
environment slabs: bulk silicon, epitaxial silicon, oxide, passivation and air.
It translates the entire coordinate system by the declared substrate offset,
following the upstream reader's convention. Decimal arithmetic avoids display
artifacts when subtracting the published elevations.

`SG13G2.xml` declares 280 µm of bulk substrate. `SG13G2_200um.xml` declares
**180 µm of bulk substrate**, plus the epitaxial and overlying layers. The UI
labels both accurately. Neither option supplies frequency or temperature
calibration. Other drawn layers have no automatic mapping or exclusion; their
presence in the requested context blocks solving until a physical interpretation
is provided. Applying the profile changes no circuit model or physical deck.

## Geometry and application checks

The top-metal via recipe uses a 900 nm cut, 1,060 nm spacing and 2,000 nm pads,
giving 550 nm enclosure. The pad width satisfies TopMetal2's 2 µm minimum as well
as TopVia2's 500 nm enclosure requirement. Both complete public geometry decks
pass the single-via and 2×2-array fixtures. The combined reports detect all five
specific faults: cut width, cut spacing, lower enclosure, upper enclosure and
upper-metal width. The maximal deck supplements the main deck; a rule need not
be duplicated in both. No native finding is filtered.

Windows and Linux checks cover source tampering, wrong package/mask identity,
all retained material slabs, unmapped context, project save/reopen and undo/redo.
The native geometry runner is `scripts/qualify_ihp_topvia.py`; the desktop probe
is `tests/gui_ihp_em_profile.py`.

## Solver limits and remaining work

The real Windows openEMS pilot exposed a truncated Gaussian excitation at the
initial 1–5 GHz band and two-million-step allowance. The application now stops
on that native warning and refuses attachment even if a later log line reports
sufficient energy decay. A process-lifecycle test verifies prompt cancellation
when the warning arrives across separate output reads. Increasing a resource
limit never bypasses the convergence checks.

The separate native integration experiment uses a generated single-turn coil
and the existing two-port top-reference-plane fixture. It is distinct from IHP's
published device geometries. Energy decay, complete two-port results, mesh
agreement and intrinsic device accuracy are separate questions. The runner
`scripts/qualify_ihp_em_profile.py` retains the exact model, driver, original masks
and logs and only writes a passing report after every configured stage and
acceptance check succeeds.

The [native rejection record](validation/ihp-em-native-rejection-2026-10-21.json)
retains the actual Windows runs at 100–300 GHz. All four 280 µm stages reach
the requested energy decay, but the two meshes disagree by 5.1% in impedance
and 98.5% in resistance. Independent full-matrix conversion confirms negative
coarse resistance for both substrate options. The 180 µm final refinement was
deliberately stopped after that independent review; it has no complete fine-mesh
acceptance result. Neither run attaches a characterized project.

The existing top-reference fixture places the plane at 336.1303 µm and uses
321.9 µm vertical lumped ports because the public profile retains its 300 µm
air slab. This is an explicit solver fixture, not an intrinsic IHP inductor
measurement. Its port/boundary interpretation needs further work before making
device claims; the high-frequency band above is an integration experiment.

The editor and qualification command now stop after the coarse pair when its
negative resistance makes the unchanged final mesh gate mathematically
impossible. For tolerance `t < 1` and the existing `F = 1 mΩ` floor, coarse
`R < -t*F` cannot agree with any nonnegative final resistance under
`abs(R - R_final) <= t*max(R_final, F)`. Tiny negative roundoff within that
bound still reaches the normal final checks. This avoids futile fine runs
without relaxing any acceptance threshold or modifying the physical mesh.

Remaining device qualification needs an appropriate operating band, converged
meshes, boundary/port studies, comparison against independent public reference
data, temperature/frequency treatment, and physical verification of each claimed
device layout. Loading these source-locked materials does not resolve those
requirements or promote any unavailable device.
