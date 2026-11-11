# Finite IHP tap extraction-to-electrical pilot

The [November 11 execution record](validation/ihp-tap-linked-2026-11-11.json)
passes four native layouts, 16 physical fault controls, 24 positive raw
electrical files and 12 electrical fault files. Independent readback checks
564 positive and 252 fault points, all 36 staged model closures and all 216
original runtime-module copies. The single electrical batch takes 7.606 seconds;
67 focused, related and CI-integration tests pass. Earlier environment and raw-
reader failures are retained separately.

This additive qualification path joins the existing four 2 × 2 µm `ntap1` /
`ptap1` physical coupons (0° and 90°) to DC and complex AC execution. It does
not change the editor, managed runtime, source models, limits, or family status.

The original full Magic DRC, native KLayout extraction, strict Netgen LVS,
stream-exchange checks, and all original physical/reference faults remain
required. The native subcircuit's port order is read explicitly. TIE and body
roles, exact model, area and perimeter must match the saved geometry.

The public native extraction uses an `R` record with `A` and `P`; that syntax is
not silently treated as a directly executable simulation model. A separately
retained electrical projection uses the exact extracted model and computes
`R = 1 / (A / 9.8e-10 + P / 9.8e-4)` from native values. The two original public
symbol hashes and full model-file hashes are required. Each reviewed model's
entire subcircuit is a literal resistor: W/L do not recalculate R internally.
An independent ideal-resistor path therefore tests this source equation without
reusing the application's computed parameter. The original extracted text is
retained unchanged beside the projection.

The application path creates a real catalog device, saves and reopens its
project, then invokes the normal simulation backend and checks the emitted
model and terminal order. All three paths use a 1 kΩ / 1 pF load at 27 °C and
the nominal section. DC is −10 through +10 mV in 1 mV steps; AC is 100 Hz through
10 MHz, five points per decade. These are inherited selected integration
stimuli, **not physical operating or reliability limits**. The inherited tap
comparison tolerances remain 1e-6 relative and 1e-10 V absolute.

A separate raw auditor reads the actual ASCII plots and requires complete
coordinates, finite complex response, the applied stimulus and current
conservation. It also reads the actual model/terminal/A/P identity, exact load,
analysis, temperature and electrical projection. Separate area +20%, perimeter
+20% and disconnected-input controls must produce the declared valid altered
response and differ from the nominal oracle. A malformed or incomplete run is
not a detected fault. The two tap models have identical equations; numerical
agreement cannot prove their names or body roles, so structural checks remain
mandatory.

```text
python scripts/qualify_ihp_tap_layouts.py --pilot --workers 2 --output NEW_PHYSICAL --magic MAGIC --netgen NETGEN --klayout KLAYOUT
python scripts/qualify_ihp_tap_linked.py --physical NEW_PHYSICAL --output NEW_LINKED --ngspice NGSPICE --osdi ORIGINAL_OSDI_DIRECTORY
python scripts/audit_ihp_tap_linked.py NEW_LINKED --output SEPARATE_AUDIT.json
```

Use new output directories and retain the source, tool, dependency and input
identities for each execution. This is local source integration, not installed
acceptance, independent physical calibration, continuous geometry or full-family
qualification. Chunk 7 remains approximately 74% complete, low confidence
55–82%; this subjective estimate does not increase with test counts.

## Evidence transport

The unchanged evidence ZIP is stored as two ordered byte parts to fit the upload
transport limit: [part 001](validation/artifacts/ihp-tap-linked-source-2026-11-11.zip.part001)
and [part 002](validation/artifacts/ihp-tap-linked-source-2026-11-11.zip.part002).
They are not individually readable ZIP archives. The execution record lists each
part's size and SHA256. Reassembly restores the original **14,054,394-byte** ZIP,
SHA256 `c7eac63a3ca21358e843969da348e6faac9574b813107cc979225f326ad8dd20`.
No evidence content or scientific result changes with this transport packaging.

From the repository root, save and run this snippet with Python (standard library
only). It verifies each part and the reconstructed bytes before creating the ZIP;
it refuses to overwrite an existing output file.

```python
from pathlib import Path
import hashlib
import json

base = Path("docs/validation")
evidence = json.loads((base / "ihp-tap-linked-2026-11-11.json").read_text())["evidence"]
chunks = []
for part in evidence["parts"]:
    chunk = (base / part["path"]).read_bytes()
    if len(chunk) != part["bytes"] or hashlib.sha256(chunk).hexdigest() != part["sha256"]:
        raise ValueError("Evidence part size/hash mismatch: " + part["path"])
    chunks.append(chunk)
data = b"".join(chunks)
if len(data) != evidence["bytes"] or hashlib.sha256(data).hexdigest() != evidence["sha256"]:
    raise ValueError("Reconstructed evidence size/hash mismatch")
with Path(evidence["reconstructed_filename"]).open("xb") as output:
    output.write(data)
print("Verified evidence ZIP:", evidence["reconstructed_filename"])
```
