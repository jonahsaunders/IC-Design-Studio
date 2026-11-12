# Historical openEMS runtime source

The retained module is byte-identical at the original GF180 acceptance commit
`2fe3c277c666089b21b4ebf39aecd62a76a3ae8d` and pre-repair candidate
`19dfbe2af822f1ea60ce1606007aeec2e1b9f388`. Its SHA-256 is
`cde41317ac8710d2d189f881b16bdfe53f4fe5f841f4ee7de215582315546a18`.

The new manifest retains every prior historical binding and adds this module
so the old GF180 production evidence continues to authenticate its original
source. The acceptance record, thresholds and qualification scope are unchanged.
This file is evidence, not the runtime loaded by the application. Current
solver-import immutability is tested separately; old production acceptance does
not apply retroactively to the bytecode-write repair.
