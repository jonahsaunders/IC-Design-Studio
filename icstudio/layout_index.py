"""Native integer-box lookup for connectivity and route attachment checks.

The database owns the search tree; exact polygon tests remain with callers.
Instances are transient, operation-local caches, never document data.
"""
from .layout import kdb


class LayoutBoxIndex:
    def __init__(self, bounds, previous=None):
        db = kdb()
        self.bounds = tuple(bounds)
        if previous is not None and len(self.bounds)==len(previous.bounds):
            self.changed=dict(previous.changed)
            for i,(old,new) in enumerate(zip(previous.bounds,self.bounds)):
                if old==new:continue
                if new==previous.base_bounds[i]:self.changed.pop(i,None)
                else:self.changed[i]=new
            if len(self.changed)<=min(256,max(16,len(self.bounds)//10)):
                self.db=previous.db;self.shapes=previous.shapes;self.base_bounds=previous.base_bounds
                return
        self.db = db.Layout()
        self.shapes = self.db.create_cell('INDEX').shapes(self.db.layer(1, 0))
        self.changed={};self.base_bounds=self.bounds
        for i, box in enumerate(self.bounds):
            self.shapes.insert(db.Box(*box)).set_property('index', i)

    def query(self, box):
        result=[s.property('index') for s in self.shapes.each_touching(kdb().Box(*box))]
        if not self.changed:return result
        return [i for i in result if i not in self.changed]+[i for i,b in self.changed.items() if b[0]<=box[2] and b[2]>=box[0] and b[1]<=box[3] and b[3]>=box[1]]
