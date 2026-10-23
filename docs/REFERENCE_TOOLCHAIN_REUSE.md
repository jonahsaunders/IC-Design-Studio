# Shared reference qualification toolchain

The reference compatibility workflow builds its patched GF180 RC extractor and
the pinned KLU-enabled ngspice once per acceptance run. Five independent corner
jobs consume the same verified installed binaries. This changes ten engine
builds into two; each corner still performs its complete extraction, terminal
equivalence, fill fault controls and post-RC startup checks.

The producer packages only the installed prefixes, upstream licenses, source
locks, build logs and version logs. Its manifest binds every file's bytes and
mode (or relative symlink target) to the full checked-out candidate SHA, absolute
installation prefix, runner image version, architecture, build script, workflow,
requirements, source locks and patch bytes. The producer job passes the archive
SHA-256 separately as a job output. Each corner checks that digest before
extracting, rejects a different candidate or build input, validates the restored
inventory and probes the engines' versions and KLU support before qualification.
Archive traversal, duplicate members and external symlinks are rejected.
Ordinary permissions, including group-writable files and non-default directory
modes, are restored exactly after archive/manifest validation. Setuid, setgid and
sticky permission bits are rejected. Symlink permissions are never applied to
their targets, and archive members beneath symlinks are rejected before writing.

The archive is an artifact of that workflow run, not a cross-run cache. Failed
build logs remain separate artifacts. All previous per-corner result directories
and engine logs remain in their existing acceptance artifacts; the restored
manifest, engine probes and host package inventory are added alongside them.

Consumers still install runtime libraries and Python dependencies. The latter
use the standard download cache keyed by the locked requirements; installation
and qualification still run. The runtime package repository is not pinned, so
this is not a hermetic environment. Both producer and consumer retain installed
package inventories, and a changed hosted runner image causes restoration to
fail. Rebuilding for the new image is preferable to silently using incompatible
binaries. The installed prefixes must have the same absolute workspace path,
because the upstream tools can embed that path.
The hosted runner's `ImageOS` and `ImageVersion` must both be present; an ordinary
local environment with missing image identity cannot produce or restore this CI
artifact.

Producer and corner setup use copies of the runner's APT source definitions.
Only the known Azure Ubuntu archive URI and the hosted image's
`mirror+file:/etc/apt/apt-mirrors.txt` reference are replaced with the official
HTTPS Ubuntu archive. Suites, components, signing-key settings and other
repositories are preserved; system source files are not edited. This avoids the
observed slow Azure download route, while retaining APT signature and package
hash verification. It is not a package-version pin or a guarantee of availability.
The [hosted image configuration](https://github.com/actions/runner-images/blob/main/images/ubuntu/scripts/build/configure-apt-sources.sh)
documents that mirror-list form.

APT index refresh and package installation have total limits of five and ten
minutes, in addition to connection timeouts and the existing step limit. Each
command must succeed. The timeout process runs with the same hosted-runner
privileges as APT so it can terminate stalled child processes. Setup logs, selected
source definitions, original/selected source hashes and package inventories are
retained even on ordinary setup failures. These limits fail a stalled setup
explicitly; they never turn a missing dependency into successful acceptance.

Routine PR and merge-queue checks use the fast workflow. Exhaustive reference
acceptance runs for selected manual candidates, version tags or release workflow
calls. A manual run requires the full SHA matching the selected branch or tag;
the candidate guard rejects stale inputs before expensive setup. Existing release
acceptance requirements and all five independent corner checks remain in force.

Focused checks:

```sh
python -m unittest tests.test_reference_toolchain tests.test_physical_engine_build -v
```

The first [hosted trial, run 40021382276](https://github.com/jonahsaunders/IC-Design-Studio/actions/runs/40021382276),
at candidate `43a04bb00af3118fe97d3d177ec73599056027b6`, failed before either
shared engine built: Azure package downloads exhausted the producer's 20-minute
setup limit. The five dependent corners were skipped. The modern schematic,
bandgap schematic and bandgap physical jobs passed independently. This failure
motivated the scoped archive selection and earlier setup logging above; it does
not validate artifact reuse. The [validation record](validation/reference-toolchain-reuse-2026-10-23.json)
binds the failed trial, fixed sources, focused tests and offline setup probes to
retained logs and a verified compact evidence archive. Local fault probes confirm
that both package errors and total timeouts remain failures, stop later setup and
retain diagnostics for the producer and consumer scripts.

Local transfer/failure-control tests do not establish a successful hosted build
or measure the resulting CI latency. The next selected acceptance run must
verify the actual producer build, five artifact restores and full native corner
results. Compare setup time, first useful failure and queue time against the
previous workflow; do not infer a device qualification improvement from reuse.
