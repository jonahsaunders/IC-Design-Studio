"""Locked upstream fixed SKY130 bipolar cells with explicit terminal contracts.

Physical masks come from the unmodified Apache-2.0 upstream GDS, never an
approximation of a bipolar structure. This adapter adds access conductors only.
The original GDS terminal labels prove which local-interconnect ring is which.
Actual DRC/LVS of each placed or regenerated instance remains required.
"""
import math
from pathlib import Path

from .catalog import binding_for, parameter_values
from .layout import kdb, rect
from .model import clone, file_digest, uid


MODEL='sky130_fd_pr__pnp_05v5_W3p40L3p40'
CELL='sky130_fd_pr__rf_pnp_05v5_W3p40L3p40'
SOURCE_COMMIT='403964dc7f9cca5ec1a8cc7b4f2a6f532b781676'
ASSET_SHA256='19758688e586f1c670ebac59ffe9adff75bd20f6fa094abc16af2834bfeacad0'
MODEL_SHA256='2cee6ecea0c60e7a5a9d7d6329b89aac0a84c80e7443d426206906196b4cae9e'
ASSET=Path(__file__).resolve().parent/'assets/physical/sky130_fixed'/f'{CELL}.gds'
# Accesses are chosen on the same connected LI regions as these upstream
# labels. Collector/base accesses use existing upstream contact landing pads.
TERMINALS={
    'collector':dict(label='Collector',label_nm=[3320,6380],access_nm=[385,3495]),
    'base':dict(label='Base',label_nm=[3245,5610],access_nm=[1125,3490]),
    'emitter':dict(label='Emitter',label_nm=[3390,3390],access_nm=[3350,3350]),
}
DRAWING_MASKS={(64,20),(65,20),(65,44),(66,44),(67,20),(67,44),(68,20),(82,44),(93,44),(94,20)}
ANNOTATION_MASKS={(67,5),(67,16),(83,44),(236,0)}


def supported(tech,d):
    binding=binding_for(tech,d)
    return bool(tech.get('package_lock',{}).get('id')=='sky130A' and binding and binding.get('model','').lower()==MODEL.lower())


def specification(tech,d):
    binding=binding_for(tech,d)
    if not supported(tech,d) or d['kind']!='PDK' or binding.get('prefix')!='X' or binding.get('pin_order')!=list(TERMINALS) or set(d['nets'])!=set(TERMINALS):
        raise ValueError('Use the shipped three-terminal SKY130 PNP W3.40/L3.40 catalog binding.')
    if binding.get('emit_parameters')!={'m':'m'}:raise ValueError('The fixed PNP requires direct multiplicity emission.')
    values=parameter_values(binding,d);count=values.get('m',1)
    if not math.isfinite(count) or count!=int(count) or not 1<=count<=16:raise ValueError('Use an integer PNP parallel multiplicity from 1 to 16.')
    from .sky130_bipolar_rules import TECH_SHA256
    from .interoperability import tool_asset
    reltech=tech.get('interoperability',{}).get('tools',{}).get('magic',{}).get('technology','libs.tech/magic/sky130A.tech')
    if tech.get('package_lock',{}).get('files',{}).get(reltech)!=TECH_SHA256:
        raise ValueError('Fixed PNP generation requires the experimental SKY130 adapter prepared with --bipolar; the older deck cannot identify PNP dimensions from GDS.')
    tool_asset(tech,'magic','technology',reltech)
    rel=f'libs.ref/sky130_fd_pr/spice/{MODEL}.model.spice'
    root=Path(tech.get('package_root','')).resolve();model=(root/rel).resolve()
    if tech.get('package_lock',{}).get('files',{}).get(rel)!=MODEL_SHA256 or not model.is_relative_to(root) or not model.is_file() or file_digest(model)!=MODEL_SHA256:
        raise ValueError('The fixed PNP requires its intact locked upstream model definition.')
    if not ASSET.is_file() or file_digest(ASSET)!=ASSET_SHA256:raise ValueError('The locked upstream PNP geometry is missing or changed.')
    result=dict(api=1,recipe='fixed_pnp',model=MODEL,model_ref=clone(d['model_ref']),kind=d['kind'],
        values=values,dimensions_nm=dict(w=3400,l=3400),nets=clone(d['nets']),
        fixed_cell=dict(cell=CELL,sha256=ASSET_SHA256,source_commit=SOURCE_COMMIT,model_sha256=MODEL_SHA256,technology_sha256=TECH_SHA256))
    if count>1:result['multiplicity']=int(count)
    return result


