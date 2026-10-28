# IHP straight resistor terminal-via source class

October 28, 2026. The selected `rsil`, `rppd`, and `rhigh` terminal-via class
passes full native DRC and strict unique LVS for five existing W/L samples
(`0.5/0.5`, `0.5/20`, `20/0.5`, `2/7`, `7/2` micrometres), at 0 and 90 degrees.
All 30 saved/reopened and independently rewritten GDS/OASIS layouts preserve
their actual extracted model, R1/R2/B identity, and dimensions. Ninety physical
and schematic controls are detected. This is selected source qualification;
it does not close the resistor family or installed application acceptance.

The current physical package is `cfb96b74cf33877e`, manifest SHA-256
`da58ba2de122d67d232ab20ca4fb353b70bdc68c00ef4279f9be7da640a68ae0`.
Its public Apache-2.0 Magic generator offers a Boolean `vias` checkbox:
`0` leaves terminal contacts on Metal1; `1` adds Via1 and Metal2 above both
resistor terminal contacts. It does not select arbitrary higher stacks.
Guard-ring `viagb`, `viagt`, `viagl`, and `viagr` coverage remains explicitly
zero; those independent options are a separate uncovered class.

The untouched `vias=1` run retains all 15 cases: nine pass and six narrow-width
cases fail Metal2 area checks. The native generator's `via1_draw` documentation
explicitly assumes that routing will supply the upper metal area. These raw
failures remain failed. The historical October 17 Metal1-only acceptance and its
older package revision retain their own scope.

The named local `m2-landing` view supplies that routing area. The exact pinned
M2.d rule requires 144000 square nanometres (0.144 square micrometres). For each
native rectangular Metal2 terminal below that area, it preserves the rectangle's
height and extends both horizontal sides equally by the smallest 5 nm amount
that reaches the rule. The two narrow `rsil` terminals grow from 360 × 300 nm to
480 × 300 nm; `rppd` and `rhigh` grow from 380 × 360 nm to 400 × 360 nm. Only
Metal2 is added. XOR checks preserve all other masks and require original Metal2
to remain a subset. No generator, native rule deck, model or package is changed.

The access view relocates R1/R2 labels and ports to their actual Metal2 landing;
it removes the original lower labels so they cannot conceal an open stack.
B remains an independently contacted Metal1 guard port. The metal/contact graph
checks distinct R1, R2 and B conductors, lower-material/contact/M1 support, and
actual M1/Via1/M2 paths. Resistive poly is never treated as an ideal wire.

Every case includes terminal-open, body-open, terminal-short, wrong-width,
wrong-model and missing-Via1 controls. Removing R1 Via1 cuts leaves DRC clean
but changes the native resistor's R1 node to an actual floating node and fails
LVS. Removing guard contacts changes B alone to a floating node and fails LVS.
The short control produces an independently checked native shorted-interface
extraction. All controls retain original geometry/model dimensions except the
explicitly changed mask or reference. A separate reader inspects actual streams,
native logs and all extracted netlists without importing the qualification runner.
Its explicit checks remain active under Python optimization. Archive readback
requires external archive/manifest hashes and verifies the complete object inventory.

Reproduce with a new output directory and the pinned native tools:

```sh
python scripts/qualify_ihp_resistor_layouts.py --output /new/via-results --magic /path/to/magic --netgen /path/to/netgen --vias 1 --access m2-landing --workers 3
```

The legacy default remains `--vias 0 --access native`; its fresh final regression
passes 30 layouts and 75 controls. `--access m2` preserves native masks and only
relocates ports; it does not repair narrow Metal2 area failures. Both Windows and
Linux pass 14 focused regressions. Native execution uses the existing ordinary
Ubuntu user in WSL; native Windows or installed desktop acceptance is not inferred.

Actual application resistor recipe/editor exposure and its fresh place/edit/save/
reopen/export workflow are a separate subsequent candidate. Continuous geometry
domains, snake/array variants, guard-via coverage, alternate isolation/guard options,
operating/statistical/reliability envelopes, electrical linkage and complete family
closure remain open. Chunk 7 stays approximately 70% complete (55–80%, low
confidence); that is an engineering estimate, not verified acceptance.
