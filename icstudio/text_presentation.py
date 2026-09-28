"""Optional Studio text appearance carried as an OASIS property.

Only appearance is restored. Text, layer purpose and electrical anchor always
come from the stream. Other tools may drop this property; use GDS when native
text presentation must be portable to tools that do not understand it.
"""
import json
import math

PROPERTY = 124
KEYS = ('rotation', 'mirror', 'size', 'font', 'halign', 'valign')


def owned(value):
    try:return isinstance(value,str) and json.loads(value).get('format')=='icstudio.text-presentation.v1'
    except (ValueError,AttributeError):return False


def encode(text, layer, datatype, dbu):
    return json.dumps({'format':'icstudio.text-presentation.v1',
        'anchor':[text['text'], layer, datatype, text['x'], text['y'], dbu],
        'style':{key:text.get(key, False if key=='mirror' else -1 if key in ('font','halign','valign') else 0) for key in KEYS}},
        sort_keys=True, separators=(',', ':'))


def restore(record, value, layer, datatype, dbu):
    if not isinstance(value, str) or len(value)>16384: return False
    try:
        data=json.loads(value); anchor=data['anchor']; style=data['style']
        if data.get('format')!='icstudio.text-presentation.v1' or len(anchor)!=6: return False
        if anchor[:5] != [record['text'],layer,datatype,record['x'],record['y']]: return False
        if not math.isclose(anchor[5],dbu,rel_tol=1e-12,abs_tol=0): return False
        if set(style)!=set(KEYS) or type(style['mirror']) is not bool: return False
        if any(type(style[key]) is not int for key in KEYS if key!='mirror'): return False
        if style['rotation'] not in (0,90,180,270) or not 0<=style['size']<=2147483647: return False
        if style['font'] not in (-1,0,1,2,3) or style['halign'] not in (-1,0,1,2) or style['valign'] not in (-1,0,1,2): return False
    except (ValueError, TypeError, KeyError, OverflowError): return False
    record.update(style); return True
