"""Native hierarchical spatial queries for the desktop view.

Masters and regular arrays stay in a KLayout database. Only a padded visible
window becomes drawing rows. IDs, array paths and schematic net mappings remain
attached to those rows; this database is a view cache, never the saved project.
"""
import math
from .layout import kdb,polygon,shape_from_polygon
from .layout_cache import geometry_key


class LayoutScene:
    def __init__(self):
        self.db=kdb().Layout();self.db.dbu=.001;self.layer=self.db.layer(1,0)
        self.cells={};self.signatures={};self.cache=None;self.generation=0

    def update(self,p,cid,depth=None):
        db=kdb();by={c['id']:c for c in p['cells']}
        # Rebuilding after cell removal also drops obsolete native allocations.
        if self.cells.keys()-by.keys():self.__init__()
        for ident in by:
            if ident not in self.cells:self.cells[ident]=self.db.create_cell(ident)
        sources={};instances={};rebuilt=0
        for ident,c in by.items():
            native=self.cells[ident]
            signature=(tuple((s['id'],s['layer'],geometry_key(s)) for s in c['shapes']),repr(c.get('layout_instances',[])))
            if self.signatures.get(ident)!=signature:
                native.clear()
                for s in c['shapes']:native.shapes(self.layer).insert(polygon(s)).set_property('id',s['id'])
                for inst in c.get('layout_instances',[]):
                    tr=db.ICplxTrans(1,inst.get('rotation',0),inst.get('mirror',False),inst['x'],inst['y'])
                    native.insert(db.CellInstArray(self.cells[inst['cell']].cell_index(),tr,db.Vector(*inst.get('a',[inst.get('dx',0),0])),db.Vector(*inst.get('b',[0,inst.get('dy',0)])),inst.get('nx',1),inst.get('ny',1))).set_property('id',inst['id'])
                self.signatures[ident]=signature;rebuilt+=1
            for i,s in enumerate(c['shapes']):sources[s['id']]=(s,i)
            for i,inst in enumerate(c.get('layout_instances',[])):instances[inst['id']]=(inst,i,c)
        self.by=by;self.sources=sources;self.instances=instances;self.cid=cid;self.depth=depth;self.cache=None;self.generation+=1;self._bounds_cache={}
        self.bounds,self.expanded_count=self._bounds(cid,depth)
        self.stats={'masters_rebuilt':rebuilt,'master_shapes':len(sources),'expanded_shapes':self.expanded_count,'query_rows':0}
        return self

    def _bounds(self,cid,depth):
        db=kdb();cachekey=(cid,depth)
        if cachekey in self._bounds_cache:return self._bounds_cache[cachekey]
        c=self.by[cid];box=db.Box();count=len(c['shapes'])
        for s in c['shapes']:box+=polygon(s).bbox()
        if depth is None or depth>0:
            for inst in c.get('layout_instances',[]):
                child,n=self._bounds(inst['cell'],None if depth is None else depth-1);count+=n*inst.get('nx',1)*inst.get('ny',1)
                box+=self._instance_box(inst,child)
        self._bounds_cache[cachekey]=(box,count);return box,count

    def _instance_box(self,inst,child):
        db=kdb();box=db.Box();a=inst.get('a',[inst.get('dx',0),0]);b=inst.get('b',[0,inst.get('dy',0)])
        if child.empty():return box
        for ix in (0,inst.get('nx',1)-1):
            for iy in (0,inst.get('ny',1)-1):box+=child.transformed(db.ICplxTrans(1,inst.get('rotation',0),inst.get('mirror',False),inst['x']+ix*a[0]+iy*b[0],inst['y']+ix*a[1]+iy*b[1]))
        return box

    def owner_bounds(self,ident):
        if ident in self.sources:return polygon(self.sources[ident][0]).bbox()
        inst=self.instances[ident][0]
        if self.depth==0:return kdb().Box()
        child,_=self._bounds(inst['cell'],None if self.depth is None else self.depth-1)
        return self._instance_box(inst,child)

    def query(self,box,*,cache=True,render=False):
        """Return ordered shapes; point snapping can bypass the viewport cache."""
        from .layout_limits import RENDER_ROWS, EXACT_QUERY_ROWS
        limit=RENDER_ROWS if render else EXACT_QUERY_ROWS
        db=kdb();box=db.Box(math.floor(box[0]),math.floor(box[1]),math.ceil(box[2]),math.ceil(box[3]))
        # An overview cache can contain the whole design. A later point-pick or
        # close-up should use the native hierarchy search instead of repeatedly
        # filtering thousands of old rows in Python.
        oversized=self.cache is not None and len(self.cache[1])>2000 and max(1,box.width())*max(1,box.height())*16<self.cache[0].width()*self.cache[0].height()
        if cache and self.cache is not None and not self.stats.get('detail_reduced') and not oversized and self.cache[0].contains(db.Point(box.left,box.bottom)) and self.cache[0].contains(db.Point(box.right,box.top)):
            return [s for s,b in self.cache[1] if b.touches(box)]
        window=box.enlarged(max(1000,int(max(box.width(),box.height())*.15))) if cache else box
        iterator=self.cells[self.cid].begin_shapes_rec_touching(self.layer,window)
        if self.depth is not None:iterator.max_depth=self.depth
        rows=[]
        self.stats['detail_reduced']=False
        while not iterator.at_end():
            if len(rows)>=limit:
                if not render:raise ValueError('Exact selection exceeds 100,000 shapes. Zoom in or select a hierarchy instance in the cell tree.')
                self.cache=None;self.stats.update(detail_reduced=True,query_rows=len(rows))
                # A labeled outline represents the hierarchy extent, never fake metal.
                b=self.bounds
                return [{'id':'','kind':'rect','layer':next(iter(self.sources.values()))[0]['layer'],'points':[[b.left,b.bottom],[b.right,b.top]],'_overview':True}]
            source,index=self.sources[iterator.shape().property('id')];elements=iterator.path();order=[];owner=None;device_owner=None;path='';mapping={}
            for element in elements:
                inst,i,cell=self.instances[element.inst().property('id')];ix=element.ia();iy=element.ib();order.extend((1,i,ix,iy))
                def net(n):return '0' if n=='0' else mapping.get(n,path+n) if n else ''
                device=next((d for d in cell['devices'] if d['id']==inst.get('device_id')),None)
                mapped={pin:net(n) for pin,n in device['nets'].items()} if device else {}
                owner=owner or inst['id'];device_owner=device_owner or inst.get('device_id');path+=inst['name']+f'[{ix},{iy}]/';mapping=mapped
            if owner:
                poly=iterator.shape().polygon.transformed(iterator.trans());netname=source.get('net','');netname='0' if netname=='0' else mapping.get(netname,path+netname) if netname else ''
                if poly.is_box():
                    b=poly.bbox();shape={'kind':'rect','layer':source['layer'],'points':[[b.left,b.bottom],[b.right,b.top]],'net':netname,'device_id':device_owner or source.get('device_id','')}
                else:shape=shape_from_polygon(poly,source['layer'],netname,device_owner or source.get('device_id',''))
                if source['kind']=='path':
                    points=[iterator.trans()*db.Point(*pt) for pt in source['points']]
                    shape['_snap_path']=[(pt.x,pt.y) for pt in points]
                shape.update(id=owner,source_id=source['id'],instance_path=path)
            else:shape=source;poly=iterator.shape().polygon
            order.extend((0,index));rows.append((tuple(order),shape,poly.bbox()));iterator.next()
        rows.sort(key=lambda row:row[0])
        if cache:self.cache=(window,[(s,b) for _,s,b in rows])
        self.stats['query_rows']=len(rows)
        return [s for _,s,b in rows if b.touches(box)]
