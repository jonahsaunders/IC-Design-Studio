"""Selected IHP resistor footprints from authenticated public Magic output.

Copyright 2025 IHP PDK Authors. Source Magic generators: Apache-2.0.
These finite samples are physical geometry, not an operating envelope.
"""
import hashlib,json,math
from pathlib import Path
from .catalog import binding_for,parameter_values
from .model import clone,uid,file_digest,digest

MANIFEST_SEMANTIC_HASH='5cb4aca37ed4192eadd82d686a1d5fc97072b018e7c45d21f062333a3361eebd'
TEMPLATE_HASH='f5b296a45657f55928b0a242c5133bafb664c74ffa88cefe3ffb3f6880ff1fe1'
SOURCE_HASHES={'ihp-sg13g2-res.tcl':'800c367d636e7dba8f9f3b15621d76a99b509416c0ebdf809631996489b799d1','ihp-sg13g2-util.tcl':'8bfa9fcb33a035d7ba3253517f423dea245a4756a5a94f31160b254bcd7a454e','ihp-sg13g2-via.tcl':'dc69231a313c84c5e67edc9b9ee3e00292eb698d971eaf50958b14e53b256efa','ihp-sg13g2-drc.tech':'bec75c6c8aeb9720edcdfdcf1e2c132d9be4af42801dd61b45715d6c6ec68402'}
MODELS=('rsil','rppd','rhigh')
SIZES=((500,500),(500,20000),(20000,500),(2000,7000),(7000,2000))

def supported(tech,d):
    b=binding_for(tech,d)
    return bool(tech.get('package_lock',{}).get('id')=='ihp-sg13g2' and b and b.get('model') in MODELS)

def strict_pairs(pairs):
    result={}
    for key,value in pairs:
        if key in result:raise ValueError('Duplicate IHP package manifest key: '+key)
        result[key]=value
    return result

def invalid_constant(value):
    raise ValueError('Nonfinite IHP package manifest value: '+value)

def verify_identity(tech):
    try:
        root=Path(tech['package_root'])
        if digest(json.loads((root/'package.json').read_bytes(),object_pairs_hook=strict_pairs,parse_constant=invalid_constant))!=MANIFEST_SEMANTIC_HASH:raise ValueError('Changed reviewed IHP package manifest.')
        for name,expected in SOURCE_HASHES.items():
            if file_digest(root/'libs.tech/magic'/name)!=expected:raise ValueError('Changed reviewed IHP resistor source: '+name)
        raw=(Path(__file__).parent/'assets/qualification/ihp-resistor-templates/templates.json').read_bytes()
        if hashlib.sha256(raw).hexdigest()!=TEMPLATE_HASH:raise ValueError('Changed IHP resistor templates.')
        return raw
    except (OSError,KeyError,json.JSONDecodeError) as exc:
        raise ValueError('Reviewed IHP resistor package or template is unavailable.') from exc

def specification(tech,d):
    if not supported(tech,d):raise ValueError('Select a reviewed IHP resistor.')
    lock=tech.get('package_lock',{})
    if lock.get('manifest_hash',MANIFEST_SEMANTIC_HASH)!=MANIFEST_SEMANTIC_HASH or lock.get('revision')!='cfb96b74cf33877e' or digest(lock.get('files',{}))!='cd225707cc10207f7b83ac85efefaa0c8f94eaa738e05c212663fefc34f3da0b':raise ValueError('Use the reviewed IHP package revision.')
    verify_identity(tech)
    b=binding_for(tech,d); v=parameter_values(b,d)
    expected={'w':'w','l':'l','m':'m','mm_ok':'mm_ok'}
    if b['model']!='rsil':expected['b']='b'
    if b.get('emit_parameters')!=expected:raise ValueError('Use the reviewed resistor model parameters.')
    if b.get('prefix')!='X' or b.get('pin_order')!=['p','m','body'] or b.get('parameter_scale')!={'w':1,'l':1} or set(d['nets'])!={'p','m','body'}:
        raise ValueError('Use the reviewed three-terminal IHP resistor binding.')
    if v.get('m',1)!=1 or v.get('b',0)!=0:raise ValueError('Selected resistor geometry requires m=1 and b=0.')
    size=[]
    for key in ('w','l'):
        value=v[key]*1e9; rounded=round(value)
        if not math.isclose(value,rounded,rel_tol=0,abs_tol=1e-6):raise ValueError('Use a selected exact W/L combination.')
        size.append(rounded)
    if tuple(size) not in SIZES:raise ValueError('Choose a selected W/L combination: 0.5/0.5, 0.5/20, 20/0.5, 2/7 or 7/2 µm.')
    via=d.get('physical_terminal_vias',False)
    if type(via) is not bool:raise ValueError('Terminal via selection must be Boolean.')
    return {'api':1,'recipe':'ihp-resistor-selected-v1','model_ref':clone(d.get('model_ref')),'model':b['model'],'kind':d['kind'],'dimensions_nm':dict(zip(('w','l'),size)),'values':v,'nets':clone(d['nets']),'terminal_vias':via,'template_sha256':TEMPLATE_HASH,'package_manifest_sha256':'da58ba2de122d67d232ab20ca4fb353b70bdc68c00ef4279f9be7da640a68ae0','package_manifest_semantic_sha256':MANIFEST_SEMANTIC_HASH,'source_hashes':clone(SOURCE_HASHES)}

def geometry(tech,d,x=0,y=0):
    spec=specification(tech,d)
    if any(type(a) is not int or a%5 for a in (x,y)):raise ValueError('Place on the 5 nm grid.')
    raw=verify_identity(tech)
    size=spec['dimensions_nm'];fmt=lambda n:format(n/1000,'g')
    key=f"{spec['model']}:{fmt(size['w'])}:{fmt(size['l'])}:{int(spec['terminal_vias'])}"
    template=json.loads(raw)['templates'][key]; ls={}
    for layer in tech['layers']:
        pair=(layer['gds'],layer['datatype'])
        if pair in ls:raise ValueError('Ambiguous IHP layer mapping.')
        ls[pair]=layer['name']
    shapes=[]
    for index,item in enumerate(template['shapes']):
        pair=tuple(item['layer'])
        if pair not in ls:raise ValueError('Missing IHP template layer: '+str(pair))
        shape={'id':uid(),'kind':item['kind'],'layer':ls[pair],'points':[[a+x,b+y] for a,b in item['points']],'holes':[[[a+x,b+y] for a,b in h] for h in item.get('holes',[])],'net':'','device_id':d['id'],'generated_device':d['id'],'generator_role':'ihp_resistor:'+str(index)}
        shapes.append(shape)
    pins=[];mapping={'R1':'p','R2':'m','B':'body'}
    for port in template['ports']:
        pin=mapping[port['name']];pair=tuple(port['layer'])
        pins.append({'id':uid(),'device_id':d['id'],'pin':pin,'layer':ls[pair],'point':[port['point'][0]+x,port['point'][1]+y]})
    return {'shapes':shapes,'pins':pins,'record':{'device_id':d['id'],'spec':spec,'origin':[x,y]}}
