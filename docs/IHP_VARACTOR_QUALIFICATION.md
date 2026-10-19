# IHP varactor physical interfaces

Studio's **Verify IHP layout with KLayout extraction…** action now retains the
public `sg13_hv_svaricap` interface: G1, W, G2 and substrate, with W/L, Nx and
multiplicity. The native public writer's four-terminal `C` record is converted
to an explicit `X` comparison primitive. Ordinary two-terminal capacitors stay
unchanged. Missing terminals, duplicate or unresolved parameters, unsupported
parameters, nonpositive dimensions and fractional counts are rejected.

This is partial physical-device coverage. The wider varactor family and chunk 7
remain incomplete. It adds no foundry approval or new electrical model.

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

For W=3.74 µm and L=0.3 µm, Nx=1 through 10 at four rotations gives 40 cases:

| Result | Cases |
| --- | ---: |
| Native extraction and strict LVS pass | 40 |
| Full native DRC and LVS pass (Nx=1, 2, 3, 5) | 16 |
| Unresolved full-DRC findings (Nx=4, 6–10) | 24 |
| Deliberate faults detected at Nx=1 | 12 |

The unresolved findings concern native poly-contact width and tie-extension
rules. The W=9.74 µm, L=0.8 µm, Nx=1 fixture additionally reports well-related
findings despite passing LVS. These cases remain failed. The full runner exits
unsuccessfully when any selected geometry fails; no finding is waived.

The twelve controls remove oxide, recognition or gate contacts; duplicate
recognition; short gate to well; and alter reference W, L, Nx, multiplicity,
well, substrate or a gate terminal. A tool crash does not count as detection.
Independent readback checks 80 native/comparison netlists, 400 exported layer
pairs and unchanged original device masks. Three Windows backend cases verify
complete received artifacts, including a valid rotated device and two faults.

The [execution record](validation/ihp-varactor-and-detector-2026-10-19.json)
retains both successful and failed runs, source hashes and recovery information.
The existing [coil qualification](IHP_INDUCTOR_QUALIFICATION.md) and earlier
bipolar/tap checks remain separate.

## Reproduction

The selected native CI regression checks the small Nx=1 device and all twelve
faults. It makes no claim about the remaining geometry envelope:

```text
python scripts/qualify_ihp_varactor_layouts.py --size small --pilot --output NEW_OUTPUT --magic MAGIC --netgen NETGEN --klayout KLAYOUT
```

Omit `--pilot` for all ten finger counts and four rotations. Omit `--size small`
to include the larger public geometries. These wider checks currently fail on
the retained DRC findings. The pinned source originals and generator attribution
are included in [third-party notices](../THIRD_PARTY_NOTICES.md).
