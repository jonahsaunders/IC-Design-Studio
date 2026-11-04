"""Translate public standard IHP MOS primitives to their simulation X view.

Only the instance prefix changes. Retain terminal order, model and every
numerical parameter, including rfmode=0. RF extraction is a separate contract.
"""
from decimal import Decimal, InvalidOperation
import re

MODELS={'sg13_lv_nmos','sg13_lv_pmos','sg13_hv_nmos','sg13_hv_pmos'}


def subcircuits(text):
    lines=re.sub(r'\n[ \t]*\+[ \t]*',' ',text).splitlines();changes=[];names=set()
    for index,line in enumerate(lines):
        tokens=line.split()
        if not tokens or tokens[0].startswith(('*','.')):continue
        if tokens[0][0].upper()=='M' and len(tokens)>5 and tokens[5].lower() in MODELS:
            params={}
            for token in tokens[6:]:
                if token.count('=')!=1:raise ValueError('Ambiguous IHP MOS extraction parameter.')
                key,value=token.lower().split('=')
                if key in params:raise ValueError('Duplicate IHP MOS extraction parameter.')
                params[key]=value
            if not {'w','l','rfmode'}<=params.keys() or params.keys()-{'w','l','as','ad','ps','pd','m','rfmode'}:
                raise ValueError('Unreviewed IHP MOS extraction interface.')
            try:standard=Decimal(params['rfmode'])==0
            except InvalidOperation:standard=False
            if not standard:raise ValueError('IHP RF MOS extraction requires its separate geometry/model contract.')
            replacement='X'+tokens[0][1:]
            lines[index]=re.sub(r'^(\s*)'+re.escape(tokens[0]),lambda m:m[1]+replacement,line,count=1)
            changes.append(dict(instance=tokens[0],replacement=replacement,model=tokens[5],terminal_count=4,
                                change='Standard MOS M-to-X prefix only; terminals and parameters unchanged.'))
        name=lines[index].split()[0].casefold()
        if name in names:raise ValueError('Duplicate instance after IHP MOS interface conversion.')
        names.add(name)
    return '\n'.join(lines)+'\n',changes
