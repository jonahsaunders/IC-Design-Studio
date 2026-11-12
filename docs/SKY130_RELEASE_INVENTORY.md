# Complete pinned SKY130 release inventory

The November 7 audit covers all seven archive assets of release
`sky130-fa87f8f4bbcc7255b6f0c0fb506960f531ae2392` (release ID `76339333`).
It extends, without replacing, the historical
[common/primitive inventory](UPSTREAM_VIEW_INVENTORY.md). Chunk 7 remains open.

| Archive | Regular files, both processes |
| --- | ---: |
| `common.tar.zst` | 3,521 |
| `sky130_fd_io.tar.zst` | 3,082 |
| `sky130_fd_pr.tar.zst` | 2,444 |
| `sky130_fd_sc_hd.tar.zst` | 1,832 |
| `sky130_fd_sc_hvl.tar.zst` | 420 |
| `sky130_ml_xx_hd.tar.zst` | 198 |
| `sky130_sram_macros.tar.zst` | 1,326 |
| **Total** | **12,823** |

There are 6,410 SKY130A and 6,413 SKY130B files. These are file counts, not
supported-device counts. All release members are hashed and retained in the
[compressed report](qualification/sky130-release-inventory-2026-11-07.json.gz).
The declaration index retains 9,036 distinct process/library/identifier tuples;
model bins, helper cells and repeated process variants are not device counts.
No upstream scripts, generators, models or macros are executed. No third-party
source is copied into the application by this work.

## Source identity and replay

The [source metadata](qualification/sky130-release-inputs-2026-11-07.json) records
the exact release, seven asset IDs, URLs, byte sizes, timestamps and SHA-256 pins.
Common, primitive and HD archives reuse the original application lock. IO, HVL,
metal-font and SRAM archives have newly retained retrieval hashes. The old assets
have no independent digest field in the GitHub release API. This audit does not
claim release-signature authentication.

Each archive is verified before and after streaming. Missing, duplicate, extra
or changed asset metadata fails, as do unsafe paths, nonregular members,
duplicate effective paths, truncated files and changed bytes. The application
package is checked against its file manifest before and after reconciliation.
Changing the audit code or helpers during a run also fails. Output gzip metadata
contains no host paths, timestamp or original filename.

Install the pinned `zstandard==0.23.0` audit dependency, then run:

```text
python scripts/inventory_sky130_release.py --inputs docs/qualification/sky130-release-inputs-2026-11-07.json --cache /retained/original-three-archives --cache /retained/new-four-archives --output /new/sky130-release.json.gz
python -m unittest tests.test_sky130_release_inventory -v
```

One cache directory containing all seven archives is also valid. Multiple
copies of the same archive in supplied directories are rejected as ambiguous.
The [validation record](validation/sky130-release-inventory-2026-11-07.json)
distinguishes exploratory runs, focused tests and final audit acceptance.
The 25 focused Windows tests include missing/changed/extra sources, scope and
prefix decoys, changed interfaces, unsupported bus expansion, quoted declarations
and absent selected-corner cells. An
[independent review](validation/sky130-release-independent-controls-2026-11-07.json)
passed 19 additional controls and six native KLayout readbacks: 225 GDS structure
names and 91 LEF macro names matched. Those bounded readbacks do not establish
geometry, connectivity or full-corpus native-tool acceptance.

## Declared cells, interfaces and process options

The report inspects actual Liberty cell and pin groups, operating-condition
declarations, LEF macros and pins, SPICE/CDL definitions and ordered terminals,
model parameter names, GDS structure records and Verilog declaration identities.
SPICE scopes, library sections, conditional nesting/branch operators and instance
prefixes are preserved. Conditional expressions, Liberty Boolean expressions,
Verilog headers and descriptive node prose are represented by hashes and byte
counts; their source text is not retained in the report. A nested helper,
incompatible model prefix or similarly named model
cannot establish a catalog binding. SPICE terminal comparison is case-insensitive;
original spellings are retained. No `_nhv`, size or other suffix is silently
removed to manufacture equivalence.

Quoted or commented fake declarations do not become cells. Verilog header
identities and conditional macro names remain explicit and unelaborated; the
audit does not claim Verilog port-set agreement. Escaped identifiers retain
their original spelling and canonical identifier. Parameterized Liberty buses
require expansion review; their unexpanded bits cannot pass a terminal check.
Magic filenames are explicitly labeled layout-file identities, not electrical
declarations. Internal Liberty pins are retained separately from external
terminals. This matters for the six HD `dlclkp`/`sdlclkp` variants whose `M0`
pin has `direction : internal`.

The application selects `sky130hd` and its typical
`sky130_fd_sc_hd__tt_025C_1v80.lib` view. Its 428 declared cells receive individual
comparisons against the release's LEF, SPICE, CDL, GDS and Verilog declarations.
All 428 have agreeing external pin sets in LEF, SPICE and CDL, consistent LEF
signal directions, and same-identifier GDS/Verilog declarations.
This checks identities and exposed pin sets; it does not perform extraction or
LVS. Per-corner cell coverage is explicit, so a cell disappearing in another
selected corner is visible. The report retains all other Liberty characterization
points without treating them as selected corners or rated operating envelopes.

The complete analog catalog is reconciled by exact model identifier and compatible
instance prefix. The two `icstudio_cap_var_*_parallel` names are local application
adapters, so their exact names are not expected in this upstream release. Their
local provenance and electrical/physical qualification remain separate. The
unavailable unsuffixed VPP model remains a blocker; the pinless `corner.sym` PDK
control is separately identified as metadata, not a missing electrical device.

Both `nodeinfo.json` files explicitly declare `METAL5`, `MIM` and
`REDISTRIBUTION`; SKY130B additionally declares `RERAM`. SKY130B is retained in
the audit and is outside the selected SKY130A process. IO, HVL and SRAM sources
are present but have no selected application digital platform. The metal-font
archive contains layout artwork and its generator. None acquires support merely
from its presence in the release.

HDLL, HS, LP, LS, MS and OSU T12/T15/T18 are explicitly `unknown` in this release's
node metadata and have no corresponding library archive. Complete coverage of
the seven assets does not establish completeness of those broader upstream
library options. A contradictory `unknown` declaration with present library
files would be reported as a review finding. Tool integration references remain
separate from library availability.

The retained report contains generated declaration facts and content identities,
not reusable copies of upstream implementation source. Its notice-file ledger
identifies the original release's named LICENSE/NOTICE files by path and hash.
File-level notices remain in the pinned source archives. The report grants no
reuse rights to underlying libraries and does not claim a complete licensing
determination across all upstream content.

## Acceptance boundary

Inventory `PASS` means that the pinned release was enumerated and its declared
metadata reconciled. Every report and identifier keeps `qualified: false`.
Complete terminal/parameter/model behavior, supported operating envelopes,
layout, extracted connectivity and exact installed-release acceptance remain
the original gates. Unsupported required devices still block chunk 7; an
unselected-library disposition is not a waiver.
