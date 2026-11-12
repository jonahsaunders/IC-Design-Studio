# Public SKY130 deck comparison

These are **unmodified GPLv3 sources**, retained as comparison fixtures. They
are not installed as a replacement for Studio's required physical checks.
The adjacent [source lock](source-lock.json) records the exact commits, Git
blobs, SHA-256 identities and original paths. The full license is retained in
[GPL-3.0.txt](GPL-3.0.txt); original headers remain intact.

- [Tiny Tapeout source](https://github.com/TinyTapeout/tt-support-tools/blob/01d5d2814fa9dd61e9d211e0b235a4a592a9316a/precheck/tech-files/sky130A_mr.drc): release `2025.10.29_01.10`.
- [ChipFoundry source](https://github.com/chipfoundry/cf-precheck/blob/6c401ed5134a6466c7eed3e5524ebaacad4cea2a/src/cf_precheck/drc_scripts/sky130A_mr.drc): release `2026.03.30_01.00`.

Tiny Tapeout's [provenance record](https://github.com/TinyTapeout/tt-support-tools/blob/01d5d2814fa9dd61e9d211e0b235a4a592a9316a/precheck/tech-files/README.txt)
identifies its main deck as a copy from ChipFoundry's `mpw_precheck` revision
`f2264a82c1686e2924422ec1dddb829b9601a86d`. These are related implementations,
not two independent specifications. The repositories' Apache-2.0 root licenses
do not replace the explicit GPLv3 headers on these files. No later-version
grant is inferred for the copied decks. Studio's new comparison/test code
continues under the project's GPL-3.0-or-later license.

The comparison runner is [review_sky130_public_decks.py](../../../scripts/review_sky130_public_decks.py).
From the repository root, use a Python environment with `klayout.db` and a
KLayout executable supporting Ruby DRC:

```sh
python scripts/review_sky130_public_decks.py --reference-root /path/to/references --output /path/to/new-results --klayout /path/to/klayout
```

The reference directory contains `counter`, `uart` and `apb`, each with
`sky130-pin-export/final.gds`. The retained audit archive supplies those exact
inputs. The runner records engine/source/input hashes, commands, native logs
and marker reports. It enables FEOL, BEOL and off-grid checks together for the
references. Seal and floating-metal switches are explicitly false; SRAM
exclusion is false. Upstream also contains built-in cell filters. None of
these settings establishes full catalog coverage.

Four small controls exercise covered/uncovered contacts with and without
`areaid:core` (`81:2`). The older Tiny Tapeout deck misses the uncovered contact
inside that marker. The newer ChipFoundry deck and Studio's existing `ct.4`
predicate detect it. These controls test contact coverage, not complete SRAM
validity. A successful comparison report is not a signoff report or a full
Tiny Tapeout project precheck.

See the [qualification record](../../../docs/SKY130_PHYSICAL_QUALIFICATION.md#tiny-tapeout-public-deck-comparison)
for execution evidence and unresolved requirements.
