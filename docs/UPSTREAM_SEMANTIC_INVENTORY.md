# Authenticated GF180 and IHP interface inventory

The [November 7 record](validation/upstream-semantics-inventory-2026-11-07.json)
and [compressed report](qualification/upstream-semantics-inventory-2026-11-07.json.gz)
reconcile declared model, symbol, generator, extraction, library and process
interfaces with the application's current packages and digital profiles. Chunk 7
remains open. Inventory success, a matching name, and a source file's presence
are not full device qualification.

The Windows pass accounts for 29,520 files, verifies 11,707 selected source
entries and emits 84,756 interface records, with zero parser gaps and one retained
blocking source diagnostic. The 641 GDS sources declare 13,898 structures; 27
use verified zero block padding. These are source/interface counts, not supported
device counts. All 21 focused tests pass. Native Linux replay is pending the
combined source snapshot.

## Source identities and retained distinctions

The original authenticated graph retains IHP-Open-PDK commit
`5e6d592e4002946a4616f798c357f0f3c06cf3b6`, all five IHP gitlinks, and the
selected GF180 primitive commit `4d0b4cef59c7686fac5fd3f4c6fb41d251d1f90c`.
The additional [GF180 parent graph](qualification/upstream-semantics-gf-inputs-2026-11-07.json.gz)
locks `fossi-foundation/gf180mcu-pdk` at
`25ed9c64b64b8e1b93cc4d2d5cade4cd82383a9a`, including all seven gitlinks:
7-track and 9-track standard cells, I/O, SRAM, the SRAM documentation repository,
the older primitive repository, and open-source-pdks documentation. Actual
`.gitmodules` URLs and commit/tree identities are verified, not inferred from
repository names or current branches.

The parent-linked primitive commit `9f992d5a9186d1f7820c58f039c484ad35b2edea`
does **not** replace the selected primitive revision. Its declarations remain
separate. The application explicitly uses that older source for GF180 high
voltage physical checks; the report verifies the existing companion provenance.
It also records the separate open-pdks source
`aa3fc215a80d32437b8cca1cb3fdee819d18c4c9` and digital physical-verification source
`05e7b6adf19edf942969c1c9625f02fd87874f06`. Their full repository graphs are not
silently included in the new parent graph.

## What is interpreted

Every file in the authenticated graphs has a ledger entry. Interface candidates
are selected by explicit path and format rules; tests/examples and other source
context remain visible. The runner reads and verifies actual Git blob bytes for
all selected candidates, including all library timing views rather than samples.
It records:

- SPICE/CDL definitions, terminal order, parameter names, section membership,
  include references, internal definitions and empty subcircuits. Conditional
  branches retain operator/nesting and expression fingerprints without evaluation.
- Xschem and gEDA terminal declarations, and Qucs-S port coordinates separately
  from nearby labels. Executable symbol attributes are fingerprinted, not run.
- Python PCell registration declarations, IHP's explicit registration list,
  parameter declarations and choice values. Nonliteral defaults retain referenced
  identifiers and expression fingerprints; these are not operating envelopes.
- Ruby extraction identities and layer-role names, literal option arrays,
  selected GF180 process variants, and explicit unresolved dynamic declarations.
  Tcl/Magic declaration identities remain source interfaces, not extracted nets.
- Liberty cells, pins, power pins, buses and PVT declarations; Verilog module
  ports; LEF macros and pins; and GDS structure names using the independently
  reviewed SKY130 inventory parser. A separately tested wrapper accepts only
  zero padding to the next 2048-byte GDS block boundary after a valid ENDLIB.

Library reconciliation keeps exact-case identities, case-distinct candidates,
missing views and CDL/LEF terminal-set differences. Liberty bus/pin contexts are
attached to their cells. Bus normalization, timing arcs, GDS connectivity and
arbitrary-design physical verification are not inferred from this inventory.
Internal SRAM subcircuits and repeated corner declarations are not counted as
separate supported devices. The one OASIS manual-test fixture is explicitly
recorded as an unimplemented format rather than silently skipped.

## Disposition rules and remaining blockers

`supported` has a narrow implementation meaning: exact upstream bytes and an
available catalog interface, with reachable global definitions, matching prefix,
terminal order and declared emitted parameters where a subcircuit is concerned.
Conditional, empty, ambiguous or unproved mappings remain `unimplemented`.
Every disposition separately records `qualified: false` or `qualification: false`.

Timing-library profile associations are candidates checked against the actual
`ORFS_PROFILES` and `BUNDLED_PLATFORMS` source and its hash. Even matching names,
families, PVT and profile paths do not establish identical installed-library bytes;
those rows stay `unimplemented`. GF180 C selects 9-track, 5-metal, 9K; D selects
9-track, 5-metal, 11K. The selected IHP library is the stdcell library. Other
libraries and corners are explicitly inventoried without promoting their support.

The limited `inapplicable` dispositions refer to explicit differences between
the source's A/B/C/D process variant and the requested C or D target. Unknown
device, generator or library mappings are never called inapplicable to close a gate.

The older GF180 model file has a mismatched `.endl` section name. The runner
retains its declarations and the original mismatch as a blocking source diagnostic;
it does not edit the source. Consequently the real report's `GAPS` status and
exit code 1 are expected. Missing source includes and explicit companion-source
routes are reported independently. In particular, the selected primitive's
launcher refers to a deck outside that selected tree; this alone is not proof of
an application failure because the application has separately locked physical
sources.

IHP's bondpad remains an empty placeholder in both simulator sources. Its
inductor geometry and openEMS/Palace integrations do not supply a qualified
compact model. Required unavailable models, complete operating envelopes,
physical/extracted connectivity and exact installed-release acceptance continue
to block chunk 7.

## Replay, integrity and attribution

Run from a clean source snapshot with the normal project Python environment:

```text
python scripts/inventory_upstream_semantics.py --cache /path/to/original-blob-cache --fetch-missing --output /path/to/new-report.json.gz
python -m unittest tests.test_upstream_semantics -v
```

Omit `--fetch-missing` for an entirely offline replay. Acquisition streams pinned
public source archives without extracting their paths, independently verifies
each selected member's Git blob hash, and retains complete original bytes and
notices in the local cache. It never executes upstream generators or tool scripts.
The report is deterministic gzip without timestamps or host-specific paths.
Changed/missing blobs or package files fail; before/after hashes guard both input
graphs, the runner, the recorded parser helpers and the current digital-profile source.

Published interface records contain generated facts and fingerprints rather
than model bodies, generator implementations, descriptive source prose or copied
netlist-format scripts. Original license/NOTICE sources have their own verified
identity list in the report and remain unmodified in the local source cache.
The corpus includes Apache-2.0 sources, the pycell4klayout GPLv3 API, the
pypreprocessor MIT implementation, and the R3_CMC ECL-2.0 declaration/NOTICE;
these are not relicensed by this audit. The Git metadata bundles retain public
commit metadata and verified `.gitmodules` configuration, separately from model
and generator source content. No universal redistribution permission or runtime
model availability is inferred from repository enumeration.
