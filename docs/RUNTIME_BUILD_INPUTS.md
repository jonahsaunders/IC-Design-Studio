# Runtime build input identity

The runtime cache now hashes the actual staged build inputs rather than a list
of repository globs. The old list omitted inputs including IHP model compilation,
Verilog-A sources, GF180/IHP preparation helpers, source locks and verification
resources. A change to one of those files could otherwise reuse an older payload.

The cache and Docker build share `stage_context()` in
`scripts/build_digital_runtime.py`. Its identity records every staged file's
relative path, SHA-256 and file mode, together with the builder's own checksum.
Temporary directory names and timestamps are excluded. Symlinks and unexpected
nonregular objects are rejected. Generated Python bytecode caches are excluded
from staging; the current context contains 537 source files.

Before building, CI requires that the staged identity still matches the computed
cache key. Both new and restored payloads must contain the identical source
inventory and matching manifest identity. Native installation and all existing
qualification checks still run after a cache hit. This identifies local recipe
inputs; it does not make mutable external package repositories reproducible or
substitute for checks of the installed engines.

The [Linux openEMS dependency change](OPENEMS_BUILD_DEPENDENCIES.md) separately
avoids reinstalling heavy build prerequisites when the restored openEMS runtime
passes its existing integrity and native checks. This does not change the
digital-runtime cache identity or remove native/release acceptance.

The staging refactor preserves every nongenerated staged file, byte and file mode
on both Windows and Linux. One previously staged Python bytecode cache is omitted.
The focused packaging/runtime suite passes 48 tests
on each host, with nine Windows and two Linux platform-specific skips. These
checks do not claim that a new Docker image or final desktop package has passed.

Run the focused checks with:

```sh
python -m unittest tests.test_digital_build_cache tests.test_gf180_runtime_bundle tests.test_digital_bundle tests.test_digital_runtime -v
```
