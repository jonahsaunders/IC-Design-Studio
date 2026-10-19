# IHP varactor physical interfaces

Studio's **Verify IHP layout with KLayout extraction…** action now retains the
public `sg13_hv_svaricap` interface: G1, W, G2 and substrate, with W/L, Nx and
multiplicity. The native public writer's four-terminal `C` record is converted
to an explicit `X` comparison primitive. Ordinary two-terminal capacitors stay
unchanged. Missing terminals, duplicate or unresolved parameters, unsupported
parameters, nonpositive dimensions and fractional counts are rejected.

The explicitly contacted small-device coupons now pass all forty selected
geometries and rotations, with all twenty-eight faults detected. This is partial
family coverage: the larger geometries and chunk 7 remain incomplete. It adds
no foundry approval or new electrical model.

## Recognition and connectivity

The private verification export retains exact `SVaricap` recognition text on
63/0 while removing unrelated child-local net labels. The private extraction
copy no longer connects those annotations to electrical nets. Actual conductor
labels and contact/metal geometry establish connectivity. Every retained
recognition label must correspond to exactly one extracted varactor.

A two-device native control places equal recognition strings on two physically
separate well terminals. The original public text-to-port connection joins them
and fails the port comparison. The corrected route preserves both distinct
terminals and passes full DRC/LVS. Original public rule sources stay unchanged.
The public Netgen setup permits interchange of G1/G2; W and substrate remain
distinct. No extra pin equivalence or parameter tolerance is introduced.

## Source geometry and limits

The [source inventory](../icstudio/assets/qualification/ihp-varactors/SOURCE.json)
pins the public IHP GDS/CDL and device-generator source at commit
`5e6d592e4002946a4616f798c357f0f3c06cf3b6`. All originals retain Apache-2.0.
The test GDS omits ThickGateOx, even though `SVaricap_code.py` explicitly creates
it. The coupon generator adds that exact rectangle in nanometres:

```text
(-100, -790) to (1150 + Nx × (500 + 2 × L_nm), W_nm + 1820)
```

It also adds conductor labels at the three original pin masks and a separate
contacted p+ substrate tie. Other public device polygons stay unchanged. This
is a documented coupon correction, never a silent repair of imported layouts.

The first run used W=3.74 µm and L=0.3 µm, Nx=1 through 10 at four rotations.
Its retained historical results were:

| Result | Cases |
| --- | ---: |
| Native extraction and strict LVS pass | 40 |
| Full native DRC and LVS pass (Nx=1, 2, 3, 5) | 16 |
| Unresolved full-DRC findings (Nx=4, 6–10) | 24 |
| Deliberate faults detected at Nx=1 | 12 |

The contact-width cause is now proved from the native imported geometry: Magic
splits a written cut into `pc` and `varc` fragments where it crosses the poly/
varactor boundary. Their union exactly matches the original contact mask; the
`pc` fragment alone can be only 135 nm wide even though the complete cut is
160 nm. The private Magic copy now measures `(pc,varc)/m1` with the same 160 nm
minimum. Every other dependency is byte-identical, the full DRC style is retained,
and no reported finding is filtered. Both this native rule and the separate
written-mask check reject the deliberately narrowed 155 nm contacts.

To satisfy the retained Magic tie checks, the opt-in `--contacted` coupons make
explicit layout additions. They extend the right active, well, buried-well and oxide edges
by 300 nm, add a second column of ten well contacts, and extend and contact the
two existing substrate tabs outside the well/oxide clearance. These additions
preserve all original drawn areas, all gates, all pin masks and recognition text.
They are a documented coupon construction, never an automatic layout repair.

The contacted W=3.74 µm, L=0.3 µm coupons give:

| Result | Cases |
| --- | ---: |
| Full DRC, unfiltered extraction, strict LVS and export checks pass | 40 |
| Deliberate physical/reference faults detected | 28 |

Removing either the added well contacts or substrate contacts from Nx=10
reproduces the tie-distance findings. The original Nx=4 coupon now passes with
only the contact-operand correction; the original Nx=10 coupon still fails with
23 tie-distance findings. The original W=9.74 µm, L=0.8 µm, Nx=1 fixture still
reports seventeen well-related findings despite passing LVS. These cases remain
failed. The runner exits unsuccessfully when any selected geometry fails.

An independent investigation runs both unmodified public IHP KLayout geometry
decks (main and maximal) at the same pinned commit. Both pass the original large
Nx=1 and original small Nx=10 fixtures; those decks contain explicit varactor
exceptions. They also pass the contacted small Nx=10 fixture. The oxide-removal
and narrow-contact probes produce native findings. This identifies a possible
route for the remaining geometries, but it is not yet an integrated, fault-tested
replacement qualification. The application still retains the Magic failures.

The first twelve controls remove oxide, recognition or gate contacts; duplicate
recognition; short gate to well; and alter reference W, L, Nx, multiplicity,
well, substrate or a gate terminal. A tool crash does not count as detection.
Sixteen additional controls narrow mixed or varactor contacts and remove either
new tie set in four orientations. Independent readback checks 80 native/comparison
netlists, 400 exported layer pairs and retention of every original drawn mask area.
Six Windows backend cases verify 720 received files. Eight earlier bipolar, tap
and coil cases pass, alongside the original-layout controls described above.

The [contact and tie execution record](validation/ihp-varactor-contacts-2026-10-19.json)
retains the new successful and failed runs, source hashes and recovery information.
The [earlier record](validation/ihp-varactor-and-detector-2026-10-19.json) retains
the original findings and detector work.
The existing [coil qualification](IHP_INDUCTOR_QUALIFICATION.md) and earlier
bipolar/tap checks remain separate.

## Reproduction

The native CI regression checks all forty explicitly contacted small layouts
and twenty-eight faults. Independent cases run in separate processes:

```text
python scripts/qualify_ihp_varactor_layouts.py --size small --contacted --workers 2 --output NEW_OUTPUT --magic MAGIC --netgen NETGEN --klayout KLAYOUT
```

Use `--pilot --workers 1` for one contacted positive and sixteen faults. Omit
`--contacted` to reproduce the original coupon construction; omitting both
`--contacted` and `--size small` also includes the larger public geometries.
Those wider original-layout checks still fail. The pinned source originals,
private corrections and generator attribution are included in
[third-party notices](../THIRD_PARTY_NOTICES.md).
