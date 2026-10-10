"""Verify that nominal wire calibration extracted the intended metal masks.

Measurement-port rectangles in a DEF import can extend the wire being measured.
Require the native area, perimeter and metal of every isolated rectangular wire
to match the exported OpenDB wire mask before using a calibration table.
"""
from decimal import Decimal, InvalidOperation
import hashlib
import json
from pathlib import Path
import shlex

METALS = {'m'+str(i): name for i,name in enumerate(
    ('Metal1','Metal2','Metal3','Metal4','Metal5','TopMetal1','TopMetal2'),1)}


def compare(text, rectangles):
    expected = {}
    for row in rectangles:
        name, box = row['name'], row['box']
        if (not isinstance(name,str) or not name or name in expected
                or row['layer'] not in METALS.values() or len(box)!=4
                or any(type(v) is not int for v in box)):
            raise ValueError('Invalid or repeated reference wire.')
        width, length = box[2]-box[0], box[3]-box[1]
        if min(width,length)<=0: raise ValueError('Empty reference wire.')
        expected[name]=(row['layer'],Decimal(width*length),Decimal(2*(width+length)))
    if not expected: raise ValueError('Reference wires are required.')
    nodes = {}; scale = None; substrate = None
    for line in text.splitlines():
        t = shlex.split(line)
        if not t: continue
        if t[0] in ('use','device','fet','resist','rnode','killnode'):
            raise ValueError('Expected a flat, isolated metal-wire calibration.')
        if t[0]=='substrate':
            try:
                if (substrate is not None or len(t)<9 or (len(t)-7)%2 or t[6]!='space'
                        or any(Decimal(v)!=0 for v in t[2:4]+t[7:]) or t[1] in expected):
                    raise ValueError('Unsupported explicit substrate geometry or parasitics.')
            except InvalidOperation as exc:
                raise ValueError('Malformed implicit substrate values.') from exc
            substrate=t[1]
            continue
        if t[0]=='scale':
            try:
                if len(t)!=4 or scale is not None: raise ValueError('Invalid native scale.')
                # Magic's length scale is in centimicrons (10 nm).
                scale=Decimal(t[3])*10
                if not scale.is_finite() or scale<=0: raise ValueError('Invalid native scale.')
            except InvalidOperation as exc: raise ValueError('Invalid native scale.') from exc
        if t[0]!='node': continue
        name=t[1].removesuffix('_BL') if len(t)>1 else ''
        if len(t)<9 or (len(t)-7)%2 or name in nodes or t[6] not in METALS:
            raise ValueError('Ambiguous or malformed native metal node.')
        try: values=[int(v) for v in t[7:]]
        except ValueError as exc: raise ValueError('Nonintegral native wire geometry.') from exc
        pairs=[(values[i],values[i+1]) for i in range(0,len(values),2)
               if values[i] or values[i+1]]
        if len(pairs)!=1 or min(pairs[0])<=0:
            raise ValueError('A native wire must have one positive resistance-class area/perimeter pair.')
        nodes[name]=(METALS[t[6]],*map(Decimal,pairs[0]))
    if scale is None or nodes.keys()!=expected.keys():
        raise ValueError('Missing scale or changed calibration net inventory.')
    errors=[]
    for name,(layer,area,perimeter) in nodes.items():
        actual=(layer,area*scale*scale,perimeter*scale)
        if actual!=expected[name]:
            errors.append(dict(name=name,expected_layer=expected[name][0],actual_layer=layer,
                expected_area_nm2=str(expected[name][1]),actual_area_nm2=str(actual[1]),
                expected_perimeter_nm=str(expected[name][2]),actual_perimeter_nm=str(actual[2])))
    return dict(schema=1,passed=not errors,qualified=False,checked_nets=len(nodes),implicit_substrate=substrate,
                failed_nets=len(errors),failures=errors[:20],
                scope='Exact metal, area and perimeter of every isolated rectangular calibration wire; not field-model accuracy.')


def audit(extraction, geometry):
    extraction,geometry=map(Path,(extraction,geometry))
    result=compare(extraction.read_text(),json.loads(geometry.read_text()))
    result.update(native_ext_sha256=hashlib.sha256(extraction.read_bytes()).hexdigest(),
                  wire_geometry_sha256=hashlib.sha256(geometry.read_bytes()).hexdigest())
    return result
