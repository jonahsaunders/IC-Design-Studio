# Public Tiny Tapeout density reference

`met_density_tiled.drc` and `LICENSE` are unmodified files from
[Tiny Tapeout 10](https://github.com/TinyTapeout/tinytapeout-10/tree/46f0a2f45c3b1fcc27aac7acb7faa054631d9955),
under Apache-2.0. `source-lock.json` records exact Git blob identities, sizes,
SHA-256 hashes and upstream paths. The checker contains DLindley's July and
September 2024 explanation of its metal-growth values.

Studio's GPL-3.0-or-later implementation is an adaptation with exact integer
areas, explicit physical units and declared bounds, inclusive endpoint windows,
and separately reported clipped windows. It preserves the upstream checker
profile and the distinct growth values attributed to SkyWater in its comments.
Those comments are not a separately authenticated foundry specification.

The original checker is retained for independent execution. On the retained
controls it omits exactly aligned endpoint windows, and its centered tile grid
can clip denominator and numerator differently at a frame edge. Studio's
explicit window calculations intentionally do not reproduce those behaviors.
No file here constitutes foundry signoff or resolves PDK-version applicability.
