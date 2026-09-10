# IC Design Studio 0.2.1

## Dark by default

The application starts in dark mode, including when upgrading from the old default-light setting. Graphite panels, a darker canvas, quieter grids, brighter secondary labels, and higher-contrast error text refine the appearance. Light mode remains available through View → Toggle light / dark; an explicit choice made in 0.2.1 is remembered.

On Windows 11, native title-bar dark appearance and caption/text colors are requested using the supported DWM attributes. Normal window controls are retained. The native frame path has not been exercised on a Windows host in this build environment.

## Windows simulation fix

The screenshot's `python.exe — Bad Image` error named `icstudio/libiccore.so`. The old loader incorrectly tried Linux, Windows, and macOS filenames on every operating system. The source ZIP also contained a Linux build artifact.

The updated loader chooses only the current platform's native filename. On Windows it considers only `iccore.dll`, rejects foreign file formats and mismatched CPU architectures before loading, and falls back to the Python solver when a compatible native core is unavailable. Source archives now exclude compiled native binaries. Frozen application packaging includes only the host platform's core.

No extra compiler is needed to run the Windows source launcher. The Python solver can perform the preview's supported analyses; a compatible locally built native solver is optional. The source package does not contain a prebuilt Windows executable.

## Update on Windows

1. Close IC Design Studio and dismiss the old error dialog.
2. Extract `IC-Design-Studio-0.2.1-Source.zip` into a new folder.
3. Open that folder and double-click `launch-windows.bat`.
4. Open your saved `.icproj` through File → Open project.

The launcher uses the installed Python and sets up its local dependencies. Keep your saved project files. There is no project-schema change in this update. Even when older Linux binaries remain in an existing source folder, the new Windows loader does not attempt to load them.

## Job feedback

Run shows a running state while a worker executes. Completion, cancellation, and failure restore the Run control and show the corresponding status. A failure points to the job log and is also reported in Analysis settings, instead of leaving a misleading running state.

## Validation

- 31 core tests passed: the existing 24 plus seven platform-loader and fallback regressions.
- The exact wrong-platform scenario was reproduced with Windows-targeted loader tests: Linux/macOS files are never passed to the loader; renamed foreign DLLs and wrong-architecture PE files are rejected.
- An RC transient completed through the Python fallback with a foreign Linux file present in the simulated Windows source folder.
- Native Qt tests passed for dark startup over the old preference, persisted explicit theme choice, dark canvases/palette, and running/completed/failed states.
- The worker cancellation check passed; a dark-mode screenshot was visually reviewed.
- The rebuilt standalone Linux executable passed offscreen startup and RC simulation without the development Python environment.

These are tests on the Linux build host, including Windows-targeted loader logic with a mocked OS loader. They are not an end-to-end Windows execution certification. Windows frame rendering and native DLL loading still require a Windows host. The application remains an engineering preview with the previously documented PDK, extraction, and qualification gaps.

## Implementation references

- [Microsoft: DWM window attributes](https://learn.microsoft.com/en-us/windows/win32/api/dwmapi/ne-dwmapi-dwmwindowattribute)
- [Microsoft: DwmSetWindowAttribute](https://learn.microsoft.com/en-us/windows/win32/api/dwmapi/nf-dwmapi-dwmsetwindowattribute)
- [Python 3.12: ctypes](https://docs.python.org/3.12/library/ctypes.html)
