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
full Magic DRC remains required. The source checkout and PDK revision are
recorded separately; this is an explicitly selected additional verifier.

Each private run copy explicitly records the local NPN orientation and unequal
emitter correction. The stored files here remain byte-identical to upstream.
The private Netgen setup retains emitter count, and the NPN fixtures use a
separately versioned Magic correction with unchanged rule operands/distances.
Finite PNP and NPN layout samples do not qualify other device classes, continuous
geometry ranges, parasitics, operating conditions or foundry signoff. See the
[IHP bipolar qualification guide](../../../../docs/IHP_BIPOLAR_LAYOUT_QUALIFICATION.md).
