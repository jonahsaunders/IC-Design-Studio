"""Immutable bounding-volume index for viewport and selection queries."""
class SpatialIndex:
    def __init__(self,entries):
        def build(items):
            if not items:return None
            bounds=(min(x[0][0] for x in items),min(x[0][1] for x in items),max(x[0][2] for x in items),max(x[0][3] for x in items))
            if len(items)<=16:return bounds,items,None,None
            axis=0 if bounds[2]-bounds[0]>=bounds[3]-bounds[1] else 1;items.sort(key=lambda x:x[0][axis]+x[0][axis+2]);mid=len(items)//2
            return bounds,None,build(items[:mid]),build(items[mid:])
        self.root=build(list(entries))
    def query(self,box):
        found=[]
        def overlaps(a,b):return a[0]<=b[2] and a[2]>=b[0] and a[1]<=b[3] and a[3]>=b[1]
        def visit(node):
            if node is None or not overlaps(node[0],box):return
            if node[1] is not None:found.extend(value for bounds,value in node[1] if overlaps(bounds,box))
            else:visit(node[2]);visit(node[3])
        visit(self.root);return found
