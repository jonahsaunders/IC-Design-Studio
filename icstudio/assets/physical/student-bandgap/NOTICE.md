# GF180-B Magic technology for Student Hub

`gf180mcuB.tech` was generated from the Apache-2.0
[open_pdks technology](https://github.com/fossi-foundation/open-pdks/blob/aa3fc215a80d32437b8cca1cb3fdee819d18c4c9/gf180mcu/magic/gf180mcu.tech)
at `aa3fc215a80d32437b8cca1cb3fdee819d18c4c9`. Original copyright and
attribution are retained in the generated file. See [LICENSE](LICENSE).

Preprocessing selects four metals, MIM between M3 and M4, 1 kΩ poly,
and 1.1 µm top metal. The source SHA-256 is
`9ab630331b8711987fa70e8c1db7c521cede2e37c35bc2b289fa7b6836abd525`.
Studio modifies the four PNP extraction declarations to measure the
emitter area and emit collector/base/emitter pins in SPICE order.
The [Banba physical verifier](../../../../scripts/verify_gf180_banba_physical.py)
documents the same correction. The generated technology is only
used by the bandgap labs for capacitance and device readback.
