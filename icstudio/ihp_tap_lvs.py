"""Strict source-checked IHP tap LVS geometry and terminal roles.

The pinned public symbols express LVS geometry as A=w*l and P=2*(w+l).
Native extraction supplies TIE/WELL and A/P. Express both as two-terminal X
devices so Netgen does not apply the generic resistor terminal permutation.
Never discard a conflicting simulation resistance or unreviewed parameter.
"""
import math,re
from pathlib import Path
from .model import file_digest,scalar
from .ihp_taps import SYMBOLS,MODELS,FORMULA


def recognition_label(layer,datatype,text):
    """Public TEXT markers select tap models; they are not conductor net names."""
    return (layer,datatype)==(63,0) and text.casefold() in ('well','sub!')


def _proof(technology,model):
    root=Path(technology['package_root']).resolve();files=technology['package_lock']['files']
    entry=technology['simulation']['catalog'].get('sg13g2_pr/'+model+'.sym',{})
    if entry.get('unavailable') or entry.get('model')!=model or entry.get('pin_order')!=['p','m']:
        raise ValueError('A reviewed two-terminal IHP tap binding is required for LVS.')
    paths=[(entry['source'],SYMBOLS[model]),(entry['model_source'],MODELS[Path(entry['model_source']).name])]
    for rel,h in paths:
        p=(root/rel).resolve()
        if not p.is_relative_to(root) or files.get(rel)!=h or file_digest(p)!=h:raise ValueError('Changed IHP tap LVS source: '+rel)
    return {rel:h for rel,h in paths}


def _parameters(tokens,allow_tap_formula=False):
    result={}
    for token in tokens:
        parts=token.split('=',1)
        if len(parts)!=2 or parts[0].lower() in result:raise ValueError('Duplicate or unresolved IHP tap LVS parameter.')
        key,raw=parts[0].lower(),parts[1]
        if allow_tap_formula and key=='r' and raw in ("'"+FORMULA.replace('@','')+"'",'{'+FORMULA.replace('@','')+'}'):
            result[key]=(None,raw);continue  # Exact reviewed formula; never evaluate arbitrary SPICE expressions.
        value=scalar(raw)
        if not math.isfinite(value) or value<=0:raise ValueError('IHP tap LVS geometry and resistance must be positive and finite.')
        result[key]=(value,raw)
    return result


def _names(lines):
    scopes={'':set()};scope=''
    for line in lines:
        tokens=line.split()
        if tokens and tokens[0].lower()=='.subckt':
            if scope or len(tokens)<2 or tokens[1].casefold() in scopes:raise ValueError('Invalid IHP tap LVS circuit scope.')
            scope=tokens[1].casefold();scopes[scope]=set();continue
        if tokens and tokens[0].lower()=='.ends':
            scope='';continue
        if not tokens or tokens[0].startswith(('*','.')):continue
        name=tokens[0].casefold()
        if name in scopes[scope]:raise ValueError('Duplicate instance after IHP tap LVS conversion.')
        scopes[scope].add(name)


def reference_geometry(text,technology):
    if technology.get('package_lock',{}).get('id')!='ihp-sg13g2':return text,[]
    lines=re.sub(r'\n[ \t]*\+[ \t]*',' ',text).splitlines();changes=[];proofs={}
    for i,line in enumerate(lines):
        tokens=line.split()
        if len(tokens)<4 or tokens[0][0].upper() not in ('X','R') or tokens[3].lower() not in SYMBOLS:continue
        model=tokens[3].lower()
        if model not in proofs:proofs[model]=_proof(technology,model)
        proof=proofs[model];params=_parameters(tokens[4:],allow_tap_formula=True)
        if set(params)=={'w','l','r'} and tokens[0][0].upper()=='X':
            w,l,r=(params[k][0] for k in ('w','l','r'));area=w*l;perimeter=2*(w+l)
            if not math.isfinite(area+perimeter) or area<=0 or perimeter<=0:raise ValueError('Invalid IHP tap LVS geometry.')
            expected=1/(area/9.8e-10+perimeter/9.8e-4)
            if r is not None and not math.isclose(r,expected,rel_tol=1e-9,abs_tol=0):raise ValueError('IHP tap resistance disagrees with its width and length.')
            values=[f'A={area:.15g}',f'P={perimeter:.15g}']
        elif set(params)=={'a','p'}:
            values=['A='+params['a'][1],'P='+params['p'][1]]
        else:raise ValueError('IHP tap LVS needs resolved W/L/R or the public A/P format; extra parameters are not discarded.')
        name=tokens[0] if tokens[0][0].upper()=='X' else 'XICSTUDIO_TAP_'+tokens[0]
        lines[i]=' '.join([name,*tokens[1:4],*values])
        changes.append(dict(instance=tokens[0],replacement=name,model=model,original=line,comparison=lines[i],source=proof,
            reason='Pinned public tap area/perimeter LVS format, preserving TIE/WELL roles. Simulation R checked when supplied.'))
    if not changes:return text,[]
    _names(lines);return '\n'.join(lines)+'\n',changes


def extracted_geometry(text):
    lines=re.sub(r'\n[ \t]*\+[ \t]*',' ',text).splitlines();changes=[]
    for i,line in enumerate(lines):
        tokens=line.split()
        if len(tokens)<4 or tokens[0][0].upper()!='R' or tokens[3].lower() not in SYMBOLS:continue
        if set(_parameters(tokens[4:]))!={'a','p'}:raise ValueError('Unreviewed IHP tap extraction parameters.')
        name='XICSTUDIO_TAP_'+tokens[0];lines[i]=' '.join([name,*tokens[1:]])
        changes.append(dict(instance=tokens[0],replacement=name,model=tokens[3],terminal_count=2,reason='Preserve public TIE/WELL polarity and every extracted A/P value.'))
    if not changes:return text,[]
    _names(lines);return '\n'.join(lines)+'\n',changes


def strict_setup(content):
    for model in ('ntap1','ptap1'):
        old=('lappend devices '+model+'\n').encode()
        if content.count(old)!=1:raise ValueError('Unexpected IHP tap comparison setup.')
        content=content.replace(old,b'# IC Design Studio: taps retain terminal roles and A/P; no generic resistor permutation or reduction.\n')
    return content
