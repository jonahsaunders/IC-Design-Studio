# Exact report storage reconstruction

The November 10 full audit produced a 23,555,501-byte gzip report, larger than
the publication transport limit. Its lossless storage delta is
`source-dispositions-2026-11-10-v1.delta.json.gz` (8,807 bytes). This is not a
replacement audit, a summary substituted for evidence, or a qualification change.

From the repository root, with Python and the existing historical report:

```sh
python scripts/reconstruct_source_dispositions.py --output build/source-dispositions-2026-11-10-v1.json.gz
```

Choose a fresh output path. The reader authenticates the historical gzip and
delta bytes, preserves unchanged rows and ordering, uses the existing canonical
JSON/gzip serialization, and checks the exact target gzip digest before writing.
It refuses to overwrite an existing output. No network or upstream execution is
needed. Reconstruction requires sufficient memory for the full report.

Pinned SHA-256 identities:

- Historical `source-dispositions-2026-11-08-v1.json.gz`:
  `ff2a08f3698dcf09d01c38f77bb9f76866e981401ae380e02efac9bc8084a442`
- Delta:
  `418fe4b99877317afade4a3717d712ea68b66d2591cd68433635e6499df01503`
- Reconstructed November 10 report:
  `263b17bf6dc2c010e230ded19bb4e0c8c4cc3712b7a321ffc84d5be10d7d7216`

Delta indices refer to the original arrays, not progressively modified arrays.
Insertions occur before the indexed original row; an index equal to the original
length appends. Six insertion groups contain 84 new facts. Six file records are
replaced and six gap records removed. Only changed top-level metadata is stored;
all other content comes unchanged from the authenticated historical base.

The actual reconstructed report was compared byte-for-byte with the original
full audit output. Its status remains `GAPS`: 776,895 facts, 101 inventory gaps,
and all device qualification/completion flags false. The historical report is
unchanged. Seven reconstruction tests cover wrong base/delta, missing/altered
content, target identity, invalid indices, output preservation and exact ordering.
