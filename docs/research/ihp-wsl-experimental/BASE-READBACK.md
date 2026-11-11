# Original base archive readback

The original `base-runtime.tar.gz` is part of the complete lossless proof, alongside
host provenance and builder receipts. It is no longer omitted build scratch.
Only `context/` and the raw `filesystem.tar` export remain explicitly omitted.

This preserves the original compressed bytes and SHA256 for the unchanged host
verifier. The derived experimental payload is not a replacement: derivation
replaces original modules/metadata and repacks gzip, so original bytes cannot be
assumed reconstructible from it.

All existing bounds remain: 3 GiB aggregate proof, 240 MiB per proof ZIP, at most
16 parts, and full chunk/file/archive readback. If the original base plus complete
proof exceeds a bound, delivery fails with explicit incomplete diagnostics. Never
drop the original base or signed proof to force a successful result.

A successful consumer reconstructs every declared proof file, verifies the base
size/hash against DELIVERY and `result.json`, independently authenticates signed
host proof with `verify_ihp_wsl_host_provenance.verify`, and checks reconstructed
experimental payload and cleanup with `check_ihp_wsl_prepared.check`. Archive
inspection and signature/package decoding do not run supplied engines/modules,
install packages, import WSL, or confer native Windows research approval.

This change applies only to its new exact candidate. Earlier deliveries that
omit the original base retain that independent-readback limitation.
