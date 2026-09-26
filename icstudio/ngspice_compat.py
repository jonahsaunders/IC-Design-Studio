"""Explicit legacy diode geometry, adapted only in disposable simulation decks.

ngspice changed level-3 AREA/PJ scaling between the qualified 42 and 46
releases. Probe the executable's behavior instead of guessing from its version.
The marker is a units declaration for the immediately following instance; no
size threshold, model substitution or change to an immutable model is used.
"""
import hashlib
import json
import math
from pathlib import Path
import re
from .model import atomic_write

MARKER='* ICSTUDIO_DIODE_GEOMETRY_V1 scale=1e-6'
MODELS={'sky130_fd_pr__diode_pw2nd_05v5','sky130_fd_pr__diode_pd2nw_05v5'}


def legacy_symbol(attributes,properties_override=None):
    from .xschem_project import properties
    defaults=properties(attributes.get('template',''))
    selected={**defaults,**(properties_override or {})}
    return (attributes.get('type')=='diode'
            and attributes.get('format','').strip()=='@name @pinlist sky130_fd_pr__@model area=@area'
            and 'format' not in (properties_override or {})
            and 'sky130_fd_pr__'+selected.get('model','') in MODELS
            and defaults.get('area')=='1e12')


def declare(line):
    words=line.split()
    if len(words)<5 or not words[0].lower().startswith('d') or words[3] not in MODELS:
        raise ValueError('The legacy diode geometry contract requires a supported SKY130 level-3 diode.')
    return MARKER+'\n'+line


def behavior(executable,directory):
    from .engines import execute,parse_raw
    from .spice_program import runtime_environment
    root=Path(directory)/'diode-geometry-probe';root.mkdir(parents=True,exist_ok=True)
    text='''* Explicit-area versus width/length level-3 behavior
.option scale=1e-6 gmin=1e-30
.model probe_d D level=3 is=1e-12
Va a 0 1
Vb b 0 1
Da 0 a probe_d area=1e12
Db 0 b probe_d w=1e6 l=1e6
.op
.save i(va) i(vb)
.end
'''
    atomic_write(root/'input.cir',text)
    log=execute([executable,'-n','-D','ngbehavior=hsa','-D','filetype=ascii','-b','-r',root/'out.raw',root/'input.cir'],root,env=runtime_environment(executable))
    atomic_write(root/'engine.log',log)
    variables,rows,complex_data=parse_raw(root/'out.raw')
    if complex_data or len(rows)!=1:raise ValueError('Incomplete diode geometry behavior probe.')
    values=dict(zip(variables,rows[0]));ratio=values['i(va)']/values['i(vb)']
    if math.isclose(ratio,1,rel_tol=1e-5):mode='scales-explicit-area'
    elif math.isclose(ratio,1e12,rel_tol=1e-5):mode='unscaled-explicit-area'
    else:raise ValueError('Unsupported ngspice diode geometry behavior: '+str(ratio))
    from .external_tools import executable_info
    record=dict(mode=mode,area_ratio=ratio,currents=values,engine=executable_info(executable))
    atomic_write(root/'behavior.json',json.dumps(record,indent=2))
    return record


def convert(text,mode):
    if mode not in ('scales-explicit-area','unscaled-explicit-area'):raise ValueError('Unknown diode geometry behavior.')
    lines=text.splitlines(keepends=True);count=0;pending=False
    for i,line in enumerate(lines):
        if line.strip()==MARKER:
            if pending:raise ValueError('Repeated diode geometry declaration.')
            pending=True;continue
        if not pending:continue
        if not line.strip() or line.lstrip().startswith('*'):continue
        declare(line);pending=False;count+=1
        if len(re.findall(r'(?i)\barea\s*=',line))!=1:
            raise ValueError('Legacy diode geometry requires one explicit AREA.')
        if re.search(r'(?i)\b[wl]\s*=',line):raise ValueError('Legacy AREA cannot be combined with W/L geometry.')
        if mode=='unscaled-explicit-area':
            def value(match):
                raw=match['value'];raw=raw[1:-1] if raw.startswith(('{',"'")) else raw
                scale='1e-12' if match['key'].lower()=='area' else '1e-6'
                return match['key']+'={('+raw+')*'+scale+'}'
            pattern=r"(?P<key>area|pj)\s*=\s*(?P<value>\{[^{}\r\n]+\}|'[^'\r\n]+'|[^\s]+)"
            lines[i],n=re.subn(pattern,value,line,flags=re.I)
            if not n:raise ValueError('Legacy diode geometry is missing an explicit AREA.')
        # Consume the marker in the runtime copy to make adaptation idempotent.
        for j in range(i-1,-1,-1):
            if lines[j].strip()==MARKER:
                lines[j]='* Applied '+MARKER[2:]+' behavior='+mode+'\n';break
    if pending:raise ValueError('Diode geometry declaration has no instance.')
    return ''.join(lines),count


def prepare(text,executable,directory):
    if MARKER not in text:return text
    record=behavior(executable,directory)
    result,count=convert(text,record['mode'])
    record.update(instances=count,source_sha256=hashlib.sha256(text.encode()).hexdigest(),
                  runtime_sha256=hashlib.sha256(result.encode()).hexdigest(),
                  convention='Level-3 AREA and PJ use the pre-46 scale=1e-6 convention; model bytes are unchanged.')
    atomic_write(Path(directory)/'diode-geometry-compatibility.json',json.dumps(record,indent=2))
    return result
