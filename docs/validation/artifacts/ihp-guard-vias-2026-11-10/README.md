# Finite IHP guard-via evidence

The three `guard-vias-v1-*.zip` files retain the original native-source run.
It is a partial result with three all-side100% DRC failures, not a passing
qualification. The three `guard-corner-safe-v2-*.zip` files retain the explicitly
corrected routing run and the original failed all-side inputs. The corrected
profile passes42 positive layouts and105 intended fault rejections, not a full
family, installed-package or foundry qualification.

For each version, its `split-map.json` binds the exact size/hash of each ZIP
and maps every uncompressed member. Use all three parts together in a fresh
folder. Their disjoint member union is identical to the corresponding retained
full ZIP, including its original manifest; the original full ZIP itself is not
duplicated here. Each part is incomplete alone. Do not concatenate these ZIPs.

The compact full bundles explicitly omit tool/compiler/runtime binary bytes and
raw baseline-run outputs. Exact provenance, hashes, build logs, licenses and
baseline receipts are retained, but these are not self-contained or
relocation-independent executable toolchains. All new-run native inputs,
outputs, successful checks and deliberate failures remain included.

For the corrected run,84 fault controls reach native LVS rejection. The other
21 guard shorts collapse the extracted port interface to B and are rejected
before LVS, not misreported as successful fault-producing tool launches.
See the parent validation records for source hashes, scope and limits.
