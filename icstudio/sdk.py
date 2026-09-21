"""Explicitly invoked, trusted local worker plugins. Not an OS security sandbox."""
import json,subprocess,sys,tempfile
from pathlib import Path
from .model import clone,validate,History

def apply_commands(project,commands):
    from .design_automation import envelope,commit_batch
    history=History(clone(project))
    # Legacy trusted plugins may still return a command list. Versioned plugins
    # can return an envelope and have stale project/revision checks enforced.
    if commands==[]:return history.project
    request=envelope(history.project,commands,'Plugin command batch') if isinstance(commands,list) else commands
    commit_batch(history,request);return history.project

def run_plugin(manifest,project):
    file=Path(manifest).resolve();m=json.loads(file.read_text())
    if m.get('api_version')!='1.0' or m.get('capabilities')!=['commands']:raise ValueError('Plugin must declare API 1.0 and commands capability.')
    entry=(file.parent/m['entry']).resolve()
    if not entry.is_relative_to(file.parent) or entry.suffix!='.py' or not entry.is_file():raise ValueError('Plugin entry must be a Python file inside its package.')
    if getattr(sys,'frozen',False):raise ValueError('Trusted Python SDK plugins run from the source distribution using Python. The packaged executable does not embed a general script host.')
    with tempfile.TemporaryDirectory(prefix='icstudio-plugin-') as tmp:
        # No shell; isolated working directory and process timeout. This is not a security boundary.
        r=subprocess.run([sys.executable,str(entry)],input=json.dumps(project),text=True,capture_output=True,cwd=tmp,timeout=30,check=True)
        if len(r.stdout)>10*1024*1024:raise ValueError('Plugin output exceeds 10 MiB.')
        commands=json.loads(r.stdout);return apply_commands(project,commands)
