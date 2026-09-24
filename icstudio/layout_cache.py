"""Geometry-revision caches independent of Qt and project edit ownership."""
from .spatial import SpatialIndex


def geometry_key(shape):
    return (shape['kind'],shape.get('width',0),tuple(map(tuple,shape['points'])),
            tuple(tuple(map(tuple,hole)) for hole in shape.get('holes',[])))


def display_key(shape,geometry):
    return (shape['id'],shape.get('source_id',''),shape.get('instance_path',''),
            geometry,shape['layer'],shape.get('net',''),shape.get('device_id',''),bool(shape.get('_overview')))


class PatchedSpatialIndex:
    """Immutable base tree plus a bounded set of replaced bounding boxes.

    Small edits avoid rebuilding the whole tree. Rebuild after 256 replacements
    or 10% of entries (minimum 16), so query cost cannot grow with undo history.
    Values remain current list indices, preserving paint and selection order.
    """
    def __init__(self,bounds,previous=None):
        self.bounds=bounds
        if previous is not None and len(bounds)==len(previous.bounds):
            self.base=previous.base;self.base_bounds=previous.base_bounds;self.changed=dict(previous.changed)
            for i,(a,b) in enumerate(zip(previous.bounds,bounds)):
                if a==b:continue
                if b==self.base_bounds[i]:self.changed.pop(i,None)
                else:self.changed[i]=b
            if len(self.changed)<=min(256,max(16,len(bounds)//10)):return
        self.base_bounds=bounds;self.base=SpatialIndex([(box,i) for i,box in enumerate(bounds)]);self.changed={}

    def query(self,box):
        result=[i for i in self.base.query(box) if i not in self.changed]
        result.extend(i for i,b in self.changed.items() if b[0]<=box[2] and b[2]>=box[0] and b[1]<=box[3] and b[3]>=box[1])
        return result


class DeferredPath:
    """Capture immutable geometry; realize a Qt path only when it is visible."""
    def __init__(self,factory,geometry):
        self.factory=factory;self.geometry=geometry;self.value=None

    def get(self):
        if self.value is None:
            kind,width,points,holes=self.geometry
            self.value=self.factory({'kind':kind,'width':width,'points':points,'holes':holes})
        return self.value


class LayoutGeometryCache:
    def __init__(self,bounds_factory,path_factory,deferred=False):
        self.bounds_factory=bounds_factory;self.path_factory=path_factory
        self.deferred=deferred
        self.snapshots=[];self.entries={};self.source=None;self.revision=0
        self.boxes=[];self.paths=[];self.by_id={};self.index=None
        self.display_keys=();self.display_revision=0

    def _display(self,keys):
        if keys!=self.display_keys:self.display_revision+=1
        self.display_keys=keys

    def update(self,shapes,revision=None,*,immutable=False):
        # Callers supplying a revision promise to advance it after mutation.
        # Unversioned callers are content-checked, including in-place edits.
        # Only committed History snapshots may opt into identity reuse across
        # revisions. A caller advancing a mutable list's revision still scans it.
        found=next((s for s in self.snapshots if s[0] is shapes and revision is not None and (s[1]==revision or immutable and s[8])),None)
        if found is not None:
            _,_,self.entries,self.boxes,self.paths,self.index,self.by_id,keys,trusted=found
            self._display(keys);self.source=shapes
            if found[1]!=revision or immutable and not trusted:
                snapshot=(shapes,revision,*found[2:8],immutable or trusted)
                self.snapshots=([snapshot]+[s for s in self.snapshots if s[0] is not shapes])[:2]
            return
        prior=next((s for s in self.snapshots if s[0] is self.source and s[8]),None)
        if immutable and prior is not None and len(shapes)==len(self.source):
            indices=[i for i,(old,new) in enumerate(zip(self.source,shapes)) if old is not new]
            if all(tuple(shapes[i].get(k,'') for k in ('id','source_id','instance_path'))==tuple(self.source[i].get(k,'') for k in ('id','source_id','instance_path')) for i in indices):
                return self.update_dirty(shapes,revision,indices,immutable=True)
        entries={};boxes=[];paths=[];bounds=[];by_id={};changed=False;display=[]
        previous_entries=dict(self.entries)
        for snapshot in reversed(self.snapshots):
            for key,value in snapshot[2].items():previous_entries.setdefault(key,value)
        for i,shape in enumerate(shapes):
            identity=(shape['id'],shape.get('source_id',''),shape.get('instance_path',''))
            key=geometry_key(shape);old=previous_entries.get(identity)
            display.append(display_key(shape,key))
            if old is not None and old[0]==key:entry=old
            else:entry=(key,self.bounds_factory(shape),DeferredPath(self.path_factory,key) if self.deferred else self.path_factory(shape));changed=True
            entries[identity]=entry;box=entry[1];boxes.append(box);paths.append(entry[2])
            bounds.append((box.left(),box.top(),box.right(),box.bottom()))
            by_id.setdefault(shape['id'],[]).append(i)
        bounds=tuple(bounds)
        index=self.index if self.index is not None and self.index.bounds==bounds else PatchedSpatialIndex(bounds,self.index)
        self.revision+=int(changed or self.source is None or len(shapes)!=len(self.boxes))
        self.source=shapes;self.entries=entries;self.boxes=boxes;self.paths=paths;self.index=index;self.by_id=by_id
        self._display(tuple(display))
        snapshot=(shapes,revision,entries,boxes,paths,index,by_id,self.display_keys,immutable)
        self.snapshots=([snapshot]+[s for s in self.snapshots if s[0] is not shapes])[:2]

    def update_dirty(self,shapes,revision,indices,*,immutable=False):
        """History's constrained move preserves list order and every identity."""
        if self.source is None or len(shapes)!=len(self.source):return self.update(shapes,revision,immutable=immutable)
        entries=dict(self.entries);boxes=list(self.boxes);paths=list(self.paths);bounds=list(self.index.bounds);display=list(self.display_keys)
        for i in indices:
            shape=shapes[i];identity=(shape['id'],shape.get('source_id',''),shape.get('instance_path',''))
            geom=geometry_key(shape);box=self.bounds_factory(shape);path=DeferredPath(self.path_factory,geom) if self.deferred else self.path_factory(shape);entries[identity]=(geom,box,path)
            display[i]=display_key(shape,geom)
            boxes[i]=box;paths[i]=path;bounds[i]=(box.left(),box.top(),box.right(),box.bottom())
        self.index=PatchedSpatialIndex(tuple(bounds),self.index);self.boxes=boxes;self.paths=paths;self.entries=entries;self.source=shapes;self.revision+=1
        self._display(tuple(display))
        self.snapshots=([(shapes,revision,entries,boxes,paths,self.index,self.by_id,self.display_keys,immutable)]+self.snapshots)[:2]

    def selected_indices(self,ids):
        return sorted({i for ident in ids for i in self.by_id.get(ident,())})
