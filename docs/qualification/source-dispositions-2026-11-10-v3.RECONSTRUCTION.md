# Exact third-report storage reconstruction

This lossless cumulative delta uses the original November 8 report. It preserves
both earlier November 10 reports and their reconstruction tools unchanged.

From the repository root, choose a fresh output:

```sh
python scripts/reconstruct_source_dispositions_v3.py --output build/source-dispositions-2026-11-10-v3.json.gz
```

The reader verifies the exact historical base, delta and reconstructed target
before exclusive output creation. No network, upstream execution or new audit
is involved. Sufficient memory for the complete report is required.

- Base: `ff2a08f3698dcf09d01c38f77bb9f76866e981401ae380e02efac9bc8084a442`
- Delta: `e64538d28e8d6ded351f19889415f7c516a80eb32b446fdaab997c5cdeb1f772`
- Target: `426b8e9b69c270dab32e5aba29e6302c99ee44d4e8c6df26714bd6cb34189448`

The 19,123-byte cumulative storage delta transports 234 added facts, ten changed
Git file records, two changed SKY accounting records and twelve removed gaps
relative to the historical base. These are storage differences, not new device
qualification evidence.

The scientific comparison against November 10 v2 establishes exactly 40 added
facts: eight setup target names and sixteen metadata/include/role facts per
SKY130A/B wrapper. All 777,005 prior items and all 95 remaining gap records are
unchanged. Full output remains `GAPS`: 777,045 items, 95 gaps, no qualification
or completion promotion. Source identities and unresolved dependencies remain
explicit. See the source-manifest complete inventory validation record.
