"""Layout queries, exact hierarchical file XOR, and bounded geometric finishing."""
import math
from pathlib import Path
from .model import clone, design_digest, file_digest, validate
from .design_ops import flatten_layout
from .layout import kdb, polygon, rect


def query(p,cid,layer='',net='',kind='',minimum_area=0,box=None,limit=5000):
    if not 1<=limit<=20000 or minimum_area<0:raise ValueError('Use a non-negative area and 1–20,000 result rows.')
    db=kdb();rows=[];total=0
    if box is not None and (len(box)!=4 or box[2]<=box[0] or box[3]<=box[1]):raise ValueError('Query box needs increasing X/Y bounds.')
    region=db.Region(db.Box(*box)) if box else None
    for s in flatten_layout(p,cid):
        if layer and s['layer']!=layer or net and s.get('net')!=net or kind and s['kind']!=kind:continue
        poly=polygon(s)
        if poly.area()<minimum_area or region is not None and db.Region(poly).interacting(region).is_empty():continue
        total+=1
        if len(rows)>=limit:continue
        b=poly.bbox();rows.append({'id':s['id'],'source_id':s.get('source_id',s['id']),
            'instance_path':s.get('instance_path',''),'layer':s['layer'],'net':s.get('net',''),
            'kind':s['kind'],'area_um2':poly.area()*1e-6,'bbox':[b.left,b.bottom,b.right,b.top]})
    return {'design_hash':design_digest(p),'cell_id':cid,'rows':rows,'total':total,'truncated':total>len(rows)}


def compare_files(a,b,top_a='',top_b='',limit=1000,max_shapes=500000,cancelled=lambda:False):
    """Compare flattened polygon coverage by layer/datatype, retaining hierarchy on input.

    Unlike native import, this does not create editable cells or impose its 100-cell
    limit. Text, properties, generator recipes and circuit equivalence are separate.
    """
    if not 1<=limit<=10000 or not 1<=max_shapes<=2000000:raise ValueError('Invalid comparison budget.')
    db=kdb();layouts=[];tops=[];hashes=[]
    for source,top_name in ((a,top_a),(b,top_b)):
        if cancelled():raise InterruptedError('Layout comparison cancelled.')
        source=Path(source)
        if source.stat().st_size>256*1024*1024:raise ValueError('Layout comparison supports files up to 256 MB.')
        before=file_digest(source);ly=db.Layout();ly.read(str(source))
        if before!=file_digest(source):raise ValueError('A layout file changed while it was being read.')
        top=ly.cell(top_name) if top_name else (ly.top_cells()[0] if len(ly.top_cells())==1 else None)
        if top is None:raise ValueError('Choose an existing top cell for each layout with multiple roots.')
        layouts.append(ly);tops.append(top);hashes.append(before)
    dbu=min(ly.dbu for ly in layouts);scale=[ly.dbu/dbu for ly in layouts]
    if any(not math.isclose(v,round(v),rel_tol=0,abs_tol=1e-9) for v in scale):
        raise ValueError('The layout database units are not integer multiples; comparison would require rounding.')
    regions=[];counts=[]
    for ly,top,factor in zip(layouts,tops,scale):
        out={};count=0
        for li in ly.layer_indices():
            info=ly.get_info(li);region=db.Region();it=top.begin_shapes_rec(li)
            while not it.at_end():
                if cancelled():raise InterruptedError('Layout comparison cancelled.')
                shape=it.shape()
                if shape.is_box() or shape.is_path() or shape.is_polygon():
                    count+=1
                    if count>max_shapes:raise ValueError('The comparison exceeds the expanded geometry budget. Select a smaller top cell.')
                    poly=shape.polygon.transformed(it.trans()).transformed(db.ICplxTrans(round(factor),0,False,0,0))
                    region.insert(poly)
                it.next()
            out[(info.layer,info.datatype)]=region.merged()
        regions.append(out);counts.append(count)
    rows=[];layers=[];total=0
    for key in sorted(set(regions[0])|set(regions[1])):
        if cancelled():raise InterruptedError('Layout comparison cancelled.')
        left=regions[0].get(key,db.Region());right=regions[1].get(key,db.Region())
        removed=left-right;added=right-left;count=0
        for change,region in (('removed',removed),('added',added)):
            for poly in region.each():
                count+=1;total+=1
                if len(rows)<limit:
                    box=poly.bbox();rows.append({'layer':key[0],'datatype':key[1],'change':change,
                        'area_um2':poly.area()*dbu**2,'bbox_um':[v*dbu for v in (box.left,box.bottom,box.right,box.top)]})
        layers.append({'layer':key[0],'datatype':key[1],'differences':count,
                       'removed_um2':removed.area()*dbu**2,'added_um2':added.area()*dbu**2})
    return {'version':1,'files':[str(Path(v).resolve()) for v in (a,b)],'sha256':hashes,
            'tops':[t.name for t in tops],'expanded_shapes':counts,'comparison_dbu_um':dbu,
            'equal_geometry':total==0,'total':total,'rows':rows,'layers':layers,'truncated':total>len(rows),
            'qualification':'Polygon coverage by layer/datatype only. Text, properties, hierarchy structure and electrical equivalence are not compared.'}