def geometry(tech,d,x=0,y=0):
    spec=specification(tech,d)
    if any(type(v) is not int or v%5 or abs(v)>100000000 for v in (x,y)):raise ValueError('Place fixed PNPs on the 5 nm grid within ±100 mm.')
    db=kdb();layout=db.Layout();layout.read(str(ASSET))
    if layout.dbu!=.001 or len(layout.top_cells())!=1 or layout.top_cell().name!=CELL:raise ValueError('Unexpected upstream fixed-cell database units or hierarchy.')
    source=layout.top_cell();mapped={(r['gds'],r['datatype']):r['name'] for r in tech['layers']}
    if DRAWING_MASKS-set(mapped):raise ValueError('The technology lacks a required upstream PNP physical mask.')
    shapes=[];regions={};labels={}
    for index in layout.layer_indexes():
        info=layout.get_info(index);mask=(info.layer,info.datatype);iterator=source.begin_shapes_rec(index)
        if mask not in DRAWING_MASKS|ANNOTATION_MASKS and not iterator.at_end():raise ValueError('Unmapped upstream PNP layer: '+str(mask))
        region=db.Region()
        while not iterator.at_end():
            shape=iterator.shape();transform=iterator.trans()
            if shape.is_text() and mask==(67,5):
                disp=shape.text.trans.disp;point=transform*db.Point(disp.x,disp.y);labels[shape.text.string]=[point.x,point.y]
            elif mask in DRAWING_MASKS:
                if not (shape.is_box() or shape.is_polygon() or shape.is_path()):raise ValueError('Unsupported physical primitive in fixed PNP.')
                region.insert(shape.polygon.transformed(transform))
            iterator.next()
        if mask not in DRAWING_MASKS:continue
        region.merge();regions[mask]=region
        for number,poly in enumerate(region.each()):
            shape=dict(id=uid(),kind='polygon',layer=mapped[mask],points=[[point.x+x,point.y+y] for point in poly.each_point_hull()],
                device_id=d['id'],generated_device=d['id'],generator_role=f'fixed:{mask[0]}/{mask[1]}:{number}',net='')
            if poly.holes():shape['holes']=[[[point.x+x,point.y+y] for point in poly.each_point_hole(i)] for i in range(poly.holes())]
            shapes.append(shape)
    pins=[]
    for name,terminal in TERMINALS.items():
        if labels.get(terminal['label'])!=terminal['label_nm']:raise ValueError('The upstream PNP terminal-label contract changed.')
        label,access=db.Point(*terminal['label_nm']),db.Point(*terminal['access_nm'])
        if not any(poly.inside(label) and poly.inside(access) for poly in regions[67,20].each()):raise ValueError('The fixed PNP access is not connected to its upstream terminal label.')
        px,py=terminal['access_nm'];net=d['nets'][name]
        # LI/mcon/metal1 construction follows the existing contacted SKY130
        # recipes; emitter already has metal1 and mcon in the upstream cell.
        for mask,half in (((67,44),85),((68,20),170)) if name!='emitter' else (((68,20),170),):
            shape=rect(mapped[mask],x+px-half,y+py-half,2*half,2*half,d['id'],net if mask==(68,20) else '')
            shape.update(generated_device=d['id'],generator_role=f'fixed:access:{name}:{mask[0]}/{mask[1]}');shapes.append(shape)
        pins.append(dict(id=uid(),device_id=d['id'],pin=name,layer=mapped[68,20],point=[x+px,y+py]))
    from .sky130_devices import parallel_geometry
    return parallel_geometry(tech,d,dict(shapes=shapes,pins=pins,record=dict(device_id=d['id'],spec=spec,origin=[x,y])),spec.get('multiplicity',1))
