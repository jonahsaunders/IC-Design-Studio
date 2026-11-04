"""Closed SKY130 contract/package identity pairs; numerical decisions stay in readers.

V1 and V2 records remain byte-for-byte historical. V3 binds the same reviewed
criteria and model sources to the separately prepared current package. No
identity version grants fresh native, installed or whole-family qualification.
"""
VERSIONS = {
    "li": {
        "v1": {
            "path": "docs/qualification/sky130-li-contract-v1.json",
            "sha256": "be2c12aa3c80f3a189da0c303d53323ce083982820d0ff101c524b8a8d4e10c6",
            "package_sha256": "840f7af802b07346650c50a5967e532a4cb1716623cf0c9d6fd6c58eaf35fcbe",
            "id": "sky130-li-contract-v1"
        },
        "v2": {
            "path": "docs/qualification/sky130-li-contract-v2.json",
            "sha256": "1d675dd4fa66d7d386c149a92d83df6e6562708df3eefd528bcff01b7da658e2",
            "package_sha256": "125cde7c313ee18a05a7ec5c280d514b99aea521d6b39476e44f486ae494153b",
            "id": "sky130-li-contract-v2"
        },
        "v3": {
            "path": "docs/qualification/sky130-li-contract-v3.json",
            "sha256": "299b229b56010043be985d2cad3aedeafeb25638cd965c315a3b293a4d66bd5e",
            "package_sha256": "0c19e0ea5718a841045b597022d13f2dcb57e35cf8be9757b254fb465f2a35c4",
            "id": "sky130-li-contract-v3"
        }
    },
    "metal": {
        "v1": {
            "path": "docs/qualification/sky130-metal-resistors-linked-v1.json",
            "sha256": "2c0ad7e2142ec684bebe843596b84a1e6809e3f5a52195660bba8509e190c612",
            "package_sha256": "840f7af802b07346650c50a5967e532a4cb1716623cf0c9d6fd6c58eaf35fcbe",
            "id": "sky130-metal-resistors-linked-v1"
        },
        "v2": {
            "path": "docs/qualification/sky130-metal-resistors-linked-v2.json",
            "sha256": "0ee0f901911cf1d7ed60e53abb907195089881b8847e6f51d30105498bc17c3a",
            "package_sha256": "125cde7c313ee18a05a7ec5c280d514b99aea521d6b39476e44f486ae494153b",
            "id": "sky130-metal-resistors-linked-v2"
        },
        "v3": {
            "path": "docs/qualification/sky130-metal-resistors-linked-v3.json",
            "sha256": "77554c7a6484f44f33a7b754bd768cc381f8df76a31d9089b015fce04a51e11d",
            "package_sha256": "0c19e0ea5718a841045b597022d13f2dcb57e35cf8be9757b254fb465f2a35c4",
            "id": "sky130-metal-resistors-linked-v3"
        }
    },
    "parallel": {
        "v1": {
            "path": "docs/qualification/sky130-metal-resistor-parallel-v1.json",
            "sha256": "66b905bcde6cc53fd94a5408fd5ae76f71387ae41d8c7a0c5357961c6bc64472",
            "package_sha256": "840f7af802b07346650c50a5967e532a4cb1716623cf0c9d6fd6c58eaf35fcbe",
            "id": "sky130-metal-resistor-parallel-v1"
        },
        "v2": {
            "path": "docs/qualification/sky130-metal-resistor-parallel-v2.json",
            "sha256": "ede9b483fbbb35b6072fff3526750dc86bf81ced805dcf48cad3df486d175363",
            "package_sha256": "125cde7c313ee18a05a7ec5c280d514b99aea521d6b39476e44f486ae494153b",
            "id": "sky130-metal-resistor-parallel-v2"
        },
        "v3": {
            "path": "docs/qualification/sky130-metal-resistor-parallel-v3.json",
            "sha256": "496fb26e7ae26fc4a95dd0ac4b1abca0640e9019fa2326e3129d7db6db723950",
            "package_sha256": "0c19e0ea5718a841045b597022d13f2dcb57e35cf8be9757b254fb465f2a35c4",
            "id": "sky130-metal-resistor-parallel-v3"
        }
    },
    "installed_metal": {
        "v1": {
            "path": "docs/qualification/sky130-metal-installed-v1.json",
            "sha256": "9245943194baf0fca698b9487b962390d2dc2af07983e19d0b493ae21f952fa2",
            "package_sha256": "840f7af802b07346650c50a5967e532a4cb1716623cf0c9d6fd6c58eaf35fcbe",
            "id": "sky130-metal-installed-v1"
        },
        "v2": {
            "path": "docs/qualification/sky130-metal-installed-v2.json",
            "sha256": "f9448aae8d3860e708a80d8ff4df8530fddf2a2ae56c1b9177dd0e4fabf9a42b",
            "package_sha256": "125cde7c313ee18a05a7ec5c280d514b99aea521d6b39476e44f486ae494153b",
            "id": "sky130-metal-installed-v2"
        },
        "v3": {
            "path": "docs/qualification/sky130-metal-installed-v3.json",
            "sha256": "0cf2ef72e6c16e10e16a7f88a41fac71cafb0f21661e8a12b095c4c00216f5e0",
            "package_sha256": "0c19e0ea5718a841045b597022d13f2dcb57e35cf8be9757b254fb465f2a35c4",
            "id": "sky130-metal-installed-v3"
        }
    },
    "installed_parallel": {
        "v1": {
            "path": "docs/qualification/sky130-metal-parallel-installed-v1.json",
            "sha256": "f2cf30ea793449d541305b2c10a57c8bbdf5cfadf2ab7b24bb9e99848e309ce9",
            "package_sha256": "840f7af802b07346650c50a5967e532a4cb1716623cf0c9d6fd6c58eaf35fcbe",
            "id": "sky130-metal-parallel-installed-v1"
        },
        "v2": {
            "path": "docs/qualification/sky130-metal-parallel-installed-v2.json",
            "sha256": "14b37da535c79fd2a3f8571772589590e8768b520571edd027b245278481f5d0",
            "package_sha256": "125cde7c313ee18a05a7ec5c280d514b99aea521d6b39476e44f486ae494153b",
            "id": "sky130-metal-parallel-installed-v2"
        },
        "v3": {
            "path": "docs/qualification/sky130-metal-parallel-installed-v3.json",
            "sha256": "67d26362a72771d32418ce21abfcecdf40c5146913b960abc8a64a1d77a89a17",
            "package_sha256": "0c19e0ea5718a841045b597022d13f2dcb57e35cf8be9757b254fb465f2a35c4",
            "id": "sky130-metal-parallel-installed-v3"
        }
    },
    "voltage": {
        "v1": {
            "path": "docs/qualification/sky130-mos-voltage-v1",
            "sha256": "4731c93a5acc43ea014cc383e1aff4e707dd56e07f2494c8bd8b2105fefdecbc",
            "package_sha256": "840f7af802b07346650c50a5967e532a4cb1716623cf0c9d6fd6c58eaf35fcbe"
        },
        "v2": {
            "path": "docs/qualification/sky130-mos-voltage-v2",
            "sha256": "1649263eedc3fcbf60b11c7dee78aaf0b4e86e421ca7d0db45dea8b4a6c1eac2",
            "package_sha256": "125cde7c313ee18a05a7ec5c280d514b99aea521d6b39476e44f486ae494153b"
        },
        "v3": {
            "path": "docs/qualification/sky130-mos-voltage-v3",
            "sha256": "ca560ab239fa24d0cf445ed045829a42bdd970ae4c034dd43be2ab87a5cedb24",
            "package_sha256": "0c19e0ea5718a841045b597022d13f2dcb57e35cf8be9757b254fb465f2a35c4"
        }
    }
}


def selected(family, contract_sha256=None, package_sha256=None):
    """Resolve one exact retained contract hash; never fall back on a mismatch."""
    rows=VERSIONS[family]
    if contract_sha256 is None:
        row=rows['v3']
    else:
        matches=[row for row in rows.values() if row['sha256']==contract_sha256]
        if len(matches)!=1:raise ValueError('Unreviewed SKY130 contract identity.')
        row=matches[0]
    if package_sha256 is not None and row['package_sha256']!=package_sha256:
        raise ValueError('SKY130 contract/package identity pair differs.')
    return row.copy()


def package_version(family, package_sha256):
    matches=[row for row in VERSIONS[family].values() if row['package_sha256']==package_sha256]
    if len(matches)!=1:raise ValueError('Unreviewed SKY130 package identity.')
    return matches[0].copy()
