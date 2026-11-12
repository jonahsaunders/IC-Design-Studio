"""Bounded inventory of the literal CVC model-rule forms in the pinned release.

These are checker declarations, not SPICE model bindings or qualified operating
limits. No expression is evaluated. Other CVC grammar remains an explicit gap.
"""
import hashlib
from pathlib import PurePosixPath
import re

IDENTIFIER=r'[A-Za-z_][A-Za-z0-9_]*'
DECIMAL=r'[+-]?(?:[0-9]+(?:\.[0-9]*)?|\.[0-9]+)(?:[eE][+-]?[0-9]+)?'
ATTRIBUTES={'MN':{'Vth','Vgs','Vds'},'MP':{'Vth','Vgs','Vds'},
            'R':{'R','model'},'D':set(),'C':set(),'Q':set()}


def require(condition,message):
    if not condition:raise ValueError('CVC declarations: '+message)


def digest(value):
    return hashlib.sha256(value.encode('utf-8')).hexdigest()


def model_rules(text):
    require(len(text)<=100_000,'source exceeds bounded reader size')
    rows=[];names=set()
    for line,raw in enumerate(text.splitlines(),1):
        if not raw.strip() or raw.startswith('#'):continue
        require(len(raw)<=2048,'record exceeds bounded reader size')
        # The primary loader recognizes column-one comments. Indented/inline
        # markers are deliberately unsupported rather than silently discarded.
        require('#' not in raw,'unreviewed comment position')
        fields=raw.split();require(len(fields)>=2,'missing checker type/name')
        kind,name=fields[:2]
        require(kind in ATTRIBUTES,'unsupported checker device type')
        require(len(name)<=256 and re.fullmatch(IDENTIFIER,name),'nonliteral checker model name')
        require(name not in names,'duplicate checker model name requires conditional/redefinition review');names.add(name)
        attributes=[];keys=set()
        for token in fields[2:]:
            require(len(token)<=256 and token.count('=')==1,'unsupported checker attribute form')
            key,value=token.split('=',1)
            require(key in ATTRIBUTES[kind],'unsupported checker attribute')
            require(key not in keys,'duplicate checker attribute');keys.add(key)
            require(bool(value),'empty checker attribute')
            fact=dict(name=key,expression_sha256=digest(value),expression_bytes=len(value.encode()),evaluated=False)
            if key in ('Vth','Vgs','Vds'):
                require(re.fullmatch(DECIMAL,value),'unsupported checker numeric expression')
                fact.update(value_kind='decimal-literal',literal=value)
            elif key=='model':
                require(value=='switch_on','unsupported checker model override')
                fact.update(value_kind='checker-model-override',literal=value,simulator_model_binding_inferred=False)
            else:
                match=re.fullmatch(r'l/w(?:\*('+DECIMAL+r'))?',value)
                require(match is not None,'unsupported checker resistance expression')
                fact.update(value_kind='bounded-resistance-expression',identifiers=['l','w'],
                            operators=['/']+(['*'] if match[1] is not None else []),
                            numeric_factors=[match[1]] if match[1] is not None else [])
            attributes.append(fact)
        rows.append(dict(kind='cvc-checker-model-declaration',name=name,checker_type=kind,line=line,
                         attributes=attributes,record_sha256=digest(raw),record_bytes=len(raw.encode()),
                         simulator_model_binding_inferred=False,operating_envelope_inferred=False))
    require(bool(rows),'no checker model declarations')
    return rows


def cvc_views(path,text):
    """Only the two known release path shapes select this reader."""
    parts=PurePosixPath(path).parts
    if len(parts)==5 and parts[0] in ('sky130A','sky130B') and parts[1:]==('libs.tech','openlane','cvc','models'):
        return model_rules(text)
    return None