def density(p,cid,layer,box,tile=10000):
    db=kdb();grid=p['pdk']['grid']
    if type(tile) is not int or tile<=0 or tile%grid or len(box)!=4 or any(type(v) is not int or v%grid for v in box):raise ValueError('Use an on-grid tile size and rectangle.')
    x0,y0,x1,y1=box
    if x1<=x0 or y1<=y0 or math.ceil((x1-x0)/tile)*math.ceil((y1-y0)/tile)>10000:raise ValueError('Density analysis supports 1–10,000 rectangular tiles.')
    if layer not in {l['name'] for l in p['pdk']['layers']}:raise ValueError('Choose a mapped density layer.')
    region=db.Region()
    for s in flatten_layout(p,cid):
        if s['layer']==layer:region.insert(polygon(s))
    region.merge();rows=[]
    for x in range(x0,x1,tile):
        for y in range(y0,y1,tile):
            b=db.Box(x,y,min(x+tile,x1),min(y+tile,y1));area=(region&db.Region(b)).area()
            rows.append({'bbox':[b.left,b.bottom,b.right,b.top],'density':area/b.area()})
    return {'design_hash':design_digest(p),'layer':layer,'rows':rows,'minimum':min(v['density'] for v in rows),'maximum':max(v['density'] for v in rows)}


def fill(p,cid,layer,box,size=1000,pitch=3000,keepout=1000,locked=()):
    """Add floating square fill with all-layer keepout; process density closure is external."""
    grid=p['pdk']['grid'];rule=next((l for l in p['pdk']['layers'] if l['name']==layer),None)
    if not rule or layer in locked:raise ValueError('Choose an unlocked mapped fill layer.')
    if any(type(v) is not int or v%grid for v in (size,pitch,keepout,*box)) or size<max(grid,rule['width']) or pitch<size+max(grid,rule['space']) or keepout<rule['space']:
        raise ValueError('Fill size, pitch and keepout must meet grid, width and spacing rules.')
    if len(box)!=4 or box[2]<=box[0] or box[3]<=box[1] or math.ceil((box[2]-box[0])/pitch)*math.ceil((box[3]-box[1])/pitch)>10000:
        raise ValueError('Fill supports at most 10,000 candidate squares in a valid rectangle.')
    db=kdb();blocked=db.Region()
    for s in flatten_layout(p,cid):blocked.insert(polygon(s))
    blocked=blocked.merged().sized(keepout);shapes=[]
    for x in range(box[0],box[2]-size+1,pitch):
        for y in range(box[1],box[3]-size+1,pitch):
            s=rect(layer,x,y,size,size)
            if (db.Region(polygon(s))&blocked).is_empty():s['dummy_fill']=True;shapes.append(s)
    if not shapes:raise ValueError('No fill sites remain after keepouts.')
    q=clone(p);c=next(c for c in q['cells'] if c['id']==cid);c['shapes'].extend(shapes);validate(q)
    next(c for c in p['cells'] if c['id']==cid).update(c);return [s['id'] for s in shapes]


def round_corners(p,cid,ids,inner,outer,points=32,locked=()):
    grid=p['pdk']['grid']
    if any(type(v) is not int or v<0 or v%grid for v in (inner,outer)) or not 8<=points<=256 or points%4:raise ValueError('Use non-negative on-grid radii and 8–256 circle points in multiples of four.')
    if not ids:raise ValueError('Select local shapes to round.')
    q=clone(p);c=next(c for c in q['cells'] if c['id']==cid);selected=[s for s in c['shapes'] if s['id'] in ids]
    if len(selected)!=len(set(ids)) or any(s['layer'] in locked for s in selected):raise ValueError('Choose unlocked local shapes.')
    for s in selected:
        poly=polygon(s).round_corners(inner,outer,points)
        # Quantize deliberately to the project's manufacturing grid, then validate.
        pts=[[round(pt.x/grid)*grid,round(pt.y/grid)*grid] for pt in poly.each_point_hull()]
        holes=[[[round(pt.x/grid)*grid,round(pt.y/grid)*grid] for pt in poly.each_point_hole(i)] for i in range(poly.holes())]
        s.update(kind='polygon',points=pts,holes=holes);s.pop('width',None)
    validate(q)
    from .layout_topology import require_preserved, _check_clearance
    require_preserved(p,q,cid);_check_clearance(p,q,cid)
    next(c for c in p['cells'] if c['id']==cid).update(c)
