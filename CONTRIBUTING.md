# Contributing to IC Design Studio

Help make open circuit design easier to learn and more dependable. Small, well-described changes are welcome: a reduced circuit that reveals a bug, a PDK adapter test, an accessible interaction, or a clearer walkthrough.

## Set up

Use Python 3.12 and the virtual-environment instructions in the [README](README.md). Install `requirements-build.txt` if working on packaging. Keep simulator and PDK dependencies explicit; do not commit installed environments, native binaries, private projects or full PDK trees.

## Find the relevant code

| Area | Location |
|---|---|
| Startup, gallery and PDK assistant | `icstudio/onboarding.py`, `icstudio/getting_started.py` |
| Native migration, analyses and exchange | `icstudio/native_*.py` |
| PDK catalog and revision locks | `icstudio/pdk_import.py`, `icstudio/pdks.py`, `icstudio/catalog.py` |
| Simulation scheduling and waveform UI | `icstudio/simulation_workspace.py`, `icstudio/run_manager.py`, `icstudio/plot.py` |
| Physical mappings and verification | `icstudio/native_physical.py`, `icstudio/process_adapters.py`, `icstudio/klayout_verification.py` |
| Examples and tutorials | `examples/`, `docs/` |
| Release automation | `scripts/`, `.github/workflows/` |

## Make a focused change

Describe the user-visible outcome. Preserve project identities, revision links and undo/recovery behavior. Keep parsing and numerical work separate from Qt where practical. For new formats or models, define the supported subset and reject unsupported constructs with an actionable explanation.

Add a meaningful regression for changed connectivity, units, parser behavior, job lifecycle or numerical results. A tiny reproducible circuit is preferable to a long simulation. Documentation-only changes need link and presentation checks, not artificial implementation tests.

## Validate

```sh
python -m unittest discover -s tests -v
python scripts/check_release.py
```

For the new-user workflow, use an installed ngspice and run:

```sh
QT_QPA_PLATFORM=offscreen python tests/gui_getting_started.py --evidence build/getting-started-evidence
```

On PowerShell, set `$env:QT_QPA_PLATFORM = 'offscreen'` first, then run the Python command without the shell assignment prefix. Set `ICSTUDIO_TEST_NGSPICE` if the test simulator is not on PATH. Use a fresh evidence directory for workflows that create fixture trees.

Do not claim external engine or platform qualification from parser fixtures or packaging alone. Record the actual command, engine version, model revision and expected numerical result.

## Submit and review

Use the pull-request template to explain why the change is needed, its behavior and tests. Include a screenshot for material interface changes. Keep product text focused on open-source tools and this project's own design. Preserve all required third-party notices and use only assets you can redistribute under their stated terms.

The [roadmap](docs/ROADMAP.md) describes larger priorities. For a broad feature, start with an issue and a concrete acceptance example so its scope can be reviewed.
