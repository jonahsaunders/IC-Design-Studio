# Selected installed SKY130 resistor acceptance

The immutable `docs/qualification/sky130-metal-installed-v1.json` defines a
finite installed-workflow milestone within chunk 7. Its original equations,
model source identities, operating samples and numerical tolerances are those
of `sky130-metal-resistors-linked-v1.json`. Neither contract qualifies an entire
device family or supplies missing foundry operating limits.

## Completion evidence

One selected clean commit must pass the full desktop workflow on Windows and
Linux, including the existing release gates. Windows exercises the executable
from the actual installer before uninstalling it; Linux exercises the frozen
distribution executable. A source pilot cannot satisfy either installed gate.

The new workflow has two independently checked stages and an aggregate receipt:

1. `verify_frozen_metal_resistors.py` launches the application's
   `--metal-resistor-acceptance` entry point. Real Qt editor actions create five
   resistor models, three geometries and two rotations: **30 layouts**. The
   application saves and reopens projects, exports schematic/reference/GDS
   files, checks pin and geometry changes, and queues fresh native DRC and LVS.
   It also exercises historical/current package bindings for all five models.
2. `qualify_installed_sky130_metal_resistors.py` consumes the **24 M1–M4
   references and fresh extractions** from that exact GUI execution. The full
   selection runs **90 simulator batches**, covering 720 conditions for each
   of DC, AC and transient analysis, plus 120 noise conditions. The original
   geometric, model, multiplicity, terminal and operating-context controls
   remain required. An independent auditor reads the actual decks, logs and
   raw samples and compares them to the fixed analytical expectations.
3. `verify_installed_metal_resistors.py` reruns independent electrical readback
   and binds both stages to the selected commit, GUI execution, executable,
   packages and exact input files. Its receipt reports only
   `installed_selected_workflow_acceptance`, keeping full qualification,
   chunk completion, release readiness and signoff false.

The GUI stage requires **43 separate queued jobs**: 30 clean layouts, five
width/LVS faults, five fresh repairs, one DRC defect, one fresh repair and one
missing-engine preflight rejection. Forty-two jobs execute native tools. Each
job retains its original project identity, engine stages and raw output.

## Preserving the actual exported devices

The electrical stage retains the original application and extracted netlists.
Positive devices are not regenerated from catalog parameters. The only
normalization changes the unique subcircuit top name to `coupon`; exact byte
spans, original files and both hashes are retained and independently checked.
Three-device multiplicity uses three copies of the same received subcircuit.
The fault controls mutate separate copies with one explicit parameter, model
or terminal change and retain the mutation proof.

Simulator selection is fixed by the installed application and the contract's
platform-specific binary digest. Installed acceptance cannot substitute a
simulator from PATH or a developer override. Model packages, runtime assets,
source files and inputs are checked before and after execution. Original
engine source references retain their upstream copyright and license notices.

The context hash uses a portable absolute file-URI path (`/C:/...` on Windows)
and a fresh nonce. Actual commands and working directories retain their native
platform paths. This representation changes no simulator input, output path or
physical unit.

## Running a selected candidate

Use the existing `build-desktop.yml` workflow with the exact forty-character
candidate commit. The Linux gate calls are:

```sh
python scripts/verify_frozen_metal_resistors.py \
  --executable dist/ICDesignStudio/ICDesignStudio \
  --physical-pdk build/physical-adapter/sky130A \
  --expected-commit "$ICSTUDIO_EXPECTED_COMMIT" \
  --timeout 2400 --out build/frozen-metal-resistor-evidence
python scripts/qualify_installed_sky130_metal_resistors.py \
  --gui-root build/frozen-metal-resistor-evidence \
  --expected-commit "$ICSTUDIO_EXPECTED_COMMIT" \
  --out build/frozen-metal-resistor-electrical-evidence
python scripts/verify_installed_metal_resistors.py \
  --gui build/frozen-metal-resistor-evidence \
  --electrical build/frozen-metal-resistor-electrical-evidence \
  --expected-commit "$ICSTUDIO_EXPECTED_COMMIT" \
  --out build/frozen-metal-resistor-workflow-evidence/acceptance.json
```

`verify_windows.ps1` runs the equivalent stages against `Installed App With
Spaces` and includes the aggregate in `windows-release.json`. Each execution
requires fresh output paths. Failed attempts are retained separately; a retry
does not relabel old output as fresh evidence.

Everyday PR feedback runs boundary and independent checker tests plus the
existing five-model editor smoke test. Full core discovery retains the
thirty-layout Qt lifecycle test. Release acceptance always executes fresh
native jobs and the full electrical selection.

## Remaining qualification limits

LI has selected editor/native-layout coverage here; its electrical qualification
is a separate track. M1–M4 results concern the sampled public compact models,
not measured silicon accuracy. Successful installed execution does not close
unsampled geometries, full operating envelopes, statistics, reliability,
upstream omissions or other PDK families. The authoritative chunk-7 state
remains in `QUALIFICATION_PROGRESS.md` and `qualification/pdk-matrix.json`.
