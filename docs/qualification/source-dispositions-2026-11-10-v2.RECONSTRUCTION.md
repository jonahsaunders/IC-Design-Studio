# Exact second-report storage reconstruction

The second November 10 audit is retained as a lossless cumulative delta against
`source-dispositions-2026-11-08-v1.json.gz`. It does not require the first November
10 report to be materialized and does not change that report or its reader.

From the repository root, choose a fresh output:

```sh
python scripts/reconstruct_source_dispositions_v2.py --output build/source-dispositions-2026-11-10-v2.json.gz
```

The reader checks the historical base, delta and exact reconstructed target
SHA-256 before exclusive creation. No network, upstream execution or repeat
audit is involved. Sufficient memory for the complete report is required.

- Historical base: `ff2a08f3698dcf09d01c38f77bb9f76866e981401ae380e02efac9bc8084a442`
- Delta: `84f25d5ad27fd4567cb6f7c29a6d5750ad55709a52098b79a0800fb1ea1c6e7c`
- Target: `9d0a7241d984fa3b5ad309957e06339c995f88307302dd219e2f236d04c50a56`

The 17,506-byte cumulative storage delta includes 194 added facts, nine changed
file records and nine removed gaps relative to the historical base. These are
transport differences, not a new qualification claim. The scientific comparison
against the first November 10 audit establishes exactly 110 added declarations
from three authenticated GF180 Xschem configurations, with all prior 776,895
items and all 98 remaining gap records unchanged.

The report remains `GAPS`: 777,005 items, 98 inventory gaps, all qualification
and completion flags false. IHP callback and Xschem menu gaps remain open.
See `../validation/chunk7-xschem-config-complete-inventory-2026-11-10.json` for
execution, exact comparison and independent readback evidence.
