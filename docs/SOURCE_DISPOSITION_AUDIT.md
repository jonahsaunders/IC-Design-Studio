# Source disposition audit

The [November 8 report](qualification/source-dispositions-2026-11-08-v1.json.gz) adds eighteen embedded schematic views and nine exact text reference/provenance views: 958 additional facts. 107 inventory gaps remain. The [cross-host record](validation/chunk7-embedded-reference-integration-2026-11-08.json) retains 356 affected tests per host and byte-identical complete audits. All previous items and remaining gaps are exact. Independent comparison checks every new fact against its reviewed source. Repeated assignments remain diagnosed; documentary references/counts are not runtime bindings or reproduced results. No model, electrical, physical or installed qualification is inferred. Earlier records below retain their original scope.

The [fifth November 7 report](qualification/source-dispositions-2026-11-07-v5.json.gz) adds fourteen literal schematic views and 24,080 source facts. 134 production inventory gaps remain. The [cross-host record](validation/chunk7-schematic-integration-2026-11-07.json) retains 307 affected tests per host and byte-identical complete audits. All prior items and 75 historical diagnostic-source declaration lists remain exact. Valid multiline headers are preserved; nineteen remaining embedded-code/property gaps now have accurate explanations. No connectivity, symbol/model equivalence or qualification is inferred. Earlier records below retain their original scope.

