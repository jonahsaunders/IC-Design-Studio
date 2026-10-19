# Third-party notices and corresponding source

The application code is GPL-3.0-or-later. Do not remove this source package, its build instructions, or these notices when distributing the application bundle. Complete desktop builds include ngspice, standard Xschem symbols, SKY130/GF180MCU/IHP primitive simulation subsets and the runtimes described below. The managed Linux/private WSL runtime includes Magic and Netgen for Studio's physical verification jobs and compiled IHP OSDI models. GF180 C/D and IHP packages include matching analog physical rule decks; SKY130 analog physical assets remain separate. The source checkout does not include the generated runtime binaries.

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

The separately supplied SKY130 reference bundle contains a subset of the SkyWater open PDK and generated derivatives of its inverter. Copyright 2020 The SkyWater PDK Authors and other notices retained in the original files. These assets are distributed under Apache-2.0; see licenses/Apache-2.0.txt and their file headers. The app's reference fetch script points to the pinned upstream Volare distribution. Verification can use configured external Magic/Netgen or the managed runtime described under Included digital tools below; that runtime does not supply this separate analog reference PDK.

The optional `scripts/prepare_sky130_digital.py` preparer selects standard-cell
timing, LEF/GDS/CDL and OpenRCX collateral from the same checksum-pinned
`sky130-fa87f8f4bbcc7255b6f0c0fb506960f531ae2392` Volare release. It retains original
file headers, copies the Apache-2.0 text, and records archive/source-file hashes in
`pvt/upstream-lock.json`. The original ORFS configuration is retained alongside
the generated physical-view adapter; ORFS notices and license requirements here
continue to apply. Full PDK trees and generated platforms are not committed to the
application source package.

The test fixture `tests/fixtures/sky130-filled-references-v1.zip` contains three
generated counter/UART/APB layouts incorporating the SKY130 HD standard cells,
independent pin/die inventories and the pinned public SKY130 rule sources.
SkyWater content retains its Apache-2.0 license in `sources/LICENSE`, original
source notices and source-lock identities. It is reference verification data,
not a complete PDK or native runtime. The application/design sources and their
existing notices remain in this repository. The fixture is not distributed as
foundry-qualified signoff data.

The digital runtime build also copies the fixture's pinned public rule sources
and `sources/LICENSE` into the SKY130 HD verification resources. The reference
layouts are not copied into those resources. The retained Apache-2.0 terms and
original file notices apply to these manual sources as well.

The verbatim F2a device and F2b mask tables in
`docs/qualification/sky130-device-tables` come from SkyWater open PDK revision
`7198cf647113f56041e02abf3eb623692820c5e1`. Their Apache-2.0 license is retained
alongside the tables. The device-intent audit records the original source URLs,
Git blob identities and SHA-256 hashes.

## Public device-qualification sources

The unmodified NPN corner sources and model in
`icstudio/assets/qualification/sky130-npn` come from
`google/skywater-pdk-libs-sky130_fd_pr` revision
`f62031a1be9aefe902d6d54cddd6f59b57627436`, under Apache-2.0.
Copyright 2020 The SkyWater PDK Authors. Their full license, original headers
and source hashes accompany the files. The bipolar qualification preparer
retains these sources and notices in its output and identifies its adaptation:
copying corner parameters into named sections while omitting redundant model
include lines. Existing bundled NPN model bytes are unchanged.

The separate SKY130 resistor and IHP MIM qualification preparers modify the
already bundled Apache-2.0 sources. Their output files identify the local
modifications, retain original notices and license files, and record original
and resulting identities. These generated packages are separately versioned;
they do not replace the source provenance or relicense upstream content.

## Public SKY130 metal-density reference

