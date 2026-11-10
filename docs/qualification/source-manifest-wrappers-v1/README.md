# Exact setup manifest and include-only KLayout sources

These unchanged pinned files support declarations, not installed tool capability,
LVS execution or device qualification. `source-lock.json` preserves all three
source identities. The two separately accounted SKY130A/B archive members have
identical bytes, retained once as `sky130.lylvs` including original CRLFs.

`tools.txt` lists eight setup targets from the pinned open-pdks repository, whose
root Apache-2.0 license is retained. The SKY wrapper carries its own Apache-2.0
notice and Efabless 2022 copyright. Its only body directive includes `sky130.lvs`;
that dependency is neither resolved nor executed here. Empty prolog/epilog,
autorun flags and every XML metadata field are explicitly retained as facts.

The binary gmon inputs, ambiguous gate lists, geometry chains and dynamic
configuration files are not covered. Neither enumeration nor source presence
closes implementation, electrical, physical, calibration or release gates.
