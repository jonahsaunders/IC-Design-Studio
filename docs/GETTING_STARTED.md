# Your first circuit

## Bring your own open design

For a larger example after the gallery, follow [real-project import](OPEN_PROJECTS.md).
It covers a hierarchical SKY130 detector, layout attachment, saved native files,
reproducible simulation and explicit LVS findings. Start with the included
examples below if you are still configuring your simulator.

Open IC Design Studio and choose **Your first waveform** from the startup gallery. Choose **Open a copy**, then press **F5**. This small RC circuit uses the included educational solver; it needs no external engine or PDK.

## Read the result

The Results window opens after the run. Select **Waveforms**, enable the output trace and use the plot's marker controls to inspect time and voltage. **Markers…** lets you edit exact coordinates and threshold comparisons. Use **Fit plot** if you lose the trace while zooming.

Press **Ctrl+S** and choose a project filename. Opening from the gallery gives your copy a new project identity so its saved results stay separate from other copies.

## Make the workspace comfortable

| Action | Control |
|---|---|
| Find a command | **Ctrl+K** |
| Run the configured analysis | **F5** |
| Save / save a copy | **Ctrl+S** / **Ctrl+Shift+S** |
| Fit the design | Canvas **Fit** control |
| Change grid or snapping | Canvas status controls |
| Arrange panels | **Window** menu or **Workspace** button |
| Recover the default arrangement | **Window → Reset workspace** |
| Choose another guided circuit | **File → Start here / example gallery** |

The Inspector contains **Properties** and **Analysis**. Results are grouped into **Simulation**, **Waveforms**, **Physical** and **Checks**. The schematic, layout and linked views share the same active cell.

## Try a native simulation

Open **Native divider and studies** from the gallery. The two 1 kΩ resistors divide a 1 V source, so the saved operating-point analysis should report **0.5 V at out**.

This example requires ngspice. It is included in the Windows portable package. For a repository checkout on any platform, install a native ngspice and select the executable in **Tools → Engine diagnostics and paths**. You can also set the `ICSTUDIO_NGSPICE` environment variable. The built-in solver remains available for teaching examples.

Press **F5**, then inspect its run and waveforms. Open **Analysis → Variation cases** to explore parameter studies. For this native circuit, the resistor parameter target is `R1.native.value`. [Native analysis details](UPDATE_0.20.md) explain sensitivity, bounded search and specifications.

## Start your own process design

Choose **File → New project** to open the [Project Hub](PROJECT_HUB.md). Pick a PDK revision, name your project and choose an empty circuit or a template. The included GF180MCU and SKY130 simulation packages appear immediately as **Available offline**; **Install PDK & create project** registers the selected package and starts your design.

The hub's **PDKs** page lists installed revisions, folders and model counts. Use **Add PDK → Find installed PDKs** or **Add folder**, then **Check and register** for an existing local installation, including IHP. Close setup with **Done** to refresh the hub. Open **Devices** in the workspace to place models. The [PDK guide](PDK_GUIDE.md) explains process-specific prerequisites.

Do not link an existing generic layout to a different process just to change the process name. Existing devices and mask layers need a valid mapping; use a new empty project for the first process exercise.

## Bring an Xschem project

Choose **File → Import and migrate Xschem project** and select the top `.sch` file. The review includes dependencies, hierarchy and unsupported constructs. Standard symbols and the included GF180 simulation assets resolve automatically where their references match; custom libraries may still need a folder added. Save the native project to a new filename and run a short reference analysis before editing further.

Migration preserves source material in a recovery archive. It supports an explicit subset rather than arbitrary Tcl-driven symbol behavior. The [migration guide](UPDATE_0.19.md) explains the review states and the [exchange guide](UPDATE_0.20.md) explains returning a native project to Xschem.

## If something gets in the way

| Symptom | Next action |
|---|---|
| ngspice unavailable | Select the native executable in Engine diagnostics; on Windows extract the whole portable package |
| Run failed | Select the failed row in Simulation Explorer and read its log |
| PDK not found | Add the variant or its parent folder; use a tool-ready installation with `libs.tech` |
| Several variants found | Check only the ones you want, then register them together |
| Model file changed | Restore the locked files or register a new revision; use the revision migration workflow |
| IHP model unavailable | Compile compatible OSDI models and select them in Simulation runtime |
| Missing panels | Reset the workspace through the Window menu |

Use the short [examples](../examples/README.md) to separate a setup issue from a larger design issue. Include the version, platform and a small reproducer when reporting a bug.
