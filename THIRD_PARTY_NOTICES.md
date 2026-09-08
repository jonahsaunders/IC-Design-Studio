# Third-party notices and corresponding source

The application code is GPL-3.0-or-later. Do not remove this source package, its build instructions, or these notices when distributing the application bundle. No proprietary PDK, foundry rule deck, or ngspice/Magic/Netgen binary is bundled.

| Component | Version | License / corresponding source |
|---|---|---|
| Qt / PySide6 / Shiboken | 6.8.3 | LGPL-3.0 and component-specific licenses; https://download.qt.io/official_releases/QtForPython/pyside6/PySide6-6.8.3-src/ and https://download.qt.io/archive/qt/6.8/6.8.3/ |
| KLayout | 0.30.5 | GPL-2.0-or-later; https://github.com/KLayout/klayout/tree/v0.30.5 and https://www.klayout.de/ |
| PyInstaller bootloader | 6.16.0 | GPL with distribution exception; https://github.com/pyinstaller/pyinstaller/tree/v6.16.0 |
| Python runtime | 3.12 | Python Software Foundation license; https://www.python.org/downloads/source/ |

Exact wheel requirements are in requirements.txt. Dynamic Qt libraries can be replaced by compatible, modified libraries; no anti-modification restriction is added. The application source and build scripts are supplied. Standard Linux graphics/runtime libraries may be collected by the packager; their distribution copyright notices are included under licenses/system when collected. They retain their original licenses. Source locations for Ubuntu packages are https://packages.ubuntu.com/noble/ and https://archive.ubuntu.com/ubuntu/pool/; exact library filenames are visible in the binary bundle.

Review licenses and provide continuing equivalent access to complete corresponding source for the versions you distribute before a public/commercial release. This delivery has not completed the blueprint's independent legal/compliance release review.

## Optional SKY130 reference evidence

The separately supplied SKY130 reference bundle contains a subset of the SkyWater open PDK and generated derivatives of its inverter. Copyright 2020 The SkyWater PDK Authors and other notices retained in the original files. These assets are distributed under Apache-2.0; see licenses/Apache-2.0.txt and their file headers. The app's reference fetch script points to the pinned upstream Volare distribution. Magic, Netgen and ngspice used for verification are external tools and are not bundled with this application.
