# Retained IHP PMOS v3 research evidence

All 20 original jobs completed: 560 native points, including 140 nominal measured-comparison points. No refinement, KLU, tolerance change or model coefficient change was used. The signed-zero-safe compensated RHS module was explicitly enabled in a separate compiler build. It is NOT the managed/default application runtime.

The original multiplicity audit REJECTED total-current 2x scaling. That historical result is preserved. A separately named source-aware consistency check accounts for the exact PSP gmin branch, which is not multiplied by model MULT. It passes under the original tolerances. No offset is subtracted from measured-data comparisons. Neither result establishes calibration, device qualification or installed acceptance.

## Portable readback (no simulation)

From repository root, choose a fresh evidence directory and a fresh output outside it:

    python scripts/materialize_ihp_pmos_measured_v3.py docs/qualification/ihp-pmos-measured-reference-v3/evidence-compact.zip packaging/ngspice/ngspice-linux47-corrected-v1.zip /tmp/ihp-v3-evidence
    python scripts/read_ihp_pmos_measured_v3.py /tmp/ihp-v3-evidence --output /tmp/ihp-v3-readback.json
    python -m unittest tests.test_ihp_pmos_measured_v3_readback

On Windows use equivalent fresh local paths. The reader never opens historical workspace paths or executes native binaries. It authenticates all 588 retained files before executing the exact reviewed Python raw/measurement reader definitions. Original absolute paths are checked only as historical invocation strings. Those readers use only current-host Python standard-library modules: argparse, bisect, hashlib, json, math, pathlib, re and decimal. The Python runtime itself is not a pinned native replay environment.

The 9,573,946-byte compact transport reconstructs every payload from the complete 44,389,077-byte archive, reusing exact files from the existing pinned engine archive and deduplicating identical payloads. No native raw files, logs, decks, original runtime/measurement/model records or independent reviews are omitted. Only 11 generated Python bytecode files were excluded; their sources are retained. The complete archive identity and manifest are recorded in full-evidence-receipt.json.

## Compiler reproducibility limits

compiler-complete.patch applies cleanly to pinned compiler f47d5579bd2f5c465f6e7db62c12745daad8b54f and reproduces all 734 candidate source identities. Reconstructed evidence includes full candidate source archive, Cargo.lock, licenses, actual build scripts/commands, toolchain acquisition/build receipts and the source-bound UCRT wrapper.

Large LLVM source/build/install trees, Debian sysroot/packages, Cargo cache, compiler executables and failed build trees are explicitly NOT bundled. Reconstituting the pinned toolchain is necessary for executable rebuild; this is NOT a turnkey build or fresh runtime qualification. See COMPILER-REPRODUCIBILITY.txt and reconstructed measured-v3/compiler-reproducibility/.

Historical v1/v2 contracts, failed attempts and the original rejected v3 audit remain unchanged. This adapter only reads evidence; it does not install a compiler, replace a managed runtime or run a new batch.

See LICENSE-ATTRIBUTION-INDEX.json for original PDK/PSP/ngspice/compiler notices and corresponding-source locations.