The public SKY130 oxide-density measurements are adapted from Tiny Tapeout 10's
`sky130_tapeout_drc/met_density_tiled.drc` at revision
`46f0a2f45c3b1fcc27aac7acb7faa054631d9955`, under Apache-2.0. The original source
includes DLindley's July and September 2024 attribution. Source:
https://github.com/TinyTapeout/tinytapeout-10/blob/46f0a2f45c3b1fcc27aac7acb7faa054631d9955/sky130_tapeout_drc/met_density_tiled.drc.
The exact upstream source, license and hashes are retained in
`tests/fixtures/sky130-tt-density-v1` and, for the mandatory application gate,
`icstudio/assets/verification/sky130/density`. Each new density result and macro
export retains the original source, license and source lock. The distribution's Apache-2.0 text is
`licenses/Apache-2.0.txt`. Studio's 2026-10-15 adaptation uses integer areas,
explicit physical units and declared bounds, includes endpoint windows, and
separates clipped diagnostics. These changes do not claim foundry equivalence.

## Public SKY130 deck comparison sources

`tests/fixtures/sky130-public-decks-v1` retains unmodified `sky130A_mr.drc`
sources from Tiny Tapeout `tt-support-tools` revision
`01d5d2814fa9dd61e9d211e0b235a4a592a9316a` and ChipFoundry `cf-precheck`
revision `6c401ed5134a6466c7eed3e5524ebaacad4cea2a`.
Their explicit GNU GPLv3 file headers apply; their repositories' Apache-2.0
root licenses do not relicense these decks. No later-version grant is
inferred. Original headers, exact source locations and hashes, provenance
links, and the full GPLv3 license accompany the files in the fixture directory.
The same unmodified ChipFoundry deck and its GPLv3 text are also retained in
`icstudio/assets/verification/sky130` for the generic local Finish check and
included in exported evidence. Its upstream filters and selected options are
recorded explicitly; this check does not establish full foundry signoff.
Studio's added runners, rule-name inventory and regression tests remain
GPL-3.0-or-later. The GPLv3-only deck retains that license rather than acquiring
the application's later-version grant.

The associated validation archive retains the same GPLv3 sources and license,
new control layouts and driver source, and the counter/UART/APB layouts with
their SKY130 HD standard-cell Apache-2.0 provenance and license. Refer to the
archive's notices and the fixture's [source record](tests/fixtures/sky130-public-decks-v1/README.md).

## Public SKY130 seal and alignment reference

The public seal/Nikon template used by `icstudio/digital_sky130_alignment.py`
comes from Open PDKs revision `0ec4fa67eade28cd0a4352c04df981840809427b`,
`sky130/custom/scripts/seal_ring_generator`, under Apache-2.0. Upstream:
https://github.com/fossi-foundation/open-pdks/tree/0ec4fa67eade28cd0a4352c04df981840809427b/sky130/custom/scripts/seal_ring_generator.
The upstream documentation credits SkyWater with the example seal geometry
subsequently imported and edited for the public Magic generator.

The unmodified source files, original notices, license and source identities
are retained in `tests/fixtures/sky130-public-seal-v1`. The distribution's
Apache-2.0 text is [licenses/Apache-2.0.txt](licenses/Apache-2.0.txt).
Studio's 2026-10-15 adaptation transcribes the public geometry into integrity
checks and requires the complete seal boundary before selecting alignment
windows. The independent Magic exports in
`tests/fixtures/sky130-public-seal-oracles-v1` and the derived layouts in
`docs/validation/sky130-alignment-audit-2026-10-15/controls.zip` retain this
upstream attribution and Apache-2.0 provenance. Studio's added checker and
test code are GPL-3.0-or-later. These template checks do not establish
foundry mask-generation equivalence or complete physical qualification.

## Included Xschem and GF180 simulation assets

Standard Xschem symbols: Ubuntu 3.4.4-1build1, GPL-2.0-or-later. Original copyright and license headers are retained under icstudio/assets/exchange/xschem; the GPL text is in licenses/GPL-2.0.txt. Corresponding source: https://archive.ubuntu.com/ubuntu/pool/universe/x/xschem/ and https://github.com/StefanSchippers/xschem/tree/3.4.4.

