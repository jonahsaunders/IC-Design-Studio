# IC Design Studio 0.22.0.dev15 — engineering preview

Dev15 adds [shared schematic editing and review](SCHEMATIC_COLLABORATION.md). Update
the server and all desktop clients together; the collaboration protocol and
server database are version 2. The earlier feature notes below remain applicable.

Dev13 groups all collaboration tools under **Tools → Collaboration**. The
dashboard discovers recent sessions, restores expired ownership with administrator
authorization, shows reservation owners, and reviews conflicting shapes before
safe reapplication or saving a separate copy. Owned workspaces can be deleted
after saving the exact shared revision. Idle presence polls no longer rewrite
the full recovery journal. See [the collaboration guide](LIVE_COLLABORATION.md).

The candidate also includes the [3D layout viewer](LAYOUT_3D.md) and live desktop
collaboration from experimental PR #13. This version identifies new source and
must qualify its own packages; the earlier dev12 draft contains different code.

The dev12 update adds [larger hierarchical layouts, schematic-driven review and concurrent cell/layer editing](LAYOUT_SCALE_AND_COLLABORATION.md). Review that guide for supported recipes, conflict handling and operation limits.


This preview makes the existing design workflows reproducible as release gates.
It includes the project hub, bundled GF180MCU/SKY130 simulation subsets, reviewed
native migration, and the layout editing improvements from the 0.22 series.

## Changes

- Scalar bus waveform selectors now quote names such as `data[0]` when emitting
  ngspice control expressions. This prevents an array-index expression from
  replacing the intended circuit node.
- A three-level, reused RC hierarchy exercises parameter overrides, live shared
  expressions, connected moves, exact undo/redo, removal of the original source,
  save/reopen and two Xschem/native round trips. Independent flattened circuits
  and analytic complex transfer functions check both output channels.
- Windows and Linux packages are extracted and executed with isolated application
  settings. Release payloads include matching source, numerical and desktop
  evidence, exact commit identity and SHA-256 inventories.
- Public, checksummed SKY130 archives recreate a committed adapter lock. The
  physical gate checks a nominal inverter and deliberate narrow-metal, route-open
  and channel-length faults with real Magic, Netgen and ngspice.
- Desktop, interoperability and physical workflows run for every PR and pushes
  to `main` and `experimental`. A separate manual workflow creates a draft
  prerelease only after all three workflows pass on the same commit.

## Validation and supported scope

The attached platform validation JSON and evidence archives identify the exact
release commit, host, asset hashes and executed checks. Consult those records
before promoting this draft. The earlier dev10 hosted baseline is preserved in
[the release status](RELEASE_STATUS.md); its results do not qualify new binaries.

Windows CI uses Windows Server 2022. The installer probe covers installation to
a path containing spaces, execution at 100/150/200% scaling, Start-menu shortcut,
file association and uninstall. The extracted portable app is tested separately.
Linux CI uses Ubuntu 24.04 with offscreen Qt; its archive targets that platform.

Fresh Windows 10/11 consumer-machine testing, interactive Linux display checks,
upgrade acceptance, screen-reader/accessibility review and signing remain
separate release checks. macOS has no qualified binary in this preview. The
native hierarchy fixture covers scalar bus members; vector-bus expansion still
requires explicit review. The physical fixture covers only the locked SKY130
subset and named cases. It does not establish foundry signoff, all corners,
arbitrary PCells, distributed-RC accuracy or other process families.

## Downloads

Use the Windows installer or extract the complete portable ZIP. On Linux,
extract the complete tarball and run `ICDesignStudio/ICDesignStudio`. Keep the
runtime directories beside the executable. Each platform has a matching source
ZIP; the Windows source includes its staged ngspice runtime. Check the final
`SHA256SUMS-0.22.0.dev13.txt` before use. See [download guidance](DOWNLOADS.md).
