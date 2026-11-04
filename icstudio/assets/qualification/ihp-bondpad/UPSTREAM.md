# IHP square bondpad source material

Unmodified public files from `IHP-GmbH/IHP-Open-PDK`, commit
`5e6d592e4002946a4616f798c357f0f3c06cf3b6`, Apache-2.0. The original copyright
headers and complete `LICENSE` are retained. `source-lock.json` gives the exact
upstream paths, public URLs, Git blob SHA-1, SHA-256 and byte length for each
file. The lock itself has SHA-256
`0811e348eb273f5827ff3f7ffb5fa32a7380f8ba53189a4c3004816c04661895`.

`bondpad_code.py` supplies the selected square, TM2, unstacked, unfilled,
non-flip-chip branch without filler exclusion. `sg13g2_tech.json` supplies
the 5 nm grid, 80 um default diameter and 2.1 um passivation enclosure.
`utility_functions.py` supplies the public floor/grid arithmetic. `sg13g2.lyp`
supplies the mask and purpose meanings.

The application generator is a separate implementation. The qualification
oracle executes the authenticated public `genLayout` method with a restricted
rectangle-call recording adapter; it does not claim to execute the complete
CNI/PCell materialization path. The recorder retains `pin#=1` and `ignore=TRUE`.
The adjacent public source comment says zero pins and calls the value one
unexplained; the selected branch emits no pin object. The application's named
center port on TM2/pin is an explicit adaptation, not an inferred upstream pin.

`sg13g2_bondpad.lib` is retained to keep the electrical blocker concrete. It
declares one `PAD` terminal and parameters, but contains no circuit elements.
It is not installed as a new electrical model. The unavailable catalog binding
is unchanged. No substrate terminal, ideal element, fitted parameter or rated
operating limit is supplied by this physical recipe.
