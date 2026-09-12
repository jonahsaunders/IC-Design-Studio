# README visual sources

The product images are direct Qt captures of IC Design Studio **0.22.0.dev20**, from application commit `e0ae6c56d3de6a32dbdb5ba488b163b81442a5d9`. They are actual UI output, with no painted-in controls, fabricated plots, or generated device geometry. The decorative [banner](../banner.svg) is original, editable SVG artwork, not a circuit or mask design.

| Image | Source and presentation |
|---|---|
| `simulation-dark.png`, `simulation-light.png` | The bundled RC gallery example, after a completed built-in transient run; the two native app themes |
| `example-gallery.png` | The app's nine-entry example gallery |
| `overvoltage-linked.png` | The original generated overvoltage bench, selected on `level_shifter` in Linked views |
| `overvoltage-layout.png` | The same cell in Layout mode, with the Inspector hidden |
| `overvoltage-3d.png` | The same cell in the actual 3D viewer, software rendering, illustrative layer heights, vertical display scale 0.6 |
| `team-review.png` | Local two-client reviewer discussion from `tests/gui_workflow_review.py`; demo participants, no external service or real recipients |

## Reproduce

Install the repository requirements, then run:

```sh
QT_QPA_PLATFORM=offscreen python scripts/capture_readme.py \
  --project /path/to/overvoltage-bench.icproj \
  --out build/readme-captures
QT_QPA_PLATFORM=offscreen python tests/gui_workflow_review.py \
  --out build/readme-review
```

Use a fresh output directory. The first command captures both simulation themes, the gallery, and the detector views. Omit `--project` to capture the bundled example and gallery only. It uses an isolated profile, executes the simulation, and checks that detector inspection changes neither the project document nor its source file. The second command captures `reviewer-threads.png` as part of an actual local reviewer workflow; copy that image as `team-review.png`.

[Capture metadata and image checksums](captures.json) identify the committed screenshots. The detector input came from the `sky130-physical-evidence` artifact of GitHub Actions run **34644511505**, artifact **10281679794**, member `open-project-evidence/overvoltage-bench.icproj`. Follow the [open-project guide](../../OPEN_PROJECTS.md) to generate the project independently.

## Design attribution

The detector screenshots derive from [LDFranck/sky130_vbl_ip__overvoltage](https://github.com/LDFranck/sky130_vbl_ip__overvoltage) at commit `53cf579f63d34227af67f0189b49ee09185f1db5`, by the Von Braun Labs contributors. That design is Apache-2.0; its source and license are recorded in the [project lock](../../../examples/open-projects/overvoltage-lock.json). See [third-party notices](../../../THIRD_PARTY_NOTICES.md). The screenshots preserve the imported geometry and include illustrative 3D presentation only; they do not establish fabrication stack dimensions or new physical qualification.
