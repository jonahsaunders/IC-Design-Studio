"""Reconcile IHP external model types with locked Verilog-A declarations.

All preprocessor branches remain explicit. This is source coverage, not a
compiler, ABI, parameter-range or electrical qualification. In particular the
XYCE and thermal PSP declarations are not added to the six-library OSDI runtime.
"""
import argparse,json,re,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from icstudio.model import file_digest
from scripts.inventory_device_models import inventory


def declarations(text,source):
    # Preserve original line numbers when removing comments. Model declarations
    # start a source line and never come from evaluating macros or source code.
    text=re.sub(r'/\*.*?\*/',lambda m:'\n'*m[0].count('\n'),text,flags=re.S)
    conditions=[];rows=[]
    for number,line in enumerate(text.splitlines(),1):
        line=line.split('//',1)[0].strip()
        directive=re.match(r'`(ifdef|ifndef|elsif|else|endif)\b(.*)',line)
        if directive:
            op=directive[1]
            if op in ('ifdef','ifndef'):conditions.append([line])
            elif not conditions:raise ValueError('Unmatched Verilog-A condition: '+source)
            elif op=='endif':conditions.pop()
            else:conditions[-1].append(line)
        if not re.match(r'module\b',line):continue
        match=re.fullmatch(r'module\s+([A-Za-z_]\w*)\s*\(\s*([\w\s,]+)\s*\)\s*;',line)
        if not match:raise ValueError('Unreviewed Verilog-A module declaration: '+source)
        pins=[p.strip() for p in match[2].split(',')]
        if not all(re.fullmatch(r'[A-Za-z_]\w*',p) for p in pins) or len(pins)!=len(set(pins)):
            raise ValueError('Invalid Verilog-A terminal declaration.')
        rows.append(dict(source=source,line=number,module=match[1],terminals=pins,conditions=[list(c) for c in conditions]))
    if conditions:raise ValueError('Unterminated Verilog-A condition: '+source)
    return rows


def reconcile(spice,modules):
    references={}
    for d in spice['definitions']:
        if d.get('prefix')=='N':references.setdefault(d['model_type'],[]).append(d['id'])
    declared={r['module'].casefold() for r in modules}
    return dict(references=references,missing=sorted(set(references)-declared),
                additional_declarations=sorted(r['module'] for r in modules if r['module'].casefold() not in references))


def run(folder):
    folder=Path(folder);spice=inventory(folder);package=json.loads((folder/'package.json').read_bytes())
    files={p:h for p,h in package['files'].items() if p.startswith('libs.tech/verilog-a/')}
    if not files:raise ValueError('No locked Verilog-A sources.')
    modules=[]
    for name in sorted(files):
        path=folder/name
        if path.suffix.lower() in ('.va','.vams','.include','.h','.inc'):
            modules.extend(declarations(path.read_text(encoding='utf-8'),name))
    bindings=reconcile(spice,modules)
    for name,h in files.items():
        if file_digest(folder/name)!=h:raise ValueError('Verilog-A source changed during inventory.')
    if file_digest(folder/'package.json')!=spice['manifest_sha256']:raise ValueError('Package changed during inventory.')
    return dict(schema=1,chunk=7,chunk_complete=False,qualified=False,scope=__doc__,status='PASS' if not bindings['missing'] else 'GAPS',
                revision=package['revision'],manifest_sha256=spice['manifest_sha256'],files=files,modules=modules,**bindings,
                runner_sha256=file_digest(__file__),spice_inventory_runner_sha256=file_digest(ROOT/'scripts/inventory_device_models.py'))


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--input',type=Path,default=ROOT/'icstudio/assets/pdks/ihp-sg13g2');p.add_argument('--output',type=Path,required=True);a=p.parse_args()
    if a.output.exists():raise ValueError('Choose a new Verilog-A inventory output.')
    r=run(a.input);a.output.write_bytes((json.dumps(r,indent=2)+'\n').encode())
    print(r['status'],len(r['modules']),'declarations;',len(r['references']),'referenced types; missing:',r['missing'])
    raise SystemExit(int(r['status']!='PASS'))
