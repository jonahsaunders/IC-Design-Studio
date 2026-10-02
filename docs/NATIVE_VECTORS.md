# Native buses and instance arrays

The native editor keeps buses and instance arrays editable in the
schematic. Validation, electrical checks, flattened and hierarchical SPICE,
saved testbenches, and operating-point readout expand the same ordered members.
Saving and reopening does not replace the compact schematic with scalar copies.

## Editing

Select one schematic device and choose **Configure instance array…** in the
Schematic menu. Enter `3:0` or `0:3`; an empty value removes the array. The canvas
shows the bounds next to the instance name. Terminal fields and placed net labels
accept `data[7:0]`, `data[3]`, or comma-separated slices such as
`data[7:4],data[1:0]`. The symbol editor accepts bus ports such as `input[3:0]`.
Ranges include both endpoints and retain their written order.

A scalar terminal on a four-member array accepts four ordered signals, or a
single scalar net explicitly broadcast to every member. A two-bit terminal on a
four-member array accepts eight signals in four contiguous two-bit groups, or
two signals broadcast as a whole port. One scalar cannot replace a multi-bit
port. Unlabelled bus/array terminals allocate distinct floating members unless a
connected scalar conductor requires broadcast.

For example, `Xbank[3:2]` with child port `p[1:0]` connected to `data[7:4]` emits:

```spice
Xbank__3 data[7] data[6] child
Xbank__2 data[5] data[4] child
```

Scalar and slice taps use explicit matching names. Connecting `data[2]` refers
only to that bit of `data[3:0]`; it does not connect every bit. A wire cannot merge
a scalar conductor with a bus or merge differently sized buses. Geometric bus
tap artwork is not provided; use named connections for taps. Different labels
on one existing geometric conductor remain an error until explicitly renamed.

## Native representation and safeguards

The instance name remains a scalar base name; bounds are stored separately:

```json
{"name":"Rbank","array":{"start":2,"end":0},
 "nets":{"p":"tap[3:1]","n":"tap[2:0]"}}
```

Expanded names are `Rbank__2`, `Rbank__1`, and `Rbank__0`. Member IDs derive from
the original device ID and explicit index, so rotation, movement and reopen do
not change identity. Name collisions with existing scalar instances are errors.
There are at most 128 members per expression/array and existing circuit capacity
limits still apply. Interface ports and global buses reject overlapping names.
Repeated net names in an explicit connection are allowed and mean an intentional
electrical connection; this does not permit repeated interface declarations.

Compact arrays must be materialized before physical placement or verification.
A scalar footprint cannot stand for every member. Remove an existing generated
primitive footprint before configuring its array, then generate member geometry
after materialization. Physical hierarchy materialization retains member
connections and deterministic identities.

Xschem export rejects compact array/vector capture that its scalar exchange
contract cannot preserve. It requires explicit scalar materialization first.
Executable Tcl and Xschem repetition expressions are not evaluated by native bus
parsing; keep unsupported source expressions on the external-engine path.

## Validation

`tests/test_native_vectors.py` covers descending/ascending ranges, slices,
broadcast and chunk ordering, hierarchy/parameter mapping, both SPICE emitters,
case/name collisions, invalid widths, globals, saved benches, history and reopen,
and actual ngspice operating-point results for an array resistor ladder. Its
simulator test runs when `ICSTUDIO_TEST_NGSPICE` or `ngspice` is available.
`tests/gui_native_vectors.py --out <directory>` exercises the desktop action,
inspector, placed labels, undo/redo and native saving, and writes a JSON report
and screenshot.
