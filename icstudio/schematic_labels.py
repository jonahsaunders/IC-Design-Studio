"""Shared positions for instance captions and schematic viewport fitting."""
from .native_vectors import display_name


def captions(device):
    texts=[item['text'] for item in device.get('symbol',{}).get('primitives',[])
           if item['kind']=='text' and not item.get('hidden')]
    if any('@name' in text or text==device['name'] for text in texts):return []
    kind=device['kind'];native=device.get('native_spice',{})
    primitive=native.get('label') in ('R','C','L','V','I')
    block=kind in ('X','XS') or kind=='SPICE' and not primitive
    sideways=device['rotation'] in (90,270)
    x=device['x']+(-35 if block else 80 if kind in ('NMOS','PMOS') else -20 if sideways else 37)
    y=device['y']+(-78 if block else -55 if sideways else -30)
    rows=[(x,y,display_name(device),11,False)]
    if not block:
        if kind=='PDK':value=device.get('model_ref',{}).get('device','').split('/')[-1].replace('.sym','')
        elif kind in ('NMOS','PMOS'):value=device['params']['w']+' / '+device['params']['l']
        else:value=device['value']
        if primitive:
            value=native.get('parameters',{}).get('value',value)
            if len(value)>40:value=value.split('(',1)[0]+' source'
        rows.append((x,y+18,value,9,True))
    return rows
