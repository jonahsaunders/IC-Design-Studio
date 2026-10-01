# Four-bit SAR ADC

Open `sar-adc.icproj`, then choose **Analysis → Mixed signal → Mixed-signal
experiment**. See the [walkthrough and simulation contract](../../docs/MIXED_SIGNAL_SAR.md).

The project owns its RTL source and native analog devices. `sar_controller.sv`
is the original controller source used by `icstudio.sar_example.sar_project()`.
Changes to this file do not change a previously saved project; edit its embedded
RTL in the digital workspace, or regenerate the example deliberately.

The default input is 0.93 V, the reference is 1.8 V, and the expected code is 8.
No external PDK is required. ngspice and Icarus run the actual closed loop.
Choose native `ngspice`, `iverilog` and `vvp` under **Local engines**. The managed
digital WSL runtime is not a backend for this experiment; see
[native engine setup](../../docs/MIXED_SIGNAL_SAR.md#local-engine-setup).
