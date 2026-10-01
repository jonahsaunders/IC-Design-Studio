# Student Hub projects

Open **File → Student Hub** for six learning paths and the advanced sensor
acquisition project. The [course guide](../../docs/STUDENT_HUB.md) explains all
41 core lessons, progression, evidence and model limits. The additional
[PDK inverter course](../../docs/STUDENT_INVERTER.md) adds eight lessons per
revision, from schematic and simulation to layout, DRC/LVS repairs and review.
`inverter-course.json` contains its teaching material and checkpoints;
`icstudio.student_inverter` binds separate course instances to exact PDK content.

`curriculum.json` contains the ordered lessons, prerequisite graph, instructions
and checkpoint requirements. `study-guide.json` adds concepts, worked examples,
experiments, interview prompts and portfolio outcomes for every lesson without
changing the grading identity of existing lessons. `icstudio.student_projects` creates independent
editable lesson documents. The four capstone milestones deliberately share one
saved project, with three faults for the student to repair.

Foundations and Analog lessons use the included teaching solver. Digital lessons
need native local Icarus (`iverilog` and `vvp`); Mixed Signal and the capstone also
need native ngspice. Configure **More → Engine setup…** in the Hub. The managed
digital WSL runtime is separate from these electrical/RTL lessons. The new
inverter physical checkpoints can use the included Magic/Netgen runtime. See
[engine setup](../../docs/STUDENT_HUB.md#engines-and-models).

`sensor-reference.icproj` is the **correct reference**, not the faulty teaching
starter. It embeds the SAR and sensor-controller RTL and the native analog
circuit. Run it with **Analysis → Mixed signal → Mixed-signal experiment**.
The [qualification script](../../scripts/verify_student_capstone.py) verifies
nominal conversion, rails, sample retention, averaging and alarm behavior and
detects four deliberately introduced faults.

`sensor_controller.sv` is the original synthesizable averaging/alarm wrapper.
It receives completed conversions from the [SAR controller](../sar-adc/sar_controller.sv).
Editing this source file does not change a project that already embeds its own
copy; edit saved-project RTL through the Digital workspace.

The new design labs include four measured gm/ID exercises, four bounded layout
repairs and three deliberately broken RTL projects with independent testbenches.
Use **More → Export portfolio report** for readable HTML; the JSON learning
record remains the export that embeds saved project snapshots.