The [fourth November 7 report](#restore-the-fourth-november-7-report) adds nine pinned legacy symbol views and 145 source facts. 148 production inventory gaps remain. The [cross-host record](validation/chunk7-legacy-symbol-integration-2026-11-07.json) retains 283 affected tests per host, identical complete reports and exact preservation of every previous item. Missing headers remain missing; pin boxes, bus references and extra power attributes remain distinct. The Qucs model identifiers and external symbol reference remain unresolved bindings. No upstream code or parameter equation is executed. Earlier records below retain their original scope.

The [third November 7 report](qualification/source-dispositions-2026-11-07-v3.json.gz) adds two CVC checker-rule files and six physical-layer/stack files: 484 additional source facts. 157 production inventory gaps remain. The [cross-host record](validation/chunk7-cvc-physical-integration-2026-11-07.json) retains 257 affected tests per host and byte-identical complete audits. Every previous item remains unchanged. Exact reviewed path/revision routing, unsupported-grammar controls and independent raw readback preserve the duplicated ITF layer, XS modeling exclusion and unevaluated Python lookup. These declarations do not supply missing simulator models or qualified operating limits. All earlier records below retain their original scope.

The [second November 7 report](qualification/source-dispositions-2026-11-07-v2.json.gz) enumerates all 22 pinned IRSIM configuration files and all eight XCircuit library/configuration files. The 30 previously opaque views now have explicit declaration dispositions; 165 other inventory gaps remain. The [cross-host record](validation/chunk7-xcircuit-irsim-integration-2026-11-07.json) retains 217 affected tests per host and byte-identical full audits. Independent raw readback checks all 484 IRSIM device declarations, 288 XCircuit objects and 1,146 pin labels. Ten template/pin discrepancies, two literal numeric-variable reads, unresolved generic-library dependencies and all qualification gates remain visible. Readers never execute upstream PostScript or Tcl. Literal value tokens and expression hashes are retained without inventing model bindings or operating limits.

The original checkpoint below retains its historical source and validation scope.

The November 7 checkpoint reports **GAPS**, with 195 unresolved production source views. It does not complete the original source-completeness criterion or qualify any device. The inventory contains 43,671 source-file identities and 744,604 explicit item dispositions; these counts are bookkeeping, not completion percentages.

The [report](qualification/source-dispositions-2026-11-07.json.gz) binds the reviewed GF/IHP semantic inventory, all seven pinned SKY130 release archives, and the complete two locked GF companion roots including their gitlink. It checks source links in both directions, exact target sets and reasons, unchanged current package/profile identities, and source/implementation hashes before and after execution. Previously omitted Liberty-JSON groups, Qucs-S symbols and schematics, Digital elements, macro options, PCell import mappings, Verilog-A parameter sets and tool configuration declarations now receive explicit accounting. SKY130B declarations are enumerated before their outside-target disposition.

Unknown dynamic/opaque production declarations remain inventory gaps. Known malformed upstream `.endl` and Xschem header diagnostics are retained without repairing the source or claiming importability. Supported inherited bindings still mean exact authenticated available source/catalog interfaces, not complete operating envelopes, extracted connectivity, simulation or release acceptance. Unsupported required devices continue to block qualification.

The [Windows validation](validation/source-dispositions-2026-11-07.json) records the completed guarded audit and 60 focused tests. Native replay is separate and was pending when that record was written; consult the [integration record](validation/chunk7-source-dispositions-integration-2026-11-07.json) for its eventual outcome. Original reports and the initial canonical-JSON comparison failure remain preserved.

The auditor runs offline: it neither downloads sources nor executes upstream programs or extracts archive paths. Reproduction requires a separately acquired original Git-blob cache, with each file named by its authenticated Git object ID, and all seven pinned `.tar.zst` release archives in the supplied archive-cache directories. The repository contains the metadata graphs and reports, not the approximately 4 GB raw-source cache. Reports retain generated identities, declaration facts and expression hashes; original sources and notices stay in those local caches. Git commit/tree associations and release digests are pinned; no upstream signature verification is asserted.

The exact graph inputs are `docs/qualification/upstream-view-inputs-2026-10-20.json.gz`, `docs/qualification/upstream-semantics-gf-inputs-2026-11-07.json.gz`, and `docs/qualification/source-dispositions-companion-inputs-2026-11-07.json.gz`. The runner also hard-pins `upstream-semantics-inventory-2026-11-07-v2.json.gz` and `sky130-release-inventory-2026-11-07.json.gz`; its report records every input and helper hash. Archive names, sizes and hashes are in `scripts/inventory_sky130_release.py` (`ASSETS`). Preserve original sources and applicable notices when preparing the caches.

The retained acquisition helpers are `work/fetch_inventory_companions.py`, `work/fetch_disposition_sources.py`, `work/fetch_small_disposition_sources.py`, `work/fetch_slib_sources.py`, and `work/semantic-audit/fetch_sources.py`, together with the separately recorded bounded IHP, remaining-source and symlink retrieval receipts. These are preparation artifacts in the output evidence bundle, not an automatic download stage in the auditor.

```text
python -m unittest tests.test_source_dispositions tests.test_source_configs
python scripts/audit_source_dispositions.py --cache <git-blob-cache> --sky-cache <sky130-pvt-cache> --sky-cache <sky-complete-release-cache> --output <new-report.json.gz>
```

This Windows run wrote the report after its final guards. Its last terminal result was truncated during tool-context handoff, so the validation does not claim a retained observed process return or wall duration; `1` is the frozen runner's expected return for `GAPS`. The separate integration record retains replay command logs and observed returns.

Chunk 7's engineering estimate remains 74%, low confidence (55–82%); it is separate from verified acceptance and unchanged by these counts.

## Restore the fourth November 7 report

The original compressed report is 22,930,906 bytes. This checkout stores its
19,041-byte [delta](qualification/source-dispositions-2026-11-07-v4.delta.json.gz)
against the [third report](qualification/source-dispositions-2026-11-07-v3.json.gz).
Use Python 3.12 from the repository root and choose a fresh output path.

```sh
python scripts/restore_nov7_dispositions.py --output build/source-dispositions-2026-11-07-v4.json.gz
```

The restore verifies both inputs and checks the compressed output against the
SHA-256 in the [original acceptance record](validation/chunk7-legacy-symbol-integration-2026-11-07.json).
The [original full file](https://github.com/jonahsaunders/IC-Design-Studio/blob/147a5501b79783a508d6057da8273195dfb2878c/docs/qualification/source-dispositions-2026-11-07-v4.json.gz)
remains available at the reviewed commit. The pilot saved 22,911,865 bytes of
report storage in the working tree. A Windows Python 3.12.7 run restored and
compared the compressed bytes in 18 seconds. Keep full inputs that an active
tool opens by path. For a historical report, record its readers, baseline,
hash, size and measured restore time before adopting this format.
