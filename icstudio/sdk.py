"""Explicitly invoked, trusted local worker plugins. Not an OS security sandbox."""
import json,subprocess,sys,tempfile
from pathlib import Path
from .model import clone,validate,History

def apply_commands(project,commands):
    if not isinstance(commands,list) or len(commands)>10000:raise ValueError('Invalid command batch.')
    history=History(project)
    def apply(p):
        for cmd in commands:
            cell=next(c for c in p['cells'] if c['id']==cmd['cell_id'])
            if cmd['type']=='add_shape':cell['shapes'].append(cmd['shape'])
            elif cmd['type']=='add_device':cell['devices'].append(cmd['device'])
            elif cmd['type']=='set_parameter':
                d=next(d for d in cell['devices'] if d['id']==cmd['device_id'])
                if cmd['name']=='value':d['value']=cmd['value']
                elif cmd['name'] in ('w','l','vto','kp','lambda'):d['params'][cmd['name']]=cmd['value']
                else:raise ValueError('Unsupported parameter.')
            else:raise ValueError('Unsupported command.')
    history.commit(apply,'Plugin command batch');return history.project

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