GF180MCU primitive symbols and ngspice model files: Apache-2.0, upstream commit 4d0b4cef59c7686fac5fd3f4c6fb41d251d1f90c. Source: https://github.com/fossi-foundation/globalfoundries-pdk-libs-gf180mcu_fd_pr/tree/4d0b4cef59c7686fac5fd3f4c6fb41d251d1f90c. Original files and license accompany the application; assets/exchange/index.json records individual hashes and source paths. These are schematic and simulation assets, not physical signoff decks.

ngspice: BSD-style and component-specific licenses retained in the runtime COPYING/copyright files. The Windows console runtime is the unmodified official version 46 distribution: https://sourceforge.net/projects/ngspice/files/ng-spice-rework/old-releases/46/ngspice-46_64.7z/download; corresponding source: https://sourceforge.net/projects/ngspice/files/ng-spice-rework/old-releases/46/. Its COPYING document retains its CC-BY-SA 4.0 notice, and the executable retains its upstream component terms. Historical Windows evidence used version 42 and keeps that identity. The Linux host-tools reference is Ubuntu 42+ds-3build1; corresponding source: https://archive.ubuntu.com/ubuntu/pool/universe/n/ngspice/. The managed Linux/WSL runtime is separately described below.

The current Windows installer and portable archive use the same PyInstaller
directory build from `scripts/package.py` and `scripts/build_windows.ps1`.
Corresponding application source accompanies the build as a source ZIP;
dependency metadata and licenses are retained by the packager. The separately
available `scripts/assemble_windows.py` recipe instead embeds CPython, extracts
Windows runtime wheels and uses Distlib native launchers. That source-based
assembly records its supplied runtime archive, wheels and file hashes in
`runtime-manifest.json` and retains Python and Distlib licenses. Distlib source:
https://github.com/pypa/distlib. Its editable `app` folder and `python` directory
describe that alternative assembly, not the current public desktop archive.

Encrypted desktop hosting uses cryptography to generate its private host certificates. Its wheel includes OpenSSL and other components with their own notices. The frozen packager retains cryptography's distribution metadata and license directory, including its bundled-component notices, and dependency metadata. The portable assembler retains the complete wheel metadata and licenses, including CFFI and pycparser. Corresponding upstream sources: https://github.com/openssl/openssl, https://github.com/python-cffi/cffi and https://github.com/eliben/pycparser; the bundled metadata identifies their versions and licenses.

## Added bundled simulation PDKs in 0.22.0.dev10

SKY130A primitive models, symbols and display layers are extracted from the checksum-pinned `common.tar.zst` and `sky130_fd_pr.tar.zst` assets of https://github.com/chipfoundry/volare/releases/tag/sky130-fa87f8f4bbcc7255b6f0c0fb506960f531ae2392. Upstream headers and Apache-2.0/model and symbol license files are retained in `icstudio/assets/pdks/sky130A`. The bundled package includes only the primitive model include closure, primitive symbols and display map. Standard-cell libraries and physical verification decks are excluded.

The GF180MCU D adapter reuses the existing pinned primitive files above, adds `.ngspice` compatibility aliases, and includes `tech/klayout/gf180mcu.lyp` from the same upstream revision. Original Apache-2.0 headers and license are retained. Each package records source provenance in `UPSTREAM-LOCK.json` and locks every distributed asset in `package.json`.

The Windows source/build provisioner uses py7zr 1.1.3 (LGPL-2.1-or-later), https://github.com/miurahr/py7zr/tree/v1.1.3, installed by pip with its dependencies. It is a setup dependency; the prepared portable desktop does not require it. The portable desktop retains the original Python license and the license files from the pinned PySide6, Shiboken, KLayout and cryptography wheels.

## Student physical process packages

