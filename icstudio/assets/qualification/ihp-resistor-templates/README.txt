IHP selected resistor geometry templates

Derived from the public IHP SG13G2 Magic resistor generators, copyright 2025 IHP PDK Authors, Apache-2.0; see LICENSE and UPSTREAM-LOCK.json. provenance.json identifies the reviewed package, each retained generator GDS, each application baseline GDS, and each source project. templates.json contains only normalized physical shapes and terminal anchors, without native labels or environment-specific paths. Its SHA-256 is verified before every use and saved with the footprint specification.

The 15 vias=0 cases are native Magic geometry. The 15 vias=1 cases add local Metal2 landing rectangles where the public M2.d minimum-area rule requires them: preserve each rectangular terminal height and extend both horizontal sides equally in 5 nm increments until the area reaches 144000 nm². All other masks remain unchanged. Resistor terminal anchors move to Metal2; the independent body remains on Metal1, with every guard-via control set to 0.

The public generator defaults vias to 1. The application deliberately defaults to Metal1 access (vias=0), preserving the previously reviewed application behavior. These are finite W/L samples, not a continuous geometry, electrical, fabrication, or full-device qualification. Run physical verification on each design.
