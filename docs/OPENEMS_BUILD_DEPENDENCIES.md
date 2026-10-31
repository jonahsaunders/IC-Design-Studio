# Reusing verified openEMS build output

The Linux desktop job now installs five openEMS development packages only when
the restored runtime fails the existing `stage_openems.py --verify` check.
Verification requires the pinned recipe metadata, every recorded file hash and
successful native geometry/port API checks. A cache name or cache-hit flag alone
is insufficient. This preparation check does not run a field solve; the separate
native solver acceptance step still does.

If verification fails, the job installs `libhdf5-dev`, `libvtk9-dev`,
`libboost-all-dev`, `libcgal-dev` and `libtinyxml-dev`, then runs the unchanged
preparation and native solver steps. Simulation and desktop runtime packages,
the compiler and CMake remain unconditional. No release gate is removed.

The previous Linux dependency step downloaded 428 MB in 1 hour 46 minutes 11
seconds. That observed delay motivates avoiding unnecessary build dependencies;
it does not establish a measured speedup for the new workflow. The active
`e3fa0cc` desktop acceptance uses the earlier workflow.

Seven actual Bash control-flow checks with isolated command stubs pass: verified,
missing and changed caches; package-index and package-install failures; runtime
preparation failure; and native-probe failure. The verified branch skips package
installation, while each required failure propagates. These checks test command
selection and error handling; they do not substitute for the next real hosted
runtime acceptance. All original workflow bytes outside the two declared
dependency changes are preserved.

The [execution record](validation/openems-build-dependencies-2026-10-26.json)
retains the original timing evidence, exact workflow hashes and control results.
