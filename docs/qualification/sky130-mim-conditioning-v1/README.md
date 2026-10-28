# Public fixture provenance and licenses

`fixture-bundle.zip` is a deterministic finite qualification input bundle containing 40 generated deck templates and 346 source files. It is not a distributable ngspice runtime. Apache-2.0 SkyWater PDK model sources retain their original in-file notices. IC Design Studio derivative adapter files retain their GPL-3.0-or-later notice. `LICENSE-APACHE-2.0.txt`, `LICENSE-GPL-3.0.txt` and `NOTICE.txt` are retained alongside the bundle. The physical inputs are the source project's generated qualification fixtures, not user-private inputs.

The v2 manifest differs from the earlier portable fixture by omitting exactly one unreferenced staging metadata file. The input difference record gives the two fixture manifest hashes, the omitted metadata hash and exact counts; the native source/deck bytes are unchanged. The public bundle excludes historical personal paths and reconstructs without an external archive.
