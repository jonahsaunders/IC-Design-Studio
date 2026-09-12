"""Run the frozen desktop with actual X11 window decorations in hosted CI."""
import json
import subprocess
import time
from pathlib import Path


def main():
    output=Path('build/x11-evidence').resolve();output.mkdir(parents=True,exist_ok=True)
    with (output/'window-manager.log').open('w') as log:
        manager=subprocess.Popen(['openbox'],stdout=log,stderr=subprocess.STDOUT)
        try:
            # Wait for Openbox to own the screen before testing native frames.
            deadline=time.monotonic()+5
            while time.monotonic()<deadline:
                if manager.poll() is not None:raise RuntimeError('The X11 window manager exited during startup.')
                ready=subprocess.run(['xprop','-root','_NET_SUPPORTING_WM_CHECK'],capture_output=True,text=True,timeout=2)
                if ready.returncode==0 and 'window id' in ready.stdout:break
                time.sleep(.1)
            else:raise RuntimeError('X11 window manager did not become ready.')
            subprocess.run(['./dist/ICDesignStudio/ICDesignStudio','--release-test',str(output)],check=True,timeout=240)
            report=json.loads((output/'release-test.json').read_text())
            if not report['frozen'] or report['status']!='passed' or report.get('experimental',{}).get('qt_platform')!='xcb':
                raise RuntimeError('The frozen X11 probe did not pass on the xcb platform.')
        finally:
            manager.terminate()
            try:manager.wait(timeout=10)
            except subprocess.TimeoutExpired:manager.kill();manager.wait()


if __name__=='__main__':main()
