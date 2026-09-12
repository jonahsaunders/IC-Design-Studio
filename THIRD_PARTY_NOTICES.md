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
