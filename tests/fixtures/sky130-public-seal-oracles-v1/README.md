# Public SKY130 seal and Nikon regression oracles

These GDS files were generated with Magic 8.3.684 from unmodified Open PDKs
revision `0ec4fa67eade28cd0a4352c04df981840809427b`. The complete source and
Apache 2.0 license are retained in `../sky130-public-seal-v1`; its source lock
binds every file to the upstream Git blob and SHA-256. `manifest.json` binds
the original Magic output, logs and generation driver. The fixture generation
driver uses the recorded workspace layout and retains every temporary output.

The standalone cross establishes the actual 31 mask-layer shapes and scale.
The 100 by 120 and 400 by 300 micrometre chip-area examples have four matching
marks and a continuous public 6 micrometre seal boundary. Dimensions passed to
the generator exclude the surrounding seal.

The unmodified 100.005 by 150.005 micrometre example is deliberately retained
as a failing boundary control. Rounding each half extent down leaves four
5 nm gaps at the quadrant joins. Its bounding box is plausible, but the full
81:1 region is not the continuous public boundary. The checker must not select
accepted mark windows from that bounding box alone.

The surrounding PDM geometry fills the four corners outside the Nikon
octagon. The octagon, rather than its bounding box, is the comparison domain.
Renamed/flattened geometry is equivalent; cell names alone never grant a pass.

Magic disables DRC during file conversion. These are independent geometry
oracles, not foundry-approved DRC results. A public-template match does not
close the 56 related signoff records, establish final-mask generation, or
qualify chip/scribe placement. The three digital reference blocks contain no
recognized public seal and retain all existing unresolved catalog decisions.
