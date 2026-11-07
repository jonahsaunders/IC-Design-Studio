# SKY130 MiM shared bottom electrodes

The November 7 change removes a reproducible application rejection of an
unambiguous shared bottom electrode. Two existing 2×10 µm capacitor units were
joined by a same-net lower-metal bridge, preserving their capacitor markers,
contacts and upper routing. For both MiM constructions, native Magic DRC,
strict Netgen LVS and the 255-category public KLayout deck passed. The
application nevertheless stopped at its blanket shared-bottom guard.

The [validation record](validation/sky130-mim-shared-2026-11-07.json) separates
that reproduction, the failed first snapshot preparation, the verified native
development run, independent review and final integration evidence. This is a
source application improvement. It adds no installed or electrical acceptance
and does not complete `MIM-PHYSICAL-CLASSES` or `MIM-EXTRACTED-RC`.

## Supported interpretation

The existing pinned public PCell convention defines W along the bottom-contact
direction and L perpendicular to it. The application now derives that direction
independently for every rectangular marker sharing one continuous bottom plate.
Each marker must be wholly contained in that plate. External bottom contacts
must identify exactly one marker by horizontal or vertical projection, and
every marker needs a nonempty contact group on one axis. Contacts inside any
same-construction marker are top contacts and are excluded from this grouping.
Boundary-straddling, ownerless, multiply owned and conflicting-axis contacts
are rejected. The algorithm does not choose the nearest marker.

This supports a reusable contact-defined geometry class rather than a list of
accepted coordinates. Native device locations must still identify every written
marker exactly once. The normalizer preserves the original native extraction
and changes only W/L tokens where the independently established axis requires
it. Its previous source pins, 2–30 µm nonsquare bounds, 5 nm grid and first-MiM
5:1 aspect check remain unchanged. These application/generator bounds are not
new electrical validity limits. Isolated units, symmetric contact rings and
true-square dispatch retain their existing behavior.

The public `bconnect` PCell option joins access metal; it is not cited as proof
of a continuous bottom-metal contract. Here, existing construction masks,
unchanged native device declarations and both executable DRC checks establish
the finite shared-bottom examples. Neither those examples nor the orientation
rule establishes the resistance of an arbitrary shared plate.

## Retained finite proof

The native selection is two 2×10 µm units of each construction at
0° and 90°. All four imported-layout application jobs pass native DRC,
extraction, strict LVS and integrity checks, and all four public DRC reports
have zero violations across 255 categories. Native readback finds two intrinsic
units with ordered P/N terminals. At 90° it confirms exactly two W/L corrections;
at 0° it confirms unchanged extraction bytes.

For each construction, deleting one unit's external contact group rejects at
extraction after DRC passes. References with an incorrect width or unit count
reach native LVS and fail with property errors. Original and corrected EXT,
exported SPICE, written GDS, saved project, scripts, logs and reports are kept.
The separate reader checks contact ownership from GDS, the complete finite
native graph, exact non-dimension bytes, positive integral exported counts,
normalization provenance, actual reference contents, stage outcomes, source
identity and the complete retained file inventory. This checks preserved
topology; it makes no calibrated parasitic-value claim.

The final combined source snapshot reran this complete selection with the
reviewed reader. All 7,065 source files remained unchanged before and after
execution. The reader passed on native Linux and independently on the complete
Windows copy, verifying 319 retained files without substituting the source
guard. The [combined integration record](validation/chunk7-mos-shared-integration-2026-11-07.json)
separately records the affected test suites and final combined source identity.
The earlier failed preparation and successful development run remain distinct.
The first combined test snapshot omitted an authentic fixture log because of
the global log-file ignore rule. Its native run passed, but its Linux fixture
test failed. The final v2 snapshot explicitly includes that unchanged log and
reruns native acceptance; no existing source bytes changed between v1 and v2.

Independent geometry controls additionally cover all eight rigid transforms,
mixed per-unit X/Y directions on one plate, ambiguity faults, cross-construction
marker handling, and exact baseline equality for isolated and ring results.
Mixed per-unit directions have geometric review only; the native selection
uses uniform units at two rigid orientations. A small unchanged native fixture
supports recurring reader regressions without rerunning solvers in unit tests.

## Remaining scope

Stacked overlap, dummy devices, ambiguous contact layouts, arbitrary imported
routing, direct hierarchical native extraction, distributed/substrate/top-sheet
accuracy, model validity envelopes and statistical/reliability calibration
remain open. The previous installed and electrical records retain their exact
candidate and geometry scopes. The full-family gate and engineering completion
estimate are unchanged by the number of checks in this work.
