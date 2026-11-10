Explicit corner-safe IHP resistor guard routing, template revision v1.

Models: rsil, rppd, rhigh; W/L 2/7 micrometres, one straight device.
Resistor terminals remain Metal1; body access is actual Metal2.
Opt-in corrected routing, NOT unchanged native PDK masks or foundry signoff.
The all-side raw native generator has retained corner DRC failures. This
profile adds exactly 0.25 square micrometres of Metal2 at the four outer
corners and redistributes the two vertical via rows: 56 total vias become54,
with190 nm cuts and220 nm spacing. All horizontal vias and other device
layers remain unchanged. No Metal2 resistor-terminal combination is supported.

Source native evidence report SHA256:
46cf624f183d76bad3b8b33f0bf04f3e7a1c427d918c1d779b6a152e44de8111
The42-positive/105-control native experiment is geometric source evidence,
not acceptance of an installed application. The app uses only its three
all-side corrected templates, with separate UI/lifecycle validation.

Reproduce with scripts/build_ihp_guard_app_templates.py using the retained
immutable guard-corner-safe-attempt-2 evidence directory. Templates include
source case, mask, contract and tool profile identities.

Original public IHP generator geometry: Copyright2025 IHP PDK Authors,
Apache License2.0. See included Apache-2.0.txt. The additive conditioner is
identified by its exact source SHA256 in templates.json.
