# Locked upstream file and tool-view inventory

The [October 20 record](validation/upstream-views-2026-10-20.json) inventories
every file in the pinned IHP repository and its five linked repositories, the
pinned GF180 primitive repository, and the retained SKY130 common and primitive
archives. Windows and Linux produce byte-identical reports. Chunk 7 remains open.

| Source scope | File entries | Comparison target |
| --- | ---: | --- |
| IHP SG13G2, including all five submodules | 6,210 | IHP bundled package |
| GF180 primitive repository | 1,028 | GF180 C and D packages separately |
| SKY130A common and primitive archives | 2,981 | SKY130A bundled package |
| SKY130B entries in the same archives | 2,984 | Explicitly outside the target process |

These 13,203 entries include documentation, measurement data, tests, generators,
tool configuration and library views. They are **file counts, not device counts**.
The complete [file report](qualification/upstream-views-2026-10-20.json.gz)
preserves each path, repository or archive, content identity, size, directory
group and comparison result. All seven repository identities and five submodule
edges are retained. The [source metadata](qualification/upstream-view-inputs-2026-10-20.json.gz)
is sufficient to reconstruct and verify every Git tree without another network
request. Both compressed files together occupy about 1 MB.

## What the comparison establishes

Each bundled package file must match its manifest before comparison. A source
file matches only if its Git blob identity equals a bundled file's actual bytes;
relocated originals are recorded by their current paths. Names alone never
establish a match. Symlink objects do not match ordinary file contents.

There are 237 IHP source entries with identical bytes in the IHP package, 74
GF180 entries in each C/D package, and 388 SKY130A entries in its package.
Repeated upstream content can match the same bundled file. The remaining rows
have no identical file in that package. This is not a count of missing supported
devices: many are examples, alternate tool views or measurements, and some have
explicitly recorded local derivatives. Additional verification assets elsewhere
in the application are also outside this particular package-file comparison.

The report separately lists package files without an identical source entry.
No unsupported item becomes supported through a file match. The inventory does
not interpret model terminals, voltage/temperature limits, PCell parameters,
extracted-device mappings, process options or licenses as interchangeable.

## Integrity and replay

Every Git tree is reconstructed from its complete entries and checked against
its pinned tree hash. Each submodule must match both its parent's gitlink and
the URL in the verified `.gitmodules` blob. Missing, extra, unreachable or
changed repository records fail. Commit-to-tree associations are explicitly
pinned from retained GitHub commit API responses; commit-signature verification
is not claimed.

The two SKY130 archives must match their release hashes before and after reading.
Every member is streamed and hashed without extracting the archive. Duplicate,
unsafe, nonregular or unexpected process paths fail. The actual pinned archives
contain only regular files. The audit does not silently skip other member types.

Install `zstandard==0.23.0` into a separate audit environment, then run:

```text
python scripts/inventory_upstream_views.py --tree-inputs docs/qualification/upstream-view-inputs-2026-10-20.json.gz --sky130-cache /path/to/retained/archives --output /path/to/new-inventory.json.gz
python -m unittest tests.test_upstream_view_inventory tests.test_primitive_inventory -v
```

The cache must contain `common.tar.zst` and `sky130_fd_pr.tar.zst` from release
`sky130-fa87f8f4bbcc7255b6f0c0fb506960f531ae2392`, with the hashes in the existing
SKY130 `UPSTREAM-LOCK.json`. The runner uses the current bundled packages and
records their identities; changed packages intentionally change the report.
Its gzip output has no timestamp, filename or host-specific absolute paths.

The fifteen focused tests on each host include omitted/changed Git objects,
missing/wrong gitlinks, altered `.gitmodules`, duplicate/unsafe archive members,
wrong archive hashes, altered bundled bytes and misleading filename matches.
The real compressed releases also pass full inventory execution on both hosts.

## Remaining scope

This closes file enumeration for the named inputs. It does not close the full
source-completeness requirement: SKY130 standard-cell/other library archives,
other GF180 repositories, and semantic device/process-option disposition remain
separate work. The IHP tree includes the public openEMS and Palace integrations,
which are now explicitly inventoried; their presence is not an electrical
inductor model or a validation result. No third-party model or solver source is
copied or relicensed by this inventory.

Required unavailable models, complete supported operating envelopes, broader
physical/extracted connectivity and exact installed-release acceptance still
prevent completion of chunk 7.
