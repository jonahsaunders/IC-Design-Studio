"""Retain original layout bytes and make lossy native conversion explicit."""
import base64
import hashlib
import tempfile
from pathlib import Path
from .model import atomic_write, file_digest
from .layout import kdb

MAX_BYTES=64*1024*1024


def inspect(path):
    path=Path(path)
    if path.stat().st_size>MAX_BYTES:raise ValueError('Select a layout smaller than 64 MB for native import.')
    db=kdb();layout=db.Layout();layout.read(str(path))
    issues=[]
    if abs(layout.dbu-.001)>1e-12:issues.append('Source database unit is '+str(layout.dbu)+' µm; native coordinates use 0.001 µm.')
    if layout.cells()>100:issues.append('Source exceeds the 100-cell native hierarchy limit.')
    for cell in layout.each_cell():
        for instance in cell.each_inst():
            tr=instance.cplx_trans
            if abs(tr.mag-1)>1e-12 or tr.angle not in (0,90,180,270):
                issues.append('Magnified or non-orthogonal instances require flattening for native editing.');break
    tops=[c.name for c in layout.top_cells()]
    if len(tops)>1:issues.append('Choose a top cell for conversion; the original contains multiple roots.')
    return {'version':1,'name':path.name,'sha256':file_digest(path),'bytes':path.stat().st_size,
            'dbu_um':layout.dbu,'cells':layout.cells(),'tops':tops,'issues':list(dict.fromkeys(issues))}


def retain(project,path,conversion=None):
    path=Path(path);report=inspect(path)
    project['layout_source']={**report,'base64':base64.b64encode(path.read_bytes()).decode(),
                              'conversion':conversion,'scope':'Original bytes retained independently of editable native geometry.'}
    return project


def restore(project,path):
    source=project.get('layout_source',{})
    try:data=base64.b64decode(source['base64'],validate=True)
    except (KeyError,ValueError) as exc:raise ValueError('No intact original layout is attached.') from exc
    if len(data)>MAX_BYTES or hashlib.sha256(data).hexdigest()!=source['sha256']:raise ValueError('The retained original layout checksum changed.')
    atomic_write(path,data)


def convert(path,top,*,flatten=False,round_to_nm=False):
    """Convert only with named choices; the original is always recoverable."""
    from .layout_import import read_layout
    path=Path(path);report=inspect(path);db=kdb();source=db.Layout();source.read(str(path))
    cell=source.cell(top)
    if cell is None or top not in report['tops']:raise ValueError('Choose a source top cell.')
    if not flatten:raise ValueError('Explicit flattening is required for this conversion path.')
    if not round_to_nm and abs(source.dbu-.001)>1e-12:raise ValueError('Explicit 1 nm rounding is required when changing database units.')
    # Bound expansion before asking KLayout to flatten arrays.
    budget=[0,0]
    def count(c,seen,mult=1):
        if c.cell_index() in seen:raise ValueError('Recursive source hierarchy.')
        budget[0]+=mult
        budget[1]+=mult*sum(c.shapes(i).size() for i in source.layer_indexes())
        if budget[0]>10000 or budget[1]>1000000:raise ValueError('Conversion exceeds the 10,000-instance / 1,000,000-shape budget.')
        for inst in c.each_inst():count(source.cell(inst.cell_index),seen|{c.cell_index()},mult*max(1,inst.na)*max(1,inst.nb))
    count(cell,set());cell.flatten(-1,False)
    target=db.Layout();target.dbu=.001;out=target.create_cell(cell.name)
    for index in source.layer_indexes():
        dest=target.layer(source.get_info(index))
        for shape in cell.shapes(index).each():
            geometry=shape.text.to_dtype(source.dbu).to_itype(.001) if shape.is_text() else shape.polygon.to_dtype(source.dbu).to_itype(.001)
            item=out.shapes(dest).insert(geometry)
            for key,value in shape.properties().items():
                if key not in (125,126,127,'icstudio_id'):item.set_property(key,value)
    with tempfile.TemporaryDirectory() as folder:
        native=Path(folder)/'converted.oas';target.write(str(native));project,notes=read_layout(native)
    project['name']=path.stem
    conversion={'top':top,'flattened':True,'source_dbu_um':source.dbu,'target_dbu_um':.001,
                'round_to_nm':round_to_nm,'expanded_instances':budget[0],
                'result':'Independent native geometry; original hierarchy, paths and properties remain in the retained original.'}
    retain(project,path,conversion)
    return project,notes+[conversion['result']]
