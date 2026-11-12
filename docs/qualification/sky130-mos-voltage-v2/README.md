# SKY130 source-defined MOS voltage screen, current package contract v2

This static, qualification-only library classifies source-relative VDS, VGS and VBS against the model-validity ranges stated in the retained SKY130 public documentation. It does not restrict simulations or establish absolute maximum ratings, rated operating limits, temperature limits, safe operating area, PCell geometry limits, reliability or a complete operating envelope. It does not promote a device status.

The reviewed source defines 17 model identities: 16 have 40 catalog bindings in the prepared `5dda725c94efe3c2` package, while the ESD PFET is source-only and has no asserted catalog binding. Four ambiguous ESD identities are outside this finite contract. The isolated high-voltage device's fifth substrate terminal has no independent bound established here. The two 16 V drain allowances apply only at exactly zero VGS and remain subject to separate source-required SOA.

Historical bias sweeps cover discrete points in 11 models under package revision `1901822ae8f81ae1` at three temperatures and five corners. Axis spans and sample counts identify that earlier evidence; they do not claim that a continuous interval or a point under the current package was simulated. TNOM is a model parameter, not a temperature operating range.

Public documentation is SkyWater PDK, revision `7198cf647113f56041e02abf3eb623692820c5e1`, Apache-2.0; see retained `sources/LICENSE`, `sources/NOTICE.txt`, `sources/device-details.rst`, and `sources/hv.rst`. Source paths, locations and SHA-256 values are recorded in the retained locks and each model-validity fact. Current package model-file hashes authenticate packaged bytes; they do not claim every packaged file is byte-identical to an upstream public tree.

The v2 catalog lock binds the unchanged public criteria, 17 models and 40 aliases to package manifest `125cde7c313ee18a05a7ec5c280d514b99aea521d6b39476e44f486ae494153b`. Its v1 predecessor remains unchanged. The corrected ESD catalog entry has no reviewed voltage definition here and adds no voltage-screen coverage.

The immutable gap table and public source lock retain their original bytes and candidate labels. The [earlier combined source check](../../validation/chunk7-final-integration-2026-10-28.json) retains its original package scope. This v2 preparation grants no new native or installed acceptance: current-package electrical coverage remains `NOT_ESTABLISHED`.

Instantiate `QualificationVoltageContract` in an explicit qualification/reporting workflow. Call `screen` with an exact model or catalog key and source-relative voltages and temperature. The package, catalog lock and model sources must match one exact reviewed version pair before screening. No default simulation path or completion gate changes.
