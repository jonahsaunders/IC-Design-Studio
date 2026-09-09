# Current source release: 0.17.1

[UPDATE_0.17.1.md](UPDATE_0.17.1.md) documents dependency lookup and repair changes.
254 core tests and 11 Xschem GUI workflow checks passed on the Linux build host.
Windows discovery paths were covered through unit tests; the application was not
run on Windows. No 0.17.1 binary was built. The earlier binary remains 0.17.0.
The reported GF180MCUD schematic remains blocked by missing process assets and
unsupported native conversion of its embedded ngspice program.

[UPDATE_0.17.md](UPDATE_0.17.md) documents direct Xschem import, source-preserving export, supported constructs and limitations. [UPDATE_0.16.md](UPDATE_0.16.md) covers the broader design workflows. The verification archive distinguishes native tests, actual engine comparisons and environment-specific failures.

The 0.17.0 release supplied source and a Linux x86_64 standalone app. Offscreen Qt and build-host checks do not establish fresh-OS compatibility, physical-display usability or general process qualification.
