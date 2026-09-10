# IC Design Studio 0.21.1.dev1

Unreleased development snapshot, 9 September 2026. Based on the prepared 0.21.0 source. This is a focused native exchange reliability update; the previous Windows portable download does not contain it.

## Native hierarchy export fix

Export previously placed every cell's interface labels at fixed coordinates: x = -120, with y starting at 0. A valid edit could put an unrelated pin, wire or label at the same position. Export then introduced conflicting net labels, preventing reviewed reimport of a circuit that was valid in the native editor.

Export now reuses a label or device contact on each port's own net. An unused port is placed clear of all existing pins, wire vertices and label anchors. Port records retain the declared terminal order. Reusing the contact also prevents another port label from being added on each exchange cycle.

This change preserves the existing transactional connectivity guard. A connected move that changes topology is still rejected, with the original history and geometry intact.

## Regression coverage

`tests/test_native_exchange.py` uses a tiny two-cell divider with voltage source, parameterized resistor hierarchy, load resistor, scalar port names and an embedded text-model dependency. It covers:

- Port placement beside moved pins, wire interiors and detached labels.
- Unused ports, declared top-level port order and stable label counts across repeated exports.
- Eighteen connected instance moves, with compact routes and exact geometry/topology restoration through undo and redo.
- Child pin rename, an instance parameter edit, and three export/review/save/reopen cycles after deleting the original source directory.
- Cell/device/terminal/net identities, terminal order, expression strings and model contents.
- Reviewed external parameter edits and rejection when a child schematic changes after review.
- Rejection of an accidental net merge without changing the live document or undo history.

Run the regression and release gates from the source root:

```sh
python -m unittest tests.test_native_exchange -v
python -m unittest discover -s tests -v
python scripts/check_release.py
```

## Validation and limits

The Linux/Python 3.12 source checks passed: eight new regression tests; 309 core tests passed with seven skipped native-engine tests; local documentation/gallery checks passed. Pinned PySide6-Essentials 6.8.3 and KLayout 0.30.5 were installed for the core suite.

The new circuits were structurally checked and netlisted. No new ngspice numerical or worker results are claimed. Qt GUI startup on this host was blocked by missing `libEGL.so.1`, so this update adds no GUI execution evidence. Windows, macOS, PDK numerical/physical qualification, hosted CI and publication remain outstanding. Historical [0.21.0 release evidence](RELEASE_0.21.md) applies to that earlier build.

The accompanying handoff includes fresh logs, source fingerprints, a minimal native reproduction, a source patch, and a machine-readable development validation record. No new platform binary was assembled.
