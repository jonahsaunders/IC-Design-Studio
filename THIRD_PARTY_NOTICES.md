# Third-party notices and corresponding source

The application code is GPL-3.0-or-later. Do not remove this source package, its build instructions, or these notices when distributing the application bundle. The desktop packages include ngspice, standard Xschem symbols and public GF180MCU primitive simulation assets. Physical rule decks and Magic/Netgen engines are separate.

| Component | Version | License / corresponding source |
|---|---|---|
| Qt / PySide6 / Shiboken | 6.8.3 | LGPL-3.0 and component-specific licenses; https://download.qt.io/official_releases/QtForPython/pyside6/PySide6-6.8.3-src/ and https://download.qt.io/archive/qt/6.8/6.8.3/ |
| KLayout | 0.30.5 | GPL-2.0-or-later; https://github.com/KLayout/klayout/tree/v0.30.5 and https://www.klayout.de/ |
| PyInstaller bootloader | 6.16.0 | GPL with distribution exception; https://github.com/pyinstaller/pyinstaller/tree/v6.16.0 |
| Python runtime | 3.12 | Python Software Foundation license; https://www.python.org/downloads/source/ |

Exact wheel requirements are in requirements.txt. Dynamic Qt libraries can be replaced by compatible, modified libraries; no anti-modification restriction is added. The application source and build scripts are supplied. Standard Linux graphics/runtime libraries may be collected by the packager; their distribution copyright notices are included under licenses/system when collected. They retain their original licenses. Source locations for Ubuntu packages are https://packages.ubuntu.com/noble/ and https://archive.ubuntu.com/ubuntu/pool/; exact library filenames are visible in the binary bundle.

Review licenses and provide continuing equivalent access to complete corresponding source for the versions you distribute before a public/commercial release. This delivery has not completed the blueprint's independent legal/compliance release review.

## Optional SKY130 reference evidence

The separately supplied SKY130 reference bundle contains a subset of the SkyWater open PDK and generated derivatives of its inverter. Copyright 2020 The SkyWater PDK Authors and other notices retained in the original files. These assets are distributed under Apache-2.0; see licenses/Apache-2.0.txt and their file headers. The app's reference fetch script points to the pinned upstream Volare distribution. Magic and Netgen used for verification are external tools. ngspice is included in the 0.18 desktop packages.

## Included Xschem and GF180 simulation assets

Standard Xschem symbols: Ubuntu 3.4.4-1build1, GPL-2.0-or-later. Original copyright and license headers are retained under icstudio/assets/exchange/xschem; the GPL text is in licenses/GPL-2.0.txt. Corresponding source: https://archive.ubuntu.com/ubuntu/pool/universe/x/xschem/ and https://github.com/StefanSchippers/xschem/tree/3.4.4.

GF180MCU primitive symbols and ngspice model files: Apache-2.0, upstream commit 4d0b4cef59c7686fac5fd3f4c6fb41d251d1f90c. Source: https://github.com/fossi-foundation/globalfoundries-pdk-libs-gf180mcu_fd_pr/tree/4d0b4cef59c7686fac5fd3f4c6fb41d251d1f90c. Original files and license accompany the application; assets/exchange/index.json records individual hashes and source paths. These are schematic and simulation assets, not physical signoff decks.

ngspice 42: BSD-style and component-specific licenses retained in the runtime COPYING/copyright files. Windows console distribution: https://sourceforge.net/projects/ngspice/files/ng-spice-rework/old-releases/42/ngspice-42_64.7z/download. Linux distribution: Ubuntu 42+ds-3build1; corresponding source: https://archive.ubuntu.com/ubuntu/pool/universe/n/ngspice/. Upstream source: https://sourceforge.net/projects/ngspice/files/ng-spice-rework/old-releases/42/.

The Windows portable package uses CPython 3.12.9, official win_amd64 wheels for the versions in requirements.txt, and Distlib native launchers distributed by pip 25.0.1. Runtime archive and file hashes are recorded in runtime-manifest.json. Python and Distlib licenses accompany those components. Distlib source: https://github.com/pypa/distlib. The application itself is supplied as editable Python source in the app folder.
