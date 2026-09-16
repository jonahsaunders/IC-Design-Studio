# Third-party notices and corresponding source

The application code is GPL-3.0-or-later. Do not remove this source package, its build instructions, or these notices when distributing the application bundle. The desktop packages include ngspice, standard Xschem symbols and public GF180MCU primitive simulation assets. Physical rule decks and Magic/Netgen engines are separate.

| Component | Version | License / corresponding source |
|---|---|---|
| Qt / PySide6 / Shiboken | 6.8.3 | LGPL-3.0 and component-specific licenses; https://download.qt.io/official_releases/QtForPython/pyside6/PySide6-6.8.3-src/ and https://download.qt.io/archive/qt/6.8/6.8.3/ |
| KLayout | 0.30.5 | GPL-2.0-or-later; https://github.com/KLayout/klayout/tree/v0.30.5 and https://www.klayout.de/ |
| PyInstaller bootloader | 6.16.0 | GPL with distribution exception; https://github.com/pyinstaller/pyinstaller/tree/v6.16.0 |
| Python runtime | 3.12 | Python Software Foundation license; https://www.python.org/downloads/source/ |
| cryptography | 50.0.1 | Apache-2.0 OR BSD-3-Clause; https://github.com/pyca/cryptography/tree/50.0.1 |

Exact wheel requirements are in requirements.txt. Dynamic Qt libraries can be replaced by compatible, modified libraries; no anti-modification restriction is added. The application source and build scripts are supplied. Standard Linux graphics/runtime libraries may be collected by the packager; their distribution copyright notices are included under licenses/system when collected. They retain their original licenses. Source locations for Ubuntu packages are https://packages.ubuntu.com/noble/ and https://archive.ubuntu.com/ubuntu/pool/; exact library filenames are visible in the binary bundle.

Review licenses and provide continuing equivalent access to complete corresponding source for the versions you distribute before a public/commercial release. This delivery has not completed the blueprint's independent legal/compliance release review.

## VGA Playground

The digital VGA preview uses Tiny Tapeout VGA Playground at commit
`3e3c77e46ae7bd51609f680851aabb81a30564a6` (GPL-3.0), including its
8bitworkshop-derived simulator. The native-editor adapter is part of Studio's
GPL-3.0-or-later source. Upstream: https://github.com/TinyTapeout/vga-playground/tree/3e3c77e46ae7bd51609f680851aabb81a30564a6.
The preset Verilog retains its Apache-2.0 headers and license texts; common
modules retain their separate upstream notices.

