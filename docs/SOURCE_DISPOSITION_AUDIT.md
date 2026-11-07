# Source disposition audit

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
