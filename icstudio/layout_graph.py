"""Incremental polygon contact and rule-influence components.

Only edges incident to changed nodes are rebuilt. Component closure includes old
and new neighbours, so removals and splits are handled as well as joins. No
geometry is clipped at the boundary of a locally checked component.
"""
from .layout import kdb,polygon
from .layout_cache import geometry_key
from .layout_index import LayoutBoxIndex


def key(shape):return (shape['id'],shape.get('source_id',''),shape.get('instance_path',''))


class GeometryGraph:
    def __init__(self,mode='contact'):
        self.mode=mode;self.records={};self.edges={};self.groups={};self.index=None;self.keys=[];self.rules=None;self.generation=0
        self.stats={}

    def sync(self,shapes,tech,trusted=False):
        db=kdb();connect=tech.get('connectivity',{});vias=connect.get('vias',[['metal1','via1','metal2']])
        conductors=set(connect.get('conductors',['metal1','metal2']))|{v for _,v,_ in vias}
        if self.mode=='contact':
            radii={(l,l):0 for l in conductors}
            for a,v,b in vias:
                for x,y in ((a,v),(v,a),(v,b),(b,v)):radii[x,y]=0
            shapes=[s for s in shapes if s['layer'] in conductors]
            if len(shapes)>20000:raise ValueError('Connected editing supports at most 20,000 conducting shapes.')
        else:
            from .live_geometry import enclosure_rules
            radii={(l['name'],l['name']):l['space'] for l in tech['layers']}
            for rule in enclosure_rules(tech):
                for a,b in ((rule['cut'],rule['conductor']),(rule['conductor'],rule['cut'])):radii[a,b]=max(radii.get((a,b),0),int(rule['minimum']))
        rulekey=repr(tech);reset=rulekey!=self.rules
        records={};changed=set();built=0
        for shape in shapes:
            ident=key(shape);old=self.records.get(ident)
            signature=old['signature'] if trusted and old and old['shape'] is shape else (shape['layer'],geometry_key(shape))
            if old and old['signature']==signature:
                record={**old,'shape':shape}
            else:
                poly=polygon(shape);b=poly.bbox();record={'signature':signature,'poly':poly,'region':db.Region(poly),'box':(b.left,b.bottom,b.right,b.top),'shape':shape};changed.add(ident);built+=1
            records[ident]=record
        removed=self.records.keys()-records.keys();changed.update(removed)
        if reset:changed.update(records)
        ordered=list(records);boxes=tuple(records[k]['box'] for k in ordered)
        index=self.index if ordered==self.keys and self.index is not None and boxes==self.index.bounds else LayoutBoxIndex(boxes,self.index if ordered==self.keys else None)
        edges={k:set(self.edges.get(k,())) for k in records} if changed else self.edges
        affected=set(changed);affected_groups=set()
        for ident in changed:
            prior_group=self.groups.get(ident)
            if prior_group:affected_groups.add(prior_group)
            for neighbour in self.edges.get(ident,()):
                if neighbour in edges:edges[neighbour].discard(ident)
            if ident in edges:edges[ident]=set()
        tests=0;radius_by_layer={a:max(r for (layer,_),r in radii.items() if layer==a) for a,_ in radii}
        for ident in changed & records.keys():
            row=records[ident];a=row['shape']['layer'];radius=radius_by_layer.get(a,0);box=row['box'];query=(box[0]-radius,box[1]-radius,box[2]+radius,box[3]+radius)
            for i in index.query(query):
                other=ordered[i]
                if other==ident or other in changed and other<ident:continue
                target=records[other];distance=radii.get((a,target['shape']['layer']))
                if distance is None:continue
                b=target['box']
                if box[0]>b[2]+distance or box[2]<b[0]-distance or box[1]>b[3]+distance or box[3]<b[1]-distance:continue
                tests+=1
                if self.mode=='influence' or not row['region'].interacting(target['region']).is_empty():
                    edges[ident].add(other);edges[other].add(ident)
                    prior_group=self.groups.get(other)
                    if prior_group:affected_groups.add(prior_group)
                    else:affected.add(other)
        for group in affected_groups:affected.update(group)
        groups={k:g for k,g in self.groups.items() if k in records and k not in affected}
        todo=(affected & records.keys()) | (records.keys()-groups.keys())
        while todo:
            start=todo.pop();component={start};pending=[start]
            while pending:
                current=pending.pop()
                for other in edges[current]-component:component.add(other);pending.append(other)
            frozen=frozenset(component)
            for ident in component:groups[ident]=frozen
            todo.difference_update(component)
        self.records=records;self.keys=ordered;self.index=index;self.edges=edges;self.groups=groups;self.rules=rulekey;self.generation+=1
        self.changed=changed;self.affected=affected & records.keys();self.stats={'polygons_built':built,'edge_tests':tests,'changed':len(changed),'affected':len(self.affected),'nodes':len(records)}
        return self

    def query(self,box):return [self.keys[i] for i in self.index.query(box)]

    def partition(self,p,cid):
        from .physical_cells import terminals,ports
        converted={g:frozenset(('shape',*v) for v in g) for g in set(self.groups.values())}
        groups={('shape',*k):converted[g] for k,g in self.groups.items()}
        # Build each component's anchor set once. Polygon contact was already
        # calculated by the graph; labels alone never join physical components.
        anchors=[(('pin',v['id']),v) for v in terminals(p,cid)]+[(('port',v['name']),v) for v in ports(p,cid)]
        buckets={};db=kdb()
        for anchor,v in anchors:
            x,y=v['point'];hits=[k for k in self.query((x,y,x,y)) if self.records[k]['shape']['layer']==v['layer'] and self.records[k]['poly'].inside(db.Point(x,y))]
            component=self.groups[hits[0]] if hits else frozenset()
            if hits and any(self.groups[k]!=component for k in hits):raise ValueError('Ambiguous terminal boundary; use a full connectivity check.')
            buckets.setdefault(component if hits else frozenset((anchor,)),[]).append(anchor)
        for component,items in buckets.items():
            members={('shape',*k) for k in component} if any(k in self.records for k in component) else set()
            members.update(items);frozen=frozenset(members)
            for ident in members:groups[ident]=frozen
        return groups


