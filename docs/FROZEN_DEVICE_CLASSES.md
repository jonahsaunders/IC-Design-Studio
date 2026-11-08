# Frozen finite device classes

The installed acceptance runner exercises 35 existing finite class cases through the frozen application's open/save/reopen, GDS/OAS export and managed native-worker paths. It covers seven IHP parallel-CMIM cases, ten SKY130 shared-bottom MiM cases, sixteen ordinary MOS grouping cases and two saved MOS benches. It preserves the source contracts, dimensions, tolerances and deliberate fault meanings established by their native readers.

The source-development pilot exposed a delivery defect: managed staging copied the locked assets but omitted `package.json`, so supported MOS grouping could not authenticate the staged package after native DRC/LVS passed. Staging now carries an existing manifest with exact saved-lock equality, strict JSON and unchanged-byte/link checks. The existing reviewed full-semantic authentication still rejects altered package meaning.

The original failure after 17 expected capacitor outcomes is retained. The corrected managed pilot produced all 35 expected outcomes in 326.593 seconds; a separate reader checked the complete raw output. Final normal and optimized focused tests each passed 15 checks. Independent reviews checked actual channel geometry and native graph/export completeness, source/registry links, all GUI streams and lifecycle refusal controls. These are source-development results, not installed acceptance. See [the finite source-pilot record](validation/frozen-device-class-source-pilot-2026-11-08.json).

Run the new installed subgate after normal frozen readiness, using the executable's containing directory as `--distribution-root`:

```text
python scripts/verify_frozen_device_classes.py --executable <installed-executable> --distribution-root <executable-parent> --candidate <exact40SHA> --physical-pdk <locked-sky130A-adapter> --output <fresh-evidence-directory>
python scripts/verify_frozen_device_classes.py --candidate <exact40SHA> --readback <retained-evidence-directory>
```

The runner preserves the 1,800-second overall limit and 300-second worker limits. It authenticates the exact candidate helpers, distribution, managed backend, package assets and complete runtime before and after execution. The final readback requires every case's source, native output, tool and failure evidence. Source-only runs cannot pass the frozen header or normal readiness checks.

This finite topology subgate supplements the existing installed recipes. It does not establish complete model validity, calibration, public-rule coverage, arbitrary geometry/hierarchy support or family qualification. Those gates remain open where their separate evidence is missing. Retention includes the complete job/probe outputs and backend identities, while excluding copied runtime binary caches; their authenticated manifests and digests identify the original payload.
