# Public IHP KLayout LVS sources

Unmodified sources from IHP-Open-PDK commit
`5e6d592e4002946a4616f798c357f0f3c06cf3b6`. [SOURCE.json](SOURCE.json) records
each original path, source URL, Git blob identity and SHA-256 checksum.
Original copyright headers and [Apache-2.0 terms](LICENSE) are retained.
The surrounding Studio adapter uses the project's GPL-3.0 license.

Studio runs this deck in extraction-only mode with simplification, combining,
purging and implicit connections disabled. It never treats the upstream
comparison's success message as acceptance. Strict Netgen comparison uses the
actual unfiltered circuit, with explicit nonempty/interface checks. The original
Magic DRC deck remains required. The source checkout and PDK revision are
recorded separately; this is an explicitly selected additional verifier.

The current qualification samples cover PNP layouts only. Other device classes,
broader geometry ranges, parasitics, operating conditions and foundry signoff
are not qualified by this bundle. See the
[IHP bipolar qualification guide](../../../../docs/IHP_BIPOLAR_LAYOUT_QUALIFICATION.md).