The build includes adapted upstream sources in `vga-playground-source.zip`,
the GPL text and dependency notices under the preview's `licenses/` directory.
It uses the upstream-provided Verilator WebAssembly artifact; Verilator is
LGPL-3.0 OR Artistic-2.0 (https://github.com/verilator/verilator). Binaryen is
Apache-2.0 (https://github.com/WebAssembly/binaryen); dependency versions are
recorded in the included upstream package-lock.json. Qt WebEngine/Chromium
component licenses and corresponding sources are supplied by the matching Qt
6.8.3 distribution linked above. The upstream WASM compiler's complete build
provenance is not established by the Studio adapter; retain the upstream source
and component notices when redistributing it.

## Optional SKY130 reference evidence

The separately supplied SKY130 reference bundle contains a subset of the SkyWater open PDK and generated derivatives of its inverter. Copyright 2020 The SkyWater PDK Authors and other notices retained in the original files. These assets are distributed under Apache-2.0; see licenses/Apache-2.0.txt and their file headers. The app's reference fetch script points to the pinned upstream Volare distribution. Magic and Netgen used for verification are external tools. ngspice is included in the 0.18 desktop packages.

## Included Xschem and GF180 simulation assets

Standard Xschem symbols: Ubuntu 3.4.4-1build1, GPL-2.0-or-later. Original copyright and license headers are retained under icstudio/assets/exchange/xschem; the GPL text is in licenses/GPL-2.0.txt. Corresponding source: https://archive.ubuntu.com/ubuntu/pool/universe/x/xschem/ and https://github.com/StefanSchippers/xschem/tree/3.4.4.

GF180MCU primitive symbols and ngspice model files: Apache-2.0, upstream commit 4d0b4cef59c7686fac5fd3f4c6fb41d251d1f90c. Source: https://github.com/fossi-foundation/globalfoundries-pdk-libs-gf180mcu_fd_pr/tree/4d0b4cef59c7686fac5fd3f4c6fb41d251d1f90c. Original files and license accompany the application; assets/exchange/index.json records individual hashes and source paths. These are schematic and simulation assets, not physical signoff decks.

ngspice 42: BSD-style and component-specific licenses retained in the runtime COPYING/copyright files. Windows console distribution: https://sourceforge.net/projects/ngspice/files/ng-spice-rework/old-releases/42/ngspice-42_64.7z/download. Linux distribution: Ubuntu 42+ds-3build1; corresponding source: https://archive.ubuntu.com/ubuntu/pool/universe/n/ngspice/. Upstream source: https://sourceforge.net/projects/ngspice/files/ng-spice-rework/old-releases/42/.

The Windows portable package uses CPython 3.12.9, official win_amd64 and pure Python wheels for the runtime dependencies, and Distlib native launchers distributed by pip 25.0.1. Runtime archive and file hashes are recorded in runtime-manifest.json. Python and Distlib licenses accompany those components. Distlib source: https://github.com/pypa/distlib. The application itself is supplied as editable Python source in the app folder.

Encrypted desktop hosting uses cryptography to generate its private host certificates. Its wheel includes OpenSSL and other components with their own notices. The frozen packager retains cryptography's distribution metadata and license directory, including its bundled-component notices, and dependency metadata. The portable assembler retains the complete wheel metadata and licenses, including CFFI and pycparser. Corresponding upstream sources: https://github.com/openssl/openssl, https://github.com/python-cffi/cffi and https://github.com/eliben/pycparser; the bundled metadata identifies their versions and licenses.

## Added bundled simulation PDKs in 0.22.0.dev10

SKY130A primitive models, symbols and display layers are extracted from the checksum-pinned `common.tar.zst` and `sky130_fd_pr.tar.zst` assets of https://github.com/chipfoundry/volare/releases/tag/sky130-fa87f8f4bbcc7255b6f0c0fb506960f531ae2392. Upstream headers and Apache-2.0/model and symbol license files are retained in `icstudio/assets/pdks/sky130A`. The bundled package includes only the primitive model include closure, primitive symbols and display map. Standard-cell libraries and physical verification decks are excluded.

The GF180MCU D adapter reuses the existing pinned primitive files above, adds `.ngspice` compatibility aliases, and includes `tech/klayout/gf180mcu.lyp` from the same upstream revision. Original Apache-2.0 headers and license are retained. Each package records source provenance in `UPSTREAM-LOCK.json` and locks every distributed asset in `package.json`.

The Windows source/build provisioner uses py7zr 1.1.3 (LGPL-2.1-or-later), https://github.com/miurahr/py7zr/tree/v1.1.3, installed by pip with its dependencies. It is a setup dependency; the prepared portable desktop does not require it. The portable desktop retains the original Python license and the license files from the pinned PySide6, Shiboken, KLayout and cryptography wheels.

## Optional overvoltage qualification source

The external regression downloads LDFranck/sky130_vbl_ip__overvoltage at commit `53cf579f63d34227af67f0189b49ee09185f1db5`, an Apache-2.0 design by the Von Braun Labs contributors identified upstream. The source lock includes its LICENSE checksum. The design itself is not bundled. Generated evidence and screenshots derived from it retain this attribution. See [the reproduction guide](docs/OPEN_PROJECTS.md).

## SKY130 resistor extraction backport in dev20

The resistor definition block in [the correction lock](examples/open-projects/sky130-resistor-extraction.json) is from open_pdks commit `1689ac3f2dc763876eaf967227c7dfe831b031ae`, `sky130/magic/sky130.tech`. Copyright (c) 2020 R. Timothy Edwards; Apache-2.0. Its [license](examples/open-projects/LICENSE-open_pdks.txt), source URL and source hash are retained. The generated deck explicitly marks the backport; the full PDK is not bundled.

## Included openEMS runtime

The qualified Windows/Linux desktop packages include a separate openEMS 0.0.36
runtime. openEMS is GPL-3.0-or-later; CSXCAD is LGPL-3.0-or-later; fparser retains
its LGPL notices. Exact corresponding project/submodule source accompanies the
runtime in `licenses/openEMS-corresponding-source.zip`, including the Linux
VTK 9 CMake compatibility changes. The project revision is
`d0d2e8dad8a02388f1919bbcdd29a67e9199dd2c`:
https://github.com/thliebig/openEMS-Project/tree/d0d2e8dad8a02388f1919bbcdd29a67e9199dd2c.
Windows uses the checksum-pinned official openEMS 0.0.36 archive. Linux builds
without AppCSXCAD or MPI; its native dependency closure excludes glibc and retains
Ubuntu package copyright files and exact versions under `licenses/system`.

The separate CPython 3.11.16 distribution comes from python-build-standalone
release 20260901 (PSF and component-specific licenses):
https://github.com/astral-sh/python-build-standalone/releases/tag/20260901.
Original Python and dependency license files are retained. NumPy 1.23.5 (BSD),
Matplotlib 3.7.5 (Matplotlib license), h5py 3.10.0 (BSD) and their pinned dependencies
retain their wheel metadata/license files. Their upstream sources are
https://github.com/numpy/numpy/tree/v1.23.5,
https://github.com/matplotlib/matplotlib/tree/v3.7.5 and
https://github.com/h5py/h5py/tree/3.10.0.
The runtime's `runtime.json` records archive hashes, wheel hashes, packages and
individual file integrity; `scripts/stage_openems.py` reproduces the runtime.
This does not add an anti-modification restriction to any component. Retain
notices and equivalent source access when redistributing dependencies.

## Included digital tools

Desktop release packaging includes a private Linux runtime (also used by the
Windows app's private WSL distribution). The original OSS CAD Suite licenses are
under `opt/icstudio/oss-cad-suite/license`; Ubuntu package copyright files are
under `usr/share/doc`. `opt/icstudio/packages.tsv` records exact binary/source
package versions, and the runtime manifest records the suite, OpenROAD and ORFS
revisions. The reproducible engine download checksums and wrapper source are in
`packaging/digital`. Their source and licenses are available upstream:

- Icarus Verilog: GPL-2.0-or-later, https://github.com/steveicarus/iverilog
- Verilator: LGPL-3.0 or Artistic-2.0, https://verilator.org/guide/latest/copyright.html
- Yosys: ISC, https://github.com/YosysHQ/yosys
- EQY: ISC, https://github.com/YosysHQ/eqy
- SBY: ISC, https://github.com/YosysHQ/sby
- Bitwuzla: MIT, https://github.com/bitwuzla/bitwuzla
- KLayout: GPL-2.0-or-later, https://github.com/KLayout/klayout
- GNU GCC and GNU make: https://www.gnu.org/software/gcc/ and
  https://www.gnu.org/software/make/ (retain package-specific license notices)
- OpenSTA: GPL-3.0, https://github.com/The-OpenROAD-Project/OpenSTA
- OpenROAD / OpenROAD Flow Scripts: BSD-3-Clause for
  the main projects, with separately licensed dependencies and platform assets,
  https://github.com/The-OpenROAD-Project/OpenROAD-flow-scripts

The complete OSS CAD Suite distribution, including its dependency notices and
package inventory, comes from
https://github.com/YosysHQ/oss-cad-suite-build/releases/tag/2026-09-13.
Its upstream build recipes are at https://github.com/YosysHQ/oss-cad-suite-build.
Ubuntu source packages are available from https://archive.ubuntu.com/ubuntu/;
use the source package/version columns of `packages.tsv` to identify them.
Retain component notices and equivalent corresponding-source access when
redistributing the runtime. Generated Studio examples, installer and configuration
templates are part of this application's source distribution.

Digital platform inputs retain their own licenses. CI downloads separately licensed
engine distributions and records their versions; these binaries and full PDK trees
are not included in the application source distribution.
