# Chunk 7: RF qualification and hosted-job recovery

The October 23 review of `b4e00d9` found nine successful hosted workflows,
four failed workflows and three cancelled workflows. Push and pull-request
runs are counted separately. The prior pending snapshot was not acceptance.

The Windows RF branch check and Linux reverse-bias check still required the
previous SKY130 default manifest. The new MiM metadata revision left the RF
corner files unchanged, but those standalone qualification entry points had
not adopted the historical-package reconstruction already used by the RF
candidate builder. The transient runner had the same defect downstream.

All three runners now capture the original `tt`, `ss` and `ff` corner bytes
through that reconstruction. They require the exact historical manifest and
check each input hash before using it. Reports bind both the selected current
manifest and the original RF manifest. Unknown revisions and changed or missing
corner inputs remain rejected. Public model files, electrical equations,
stimuli, fault controls and numerical tolerances are unchanged.

Both Windows and Linux pass the complete existing batches:

| Batch | Verified result on each host |
| --- | --- |
| Branch equations | 360 cases: 90 valid and 270 detected faults; repeated AC after DC |
| Reverse bias and noise | 360 cases: 90 valid and 270 detected faults; seven sequential bias points |
| Nonlinear transient | 90 conditions: 180 valid refinement runs and 270 detected faults |
| Application integration | Both RF interfaces, independent DC/AC references, polarity/width faults and six automatic runtime checks |
| Focused regressions | 21 tests pass, including exact historical inputs and altered/missing corner rejection |

An independent inventory audit verifies 8,730 retained raw files on each host,
the result/control counts and matching historical input hashes. This audit
checks retained-file integrity; it does not independently establish measured
RF model accuracy. The native runners retain their earlier equation oracles.

The initial Linux execution selected the ordinary `/opt/icstudio/bin/ngspice`,
which failed the existing explicit-area runtime guard. That attempt is retained.
The complete rerun uses the exact earlier RF-compatible engine, verifies its
behavior again, and passes. The guard was not bypassed and no engine was changed.

Two separate hosted infrastructure problems also prevented acceptance. The IHP
workflow exhausted its 60-minute total while its existing device gates were
still running. Its total is now 120 minutes, preserving every existing test
and individual gate timeout. One GF180 reference job exhausted 210 minutes
inside package installation before any extraction ran. The affected setup
steps now have a 20-minute bound, explicit download timeouts and bounded retries.
Index-update errors fail the setup step; they cannot be treated as successful
qualification. The settings follow the documented
[APT retry options](https://manpages.debian.org/bookworm/apt/apt.conf.5.en.html),
[HTTP timeout](https://manpages.debian.org/bookworm/apt/apt-transport-http.1.en.html)
and [update error handling](https://manpages.debian.org/bookworm/apt/apt-get.8.en.html).

Workflow lint passes locally. These workflow changes still require a fresh
hosted run; local success is not evidence that the hosted failures are closed.
The [execution record](validation/chunk7-ci-recovery-2026-10-23.json) retains
source hashes, raw-result bindings, original failures and archive identity.

This repairs qualification reproducibility and removes known CI impediments.
It does not promote the RF candidates or any device status. Seven unavailable
required bindings, complete operating ranges, wider physical/process-option
coverage and final installed acceptance still keep chunk 7 open.
