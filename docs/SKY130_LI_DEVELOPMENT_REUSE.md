# Selected LI physical development reuse

This opt-in pilot reuses **one complete `l1-w2-l5` physical case** after an
independent audit of its original native outputs. That unit contains both 0°
and 90° layouts, full native DRC, strict LVS, stream exchange, and all five
terminal/reference fault controls. It does not reuse isolated successful stages.
It does not qualify the full LI family, electrical behavior, an operating
envelope, installed deliverables or a release. See the
[family closure plan](CHUNK7_DEVICE_FAMILY_CLOSURE.md).

The default runner and exhaustive/release callers still execute fresh.
`--select` and `--resume-from` without `--development` are errors. Unknown,
empty or duplicate selections fail before native tools or output creation.
Every invocation requires a new output directory. The development report lists
the selected case and the complete 30-case exhaustive list separately, with
`qualified`, `chunk_complete` and `release_acceptance` all false.

## Supported runtime and usage

The first profile is deliberately narrow: Linux x86_64, Python 3.12, and the
reviewed IC Studio headless Magic/Netgen installation under `/opt/icstudio`.
Other platforms, launcher paths or changed native/Tcl installations are rejected
for reuse. They can still use the existing fresh runner. This is not a generic
cache for arbitrary system tool installations.

Use the locked physical adapter accepted by
`examples/sky130-qualification-lock.json`. Start Python with a deterministic
hash seed and disabled user-site imports; changing these variables inside an
already running interpreter is insufficient:

```sh
PYTHONHASHSEED=0 PYTHONNOUSERSITE=1 python3.12 -B \
  -X pycache_prefix=/__icstudio_li_development_no_bytecode__ \
  scripts/qualify_sky130_metal_resistor_layouts.py \
  --development --select l1-w2-l5 \
  --sky130 /path/to/locked-physical-adapter \
  --magic /opt/icstudio/bin/magic --netgen /opt/icstudio/bin/netgen \
  --output /path/to/new-original-run

PYTHONHASHSEED=0 PYTHONNOUSERSITE=1 python3.12 -B \
  -X pycache_prefix=/__icstudio_li_development_no_bytecode__ \
  scripts/qualify_sky130_metal_resistor_layouts.py \
  --development --select l1-w2-l5 \
  --sky130 /path/to/locked-physical-adapter \
  --magic /opt/icstudio/bin/magic --netgen /opt/icstudio/bin/netgen \
  --resume-from /path/to/new-original-run \
  --output /path/to/new-reuse-validation
```

Resume from the **original execution directory**. A reuse-validation directory
contains a reference to the original; it is not a new execution and cannot
serve as a substitute original. Chained aliasing, moved originals and evidence
symlinks are rejected. Nothing rewrites the original case or its timestamps.
Missing, failed, interrupted, incompatible or corrupt prior evidence produces
a recorded miss and fresh execution in the new output directory.

## Input and output identity

The input key includes the case's parameters, all orientations/faults, exact
geometry thresholds, all Python files under `icstudio`, `scripts` and `tests`,
application assets, top-level example JSON/project fixtures and locks, and
requirements files. All physical adapter files are inventoried in addition to
the package's existing lock checks. This case performs no simulation and uses
no simulation PDK; its report states that explicitly. Unrelated Markdown edits
do not change the key. An uncommitted helper change does.

Runtime checks inventory complete Python standard-library and import/package
roots, the native installation and Tcl roots, Python flags and actual imported
ELF mappings. ELF dependencies of the mapped Python extensions, native Magic
and Netgen Tcl extensions, interpreter and shell helpers are resolved under the
effective library search path and hashed. The reviewed launchers and native
Tcl installation have additional fixed hashes: changed scripts/binaries could
open new dependencies that `ldd` cannot enumerate, so they require a profile
review before reuse. This is an inspected, pinned headless dependency profile,
not a general syscall trace or a claim that all Linux toolchains are supported.

Native subprocesses receive a small fixed environment, with an absent-home
sentinel preventing user startup files. Python must also start with the explicit
absent bytecode-prefix sentinel above: `-B` alone disables bytecode writes but
does not prevent loading a stale project `.pyc`. The before/after identity check includes
OS/architecture, effective environment, runtime files, PDK and source inputs.
An input changed during a run prevents terminal receipt publication. A narrow
frozen source copy can carry `.qualification-source.json`; its original commit
and complete source manifest must match the copy exactly. This avoids holding
up unrelated development without relabeling the source revision.

The original execution retains `inputs.json`, a complete `case-manifest.json`,
`receipt.json`, the original source hashes/commit, run ID and native execution
times. The terminal receipt is published only after the case passes, the raw
audit passes and input identities remain unchanged. Reuse verifies every output
and reruns the independent auditor. A missing required output remains a failure
even if its entry has been removed from a rewritten manifest.

The auditor reads the actual GDS/OASIS streams and saved projects, checks the
literal sampled LI marker/conductor geometry and terminal anchors, and parses
the actual extracted SPICE. It checks native full-DRC completion/counts and
strict LVS diagnostics, plus the particular native symptom for each fault.
It also checks the complete fixed-case generator, startup, DRC and extraction
scripts, recorded extraction settings, and the actual Netgen input/setup and
output paths. Native preflight/integrity asset and tool hashes must match the
captured execution identity. Independent review found five missing script/setup
bindings in the first version; all five now have retained rehashed-evidence
rejection controls.
Rehashing wrong geometry, a wrong model, a missing terminal or a non-detected
fault does not make that evidence acceptable. The existing fixture uses
ordinary-purpose LI top labels selected by its explicit two-terminal reference;
the audit does not relabel them as pin-purpose evidence.

## Performance and limits

Separate native execution, identity checks and reuse audit time in
`qualification.json`. Broad runtime hashing is deliberately conservative and
can cost more than this small native case. The initial work-in-progress native
case took about 4.6 seconds, while before/after runtime identity checks took
about 21 seconds. Therefore this pilot must not be advertised as faster than
the original unkeyed fresh 2 × 5 case. It establishes a safe unit of reuse and
measures its overhead; narrowing the runtime closure or applying it to longer
suites needs a separate reviewed change. Release acceptance remains fresh.

The [October 23 validation record](validation/sky130-li-development-reuse-2026-10-23.json)
retains the final reviewed source, original execution and reuse identities.
That keyed fresh run took **13.87 seconds**, including **4.52 seconds** of
native execution. Its reuse validation took **9.36 seconds**, with
**0.184 seconds** spent checking/auditing original evidence and no new native
execution. These invocations include different filesystem-cache conditions
and do not establish an overall CI speedup. Twenty-one retained input,
semantic and publication controls pass. An independent reviewer separately
confirmed the five script/setup mutations are rejected and original evidence
is unchanged. The affected regression set passes **23 tests** on each of
Windows and Linux. Windows test success does not enable Windows native reuse;
the runtime profile remains Linux-only.

Focused protocol and semantic tests run with:

```sh
python -m unittest tests.test_sky130_li_resume -v
```

Tests of receipt publication use explicit protocol fixtures. Native acceptance
must additionally retain an actual complete miss → hit run and private-copy
corruption controls; mocked protocol tests are not native qualification.
