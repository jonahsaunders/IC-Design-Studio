# GF180 substrate and diode comparison recipe

`scripts/prepare_gf180_lvs.py` prepares a reproducible copy of the GF180 LVS
rules used by the [connectivity controls](validation/gf180-connectivity-controls-2026-10-09.json).
It authenticates 32 source files, preserves attribution and records the original
and prepared hash of every file. The source checkout remains unchanged, and an
existing output directory is rejected.

The upstream repository is
[GlobalFoundries GF180 physical verification](https://github.com/efabless/globalfoundries-pdk-libs-gf180mcu_fd_pv),
pinned to `05e7b6adf19edf942969c1c9625f02fd87874f06`. Its required files are listed
in the [source lock](../examples/gf180-lvs-source-lock.json).

```sh
python scripts/prepare_gf180_lvs.py --pv ../gf180-pv --output build/gf180-lvs
```

The output contains the attributed source files, `source-lock.json` and
`recipe.json`. Its rule entry is `klayout/lvs/gf180mcu.lvs`. A successful command
means preparation completed; its record remains `prepared_not_qualified`.

## Reviewed changes

Only two rule files change:

| File | Change and purpose |
|---|---|
| `rule_decks/general_connections.lvs` | Attach the physical p-substrate taps to the substrate with `soft_connect_global`. Replace the wildcard implicit join with strict top-level mode. |
| `gf180mcu.lvs` | Before comparison, require the supported antenna diodes' area and perimeter to participate in matching on both extracted and reference netlists. |

The upstream `sub` layer is an initially empty polygon layer populated by
extracted bulk terminals. Connecting only that layer globally does not attach
every physical substrate tap. KLayout documents global soft connections as the
mechanism for substrate contacts while checking that high-resistance substrate
paths do not replace wiring. Its implicit connections can join disconnected
shapes by name; strict top-level mode treats unresolved must-connect findings
as errors. See the [KLayout connection reference](https://www.klayout.de/0.29/doc/about/drc_ref_netter.html)
and [substrate example](https://klayout.de/doc/manual/lvs_intro.html).

The diode guard checks class, terminal and parameter definitions before making
area and perimeter mandatory. It rejects unexpected custom comparison policies.
The separate [CDL adapter](../scripts/gf180_cdl_diodes.py) converts the supported
positional diode records without changing their terminals or geometry. Native
comparison requires both the adapter and the guard when these records occur.

## Acceptance requirements

The recorded reference scope is GF180 C/D, 5LM, using the 9-track standard-cell
library. C uses the 9K top-metal setting and D uses 11K. Other devices, metal
stacks and operating workflows retain their own qualification requirements.

Run with an authenticated, compatible KLayout executable. The native reference
controls use KLayout 0.30.5. Engine version text or successful preparation alone
does not prove that the rules executed correctly.

Require **both strict LVS and independent metal continuity**. The whole-layout
controls demonstrate that LVS alone can miss a disconnected power port, while
a metal-only check cannot detect a missing substrate contact. Preserve all
extraction diagnostics and require the expected device, parameter, terminal and
port coverage. A generic engine error or a missing comparison database is not
proof that a physical fault was detected.

This command prepares the rule directory; it does not install a runtime, run a
project comparison or change a project's acceptance status. Consumer-flow
integration, installed acceptance, complete fill coverage and post-fill
function/timing remain required by the [qualification plan](PDK_QUALIFICATION_PLAN.md).
The upstream stock-deck results remain available separately. No foundry waiver
or tapeout qualification is implied.

The [preparation checkpoint](validation/gf180-lvs-preparation-2026-10-09.json)
records both-OS byte equality and 24 focused tests per OS, plus the 1,557-test
Windows suite (62 skips). Four fresh counter controls reproduce their expected
results. A fresh APB run exceeded the initial 300-second execution allowance;
its failure is retained, and APB continuation remains pending.
