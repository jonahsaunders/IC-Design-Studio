"""Identify source checkouts, archived source and frozen desktop packages."""
import json
import os
import platform
import subprocess
import sys
from pathlib import Path
from . import __version__


def identity():
    from . import build_info
    result = dict(version=__version__, commit=getattr(build_info,'BUILD_COMMIT','unknown'),
                  branch=getattr(build_info,'BUILD_BRANCH','unknown'), dirty=getattr(build_info,'BUILD_DIRTY',None),
                  frozen=bool(getattr(sys,'frozen',False)))
    root=Path(__file__).resolve().parents[1]
    if not result['frozen'] and (root/'.git').exists():
        def git(*args):
            return subprocess.check_output(['git',*args],cwd=root,text=True,stderr=subprocess.DEVNULL,timeout=3).strip()
        try:
            result.update(commit=git('rev-parse','HEAD'),branch=git('rev-parse','--abbrev-ref','HEAD'),
                          dirty=bool(git('status','--porcelain','--untracked-files=no','--','.',':(exclude)icstudio/build_info.py')))
            if git('ls-files','--others','--exclude-standard','--','icstudio','scripts','docs','examples'):
                result['dirty']=True
            if result['branch']=='HEAD':
                result['branch']=os.environ.get('GITHUB_HEAD_REF') or os.environ.get('GITHUB_REF_NAME') or 'detached HEAD'
        except (OSError,subprocess.SubprocessError):
            result.update(commit='unknown',branch='unknown',dirty=None)
    elif not result['frozen']:
        # The archive identifies its origin; without Git, local edits to that
        # unpacked source cannot be ruled out by embedded metadata alone.
        result['dirty']=None
    return result


def diagnostic_report():
    from PySide6 import __version__ as qt_version
    from PySide6.QtGui import QGuiApplication
    app=QGuiApplication.instance()
    return json.dumps(dict(build=identity(),os=platform.platform(),architecture=platform.machine(),
                           python=platform.python_version(),pyside=qt_version,
                           display=app.platformName() if app else 'not initialized',
                           screens=[dict(geometry=[s.geometry().x(),s.geometry().y(),s.geometry().width(),s.geometry().height()],
                                         available=[s.availableGeometry().x(),s.availableGeometry().y(),s.availableGeometry().width(),s.availableGeometry().height()],
                                         scale=s.devicePixelRatio()) for s in app.screens()] if app else []),indent=2)