GF180 C/D Magic technology and Netgen setup files are generated from unmodified open_pdks commit `aa3fc215a80d32437b8cca1cb3fdee819d18c4c9`: https://github.com/fossi-foundation/open-pdks/tree/aa3fc215a80d32437b8cca1cb3fdee819d18c4c9. Copyright and Apache-2.0 notices are retained in the files and `OPEN_PDKS_LICENSE`. Each variant records its source commit in `PHYSICAL-SOURCE-LOCK.json`; preprocessing options are explicit in `scripts/build_student_pdks.py`, and generated file hashes are in `package.json`. Models retain the separate primitive source lock above.

The IHP SG13G2 model, symbol, layer-map, Magic, Netgen and Verilog-A subset comes from https://github.com/IHP-GmbH/IHP-Open-PDK/tree/5e6d592e4002946a4616f798c357f0f3c06cf3b6. Its Apache-2.0 license, component-specific model headers, PSP notices and R3_CMC Educational Community License 2.0/NOTICE files are retained under `icstudio/assets/pdks/ihp-sg13g2`. All distributed files are checksummed in `package.json`; `scripts/build_student_pdks.py` reproduces the subset.

The managed runtime compiles the six IHP Verilog-A libraries with the checksum-pinned OpenVAF Reloaded OSDI 0.3 compiler in `packaging/digital/Dockerfile` (https://fides.fe.uni-lj.si/openvaf/). The build compiler is not distributed. Corresponding model sources and their notices accompany the generated libraries under `opt/icstudio/osdi/ihp-sg13g2/sources`; `build.json` records each compiled binary, compiler identity, generic CPU target and complete model-source dependency hashes.

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

The strict SKY130 HD connectivity adapter retains the BSD-2-Clause extraction
source by laurentc2 at revision `8f94c07178fbeef8630353add86f717746b1e3ab`:
https://github.com/laurentc2/SKY130_for_KLayout/tree/8f94c07178fbeef8630353add86f717746b1e3ab.
Its original source, copyright, license and pinned provenance are in
`icstudio/assets/verification/sky130/lvs`. The captured ORFS extraction file
differs only in runtime argument names, its usage comment and default schematic
filename; the adapter verifies that relationship before applying Studio's
strict device/body/port comparison changes. Every new LVS result and macro
export retains the original license and source alongside the generated checker.
This does not apply ORFS's build-script license to third-party platform files.

The independent `sky130_fd_sc_hd__diode_2` GDS/SPICE references are Apache-2.0,
Copyright 2020 The SkyWater PDK Authors, from
https://github.com/fossi-foundation/skywater-pdk-libs-sky130_fd_sc_hd/tree/9cb2d7cb8ed4619094263614039a61b6b2d22a88.
Their original headers, license and source lock accompany the adapter and the
`tests/fixtures/sky130-diode-reference` controls. The application LVS regression
fixture incorporates these cells and retains both the Apache and BSD terms.
Studio's adapters, test drivers and generated reference design remain under
this project's GPL-3.0-or-later license; third-party files keep their own terms.

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

The runtime build recipe retains SKY130 HD, GF180 MCU and IHP SG13G2 digital
platform files from ORFS commit `eaba6576441bf7c1743ea56ecdb1904210ec02c2`.
Original copyright and license headers remain in the captured files; the common
Apache-2.0 text and these notices are copied to `opt/icstudio/licenses`.
ORFS's BSD-3-Clause build/run-script license is retained at
`opt/icstudio/orfs/LICENSE_BUILD_RUN_SCRIPTS`. Exact platform inventories,
including materialized linked extraction rules, are locked in
`opt/icstudio/platforms.json`; each package's `files.json` also locks these
manifests and notice files. Source is available at the pinned
[ORFS revision](https://github.com/The-OpenROAD-Project/OpenROAD-flow-scripts/tree/eaba6576441bf7c1743ea56ecdb1904210ec02c2/flow/platforms).

Current source runtime builds replace the SKY130 HD library and physical views
with matched typical/slow/fast libraries, cell/technology LEFs, GDS, CDL and
minimum/nominal/maximum extraction decks from the checksum-pinned
`common.tar.zst` and `sky130_fd_sc_hd.tar.zst` assets of
[Volare sky130-fa87f8f4bbcc7255b6f0c0fb506960f531ae2392](https://github.com/chipfoundry/volare/releases/tag/sky130-fa87f8f4bbcc7255b6f0c0fb506960f531ae2392).
Copyright 2020 The SkyWater PDK Authors and other notices retained in the source
headers; Apache-2.0. The generated platform retains its archive/file hashes,
original ORFS configuration and physical-view overrides under `sky130hd/pvt`.
Each bundled platform also captures the common license, these source notices,
ORFS build-script license and a source lock under `redistribution`. Macro exports
copy the captured license and source-notice files with their hashes. Build-time
archive reading uses backports.zstd 1.7.0 in a temporary environment removed from
the runtime; corresponding source is [backports.zstd](https://github.com/rogdham/backports.zstd).

The application's optional timing-oriented mapping recipe is adapted from
`flow/scripts/abc_speed.script` at the same ORFS revision. Copyright (c) 2018-2023,
The Regents of the University of California. Its BSD-3-Clause terms and disclaimer
are retained in [the source-distribution license](licenses/OpenROAD-flow-scripts-BSD-3-Clause.txt).
Studio adds explicit delay targets to mapping and sizing commands and retains
the generated script in each mapped job. This does not change the separate
licenses of ABC, Yosys or the selected cell libraries.

The managed runtime also includes Magic and Netgen at the commits in
`examples/physical-engine-lock.json`, plus the Ubuntu ngspice package. Magic's
`LICENSE`, Netgen's `Copying`, their complete source trees and the source lock
are retained under `opt/icstudio/physical`; Ubuntu package notices and source
versions are retained in the package inventory above. The relocatable Magic
batch initializer and Netgen Tcl initializer are changed by
`packaging/digital/assemble.py`, with their resulting source and file hashes
included in the runtime. The separate experimental GF180 extractor patch is
in `packaging/physical/magic-gf180-rc.patch`; it is not the default desktop engine.

The default SKY130 device package retains the above public NPN inputs and adds
their t/s/f selections only inside the existing tt/ss/ff library sections. The
modified library identifies this change. Original source deltas and license
copies under `icstudio/assets/qualification/sky130-base-v1` reproduce the prior
package; the IHP MIM fixture likewise retains its Apache notice and license.

The Linux/WSL simulation runtime builds from the ngspice 47 release with
OSDI, XSPICE, KLU and predictor support. Its SHA-256-pinned original source
archive, COPYING terms, build logs and binary identity are retained under
`opt/icstudio/simulation`. The Windows console runtime retains its separately
pinned, unmodified ngspice 46 distribution. Numerical qualification identifies each engine.
The generated Linux initializer is modified to resolve code models relative to
the installed launcher and to default to one simulation thread. Its original
bytes and an explicit modification notice are retained; users may select another
thread count in their control program. The corrected runtime also applies the
documented capacitor-multiplicity parser fix in `src/frontend/inpcom.c` through
`scripts/build_ngspice_runtime.py`. It retains the original source file,
`capacitor-multiplier.patch` and a modification notice with the source archive.
PDK model equations are unchanged. Qualification records distinguish this
corrected engine from the earlier build.

The MOS boundary qualification sources in
`docs/qualification/mos-boundary-sources-v1` are unmodified excerpts from the
public SkyWater and GlobalFoundries PDK documentation. Their Apache-2.0 license
copies, exact upstream revisions, original paths and SHA-256 checksums accompany
them. Local filenames are shortened; their contents and third-party licensing
are unchanged. The IHP boundary checks use the already bundled Apache-2.0 model
header identified in the qualification record. The new test runner is separate
project code under this project's GPL-3.0 license.

The selected GF180 resistor-layout qualification retains six unmodified
open-pdks source/license files at commit
`aa3fc215a80d32437b8cca1cb3fdee819d18c4c9` under
`icstudio/assets/physical/gf180_resistors`. Original headers, the Apache-2.0
license and exact path/checksum lock accompany them. The local invocation in
`scripts/qualify_gf180_resistor_layouts.py` explicitly changes contact enclosures,
guard clearance and contact coverage; it does not modify the retained source or
the process verification decks. IHP resistor checks use the already bundled
Apache-2.0 generators with their optional via stacks disabled.

The optional IHP KLayout extraction route retains the unmodified public LVS
runset and dependencies from IHP-Open-PDK commit
`5e6d592e4002946a4616f798c357f0f3c06cf3b6` under
`icstudio/assets/physical/ihp_klayout_lvs`. Original copyright headers and the
Apache-2.0 license accompany an exact source and checksum inventory. These
upstream files keep their separate license. Studio's GPL-3.0 adapter executes
extraction without alignment, simplification, purging or implicit connections;
it retains native results and records the pin-text and BJT instance-prefix
interoperability conversions separately. Netgen compares the unfiltered circuit.

The same pinned Apache-2.0 IHP repository supplies the original inductor GDS/CDL
regression fixtures in `icstudio/assets/qualification/ihp-inductors`, with their
license, Git blob identities, download URLs and SHA-256 hashes. The qualification
script records its isolated-fixture crop, terminal/contact additions and explicit
10 nm bridge correction. Studio's private extraction copies preserve IND device
annotations, assign winding terminals by LA/LC/LB role and keep annotation text
separate from electrical net names. All public source files remain unchanged;
each run records hashes and descriptions of its local corrections. See
`docs/IHP_INDUCTOR_QUALIFICATION.md` for the limits; no electrical model is supplied.

The same pinned Apache-2.0 IHP repository supplies the unmodified NPN GDS/CDL
reference inputs in `icstudio/assets/physical/ihp_bipolars`, with their source
inventory and license. Local qualification adds explicitly recorded substrate
contacts inside the original guard. The optional extractor creates a private
run copy with an identified NPN orientation/unequal-emitter correction and a
private comparison setup retaining emitter count. A separate, versioned IHP
package can correct the NPN connected-region DRC search. Original upstream
headers and licenses remain in all copies; the correction recipes and test
runners are project code under GPL-3.0. These are local modifications, not
upstream or foundry-approved signoff decks.

The GF180 asymmetric high-voltage verification route retains unmodified public
DRC and LVS sources from `google/globalfoundries-pdk-libs-gf180mcu_fd_pr` commit
`9f992d5a9186d1f7820c58f039c484ad35b2edea` under
`icstudio/assets/physical/gf180_hv`. The original Apache-2.0 license, author list,
copyright headers and exact path/checksum inventory accompany these files.
They retain their separate license. The project's GPL-3.0 adapter creates private,
explicitly identified run copies correcting MDN.10d orientation, selecting the
asymmetric extractor from public drain masks, removing reference-driven filtering
and implicit joins, and connecting substrate only after independent physical-metal
checks. The original mask-coupon generator and audit code are project code under
GPL-3.0. These local changes are not upstream or foundry-approved signoff rules.

The RF diode qualification inputs under `icstudio/assets/qualification/sky130-rf`
retain four unmodified files from the public `google/skywater-pdk-libs-sky130_fd_pr`
tree `f62031a1be9aefe902d6d54cddd6f59b57627436`, their individual Git blob identities,
checksums, original headers and Apache-2.0 license. These originals keep that
license. The separate candidate builder marks its two derivative wrappers and
adds the explicit perimeter to their `dp` branches. It retains all originals
alongside the derivatives. The independent equations, runtime guard and
qualification runners are project code under GPL-3.0. The candidate remains
outside the default package pending physical and operating-envelope qualification.