class IncrementalDRC:
    """Cache flat-cell findings by complete rule-influence component.

    Dirty components are checked together in one native region pass. Removing a
    bridge invalidates every old member, including members of the resulting
    split components. Hierarchical callers retain the complete-check path.
    """
    def __init__(self):self.graph=GeometryGraph('influence');self.results={}

    def check(self,p,cid,shapes):
        from .layout import drc
        from .live_geometry import check_enclosures
        from .model import digest
        graph=self.graph.sync(shapes,p['pdk']);groups=list(dict.fromkeys(graph.groups[k] for k in graph.keys))
        dirty={g for g in groups if g not in self.results or g & graph.affected}
        results={g:self.results[g] if g not in dirty else [] for g in groups}
        subset=[graph.records[k]['shape'] for k in graph.keys if graph.groups[k] in dirty]
        if subset:
            cell=next(c for c in p['cells'] if c['id']==cid)
            local={**p,'cells':[{**cell,'shapes':subset,'layout_instances':[]}]}
            by_id={s['id']:graph.groups[key(s)] for s in subset}
            for issue in drc(local,cid)+check_enclosures(local,cid,subset):
                # Flat cells have unique shape IDs; each pair finding belongs to
                # the same influence component as its referenced shape.
                group=by_id.get(issue['object'])
                if group is None:raise ValueError('Unattributed local finding; run the complete layout check.')
                results[group].append(issue)
        self.results=results;out=[]
        for issues in results.values():
            for old in issues:
                issue={**old};issue['fingerprint']=digest({'revision':p['revision'],'rule':issue['code'],'object':issue['object'],'bbox':issue.get('bbox'),'message':issue['message']});out.append(issue)
        if len(out)>2000:raise ValueError('More than 2,000 violations. Fix coarse geometry first.')
        self.stats={**graph.stats,'components_checked':len(dirty),'components_total':len(groups),'shapes_checked':len(subset)}
        return out
