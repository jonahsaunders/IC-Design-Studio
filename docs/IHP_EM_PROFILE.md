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

The command accepts `--mesh-um` to refine the same fixture without editing its
source. The second mesh retains its 0.7 refinement factor, and both Z and R
retain the 5% limit. Keep geometry, materials and the frequency band unchanged
within a mesh study; a passing smaller frequency subset cannot qualify the
original band. `--max-cells` changes the explicit memory guard when deliberately
requested; its default stays at two million cells. All unsuccessful attempts
keep their own output directories.

The [native rejection record](validation/ihp-em-native-rejection-2026-10-21.json)
retains the actual Windows runs at 100–300 GHz. Its independent-column conversion
is historical and has the defect described below. All four 280 µm stages reach
the requested energy decay, but the two meshes disagree by 5.1% in impedance
and 98.5% in resistance. Independent full-matrix conversion confirms negative
coarse resistance for both substrate options. The 180 µm final refinement was
deliberately stopped after that independent review; it has no complete fine-mesh
acceptance result. Neither run attaches a characterized project.

The subsequent [measured-wave audit](validation/ihp-em-waves-2026-10-21.json)
identifies a conversion error: the unpowered port has a nonzero incoming wave
(up to 4.47% of the driven incident wave). The old driver divided each outgoing
column by only its own driven wave, implicitly treating the incident matrix as
diagonal. The corrected driver retains both incoming and outgoing waves from
both excitations and solves `B = S A`. Independent direct `Z = U inv(I)` from
the original voltage/current files agrees with that correction.

The corrected 280 µm readback has positive differential resistance at every
sample: 10.43–67.79 Ω coarse and 10.71–73.47 Ω fine. All sampled scattering
singular values are below one. However, mesh differences remain 4.80% in Z and
7.73% in R, so the unchanged 5% gate still rejects it. The 180 µm coarse pair
also has positive resistance; its stopped refinement is still incomplete.
The earlier negative-resistance explanation and early-stop decision were based
on the faulty conversion, not a demonstrated active physical device. Original
outputs remain unchanged and are not relabeled as new executions.

Older structured openEMS characterizations remain in saved projects but show
as stale and cannot be attached as current results. A new run is required.
The read-only `scripts/audit_openems_waves.py` command audits retained native
waveforms; it never installs characterization or qualifies a device.

The [completed 1 µm refinement record](validation/ihp-em-refinement-2026-10-21.json)
adds four finished native stages for each substrate option, using the corrected
wave conversion and unchanged 100–300 GHz band. Both runs reach their energy
targets and remain passive at every sampled frequency. The 280 µm case changes
by 4.0434% in Z and 5.3686% in R; the 180 µm case changes by 4.0433% in Z and
5.3710% in R. Both therefore fail the unchanged 5% resistance limit and attach
no characterization. These completed runs supersede the earlier stopped 180 µm
attempt only as newer evidence; the original failure remains preserved.

Windows and Linux independently reconstruct both results from the actual native
voltage/current files and agree with the application. The audit now retains
the actual probe coordinates, including current-loop enlargement and staggered
mesh placement. For example, the requested current plane is 175.1803 µm, while
the recorded base and fine planes are 169.479 and 171.173 µm. This reports the
solver's sampled geometry; it does not correct or de-embed the result. Paired
excitations with inconsistent coordinates are rejected. Source comparisons
verify unchanged masks, materials, port requests and band; only mesh size,
resource timeout and the existing mesh-dependent padding inside PEC change.

A separate [synthetic refinement study](validation/openems-mesh-study-2026-10-21.json)
reduced the base mesh limit from 2 to 0.5 µm and passed the then-current numerical
gate: 1.40% in Z and 1.95% in R, below the unchanged 5% limits. Its acceptance is
superseded by the [full-network audit](validation/openems-passivity-2026-10-21.json):
the fine response has a maximum scattering singular value of 1.151684, implying
gain for an incident-wave combination in this passive fixture. Both hosts now
reject attachment, and the saved characterization remains available but stale.
Agreement between meshes and positive differential resistance are insufficient.
Original outputs are preserved. Coil masks, materials, ports, band and reference
plane were unchanged within that study; computational padding inside the ideal
PEC cap changed from 2 to 1 µm under the existing mesh rule. These synthetic
materials cannot establish IHP convergence or device accuracy.

A private synthetic boundary study in the
[same completed record](validation/ihp-em-refinement-2026-10-21.json) uses a
50 µm side/bottom margin and five eight-cell PML boundaries, retaining the top
PEC plane. Both meshes pass the original checks: 3.44% in Z, 1.20% in R and
maximum fine-mesh scattering gain 0.98257. All drawn geometry, ports and bottom
material interfaces remain outside the absorbing cells. This changes both the
boundary method and domain extent, so it does not isolate their individual
effects. The production driver remains unchanged. A separate attempt to align
the current-probe plane still gives gain 1.14728 and is rejected. Neither private
experiment qualifies IHP materials or an intrinsic device model.

The unchanged production driver also passes a separate two-mesh study of the
50 µm synthetic fixture with its existing MUR boundaries: 3.71% in Z, 4.94% in R
and maximum fine gain 0.98288. It uses 97,980 base and 242,112 fine cells. Both
hosts independently audit the raw probes and reopen the accepted characterization.
The CI execution smoke test retains its original single-mesh scope. Neither
passing synthetic case resolves the failed IHP convergence or missing independent
device-accuracy references.

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
