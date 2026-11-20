"""Physical evidence and reviewed local edits for the assistant. Coordinates are nm."""
from collections import Counter, defaultdict
import math

from .design_ops import flatten_layout
from .layout import drc, kdb, polygon
from .layout_topology import shape_key
from .ai_rule_repairs import checked_change, supporting_edge
from .layout_vias import technology
from .live_geometry import enclosure_rules, full
from .model import clone, design_digest, digest
from .physical import connectivity


def bounds(shape):
    b = polygon(shape).bbox()
    return [b.left,b.bottom,b.right,b.top]


def rectangular_pad(shapes, cut, rule):
    """A single true rectangle gives four identifiable cut-to-pad margins."""
    region = kdb().Region(polygon(cut)).sized(rule['minimum'])
    pads = [s for s in shapes if s['layer'] == rule['conductor'] and
            not (kdb().Region(polygon(s)) & region).is_empty()]
    if len(pads) == 1 and cut['kind'] == 'rect' and polygon(pads[0]).is_box():
        return pads[0]


def enclosure_evidence(shapes, cut, rule):
    pad = rectangular_pad(shapes, cut, rule)
    if pad is None:
        # Use the same merged metal and sizing metric as the enclosure checker.
        metal = kdb().Region()
        for s in shapes:
            if s['layer'] == rule['conductor']:
                metal.insert(polygon(s))
        inner = kdb().Region(polygon(cut))
        if not (inner - metal).is_empty():
            return {'detail':'The cut extends outside the merged conductor.'}
        lo, hi = 0, rule['minimum']
        while lo < hi:
            mid = (lo+hi+1)//2
            if (inner.sized(mid)-metal).is_empty():
                lo = mid
            else:
                hi = mid-1
        return {'measured_nm':lo}
    x,y,r,t = bounds(cut)
    a,b,c,d = bounds(pad)
    margins = [x-a,y-b,c-r,d-t]
    pairs = [([[x,y],[x,t]],[[a,b],[a,d]]), ([[x,y],[r,y]],[[a,b],[c,b]]),
             ([[r,y],[r,t]],[[c,b],[c,d]]), ([[x,t],[r,t]],[[a,d],[c,d]])]
    return dict(measured_nm=min(margins), edges=list(pairs[margins.index(min(margins))]), pad=pad['id'])


def finding_evidence(project, shapes, issue):
    keys = ('code','message','object','cell_id','bbox','edges','layer','conductor','minimum_nm','measured_nm',
            'rule_source','rule','deck','source','source_design_hash','remediation','net','shape_ids','objects')
    data = {k:clone(issue[k]) for k in keys if k in issue}
    if data.get('rule_source'):
        tech=technology(project)
        data['rule_source'] += ' · ' + tech['name'] + ' · ' + str(tech.get('revision',''))
    if issue.get('code') == 'ENCLOSURE' and 'conductor' in issue:
        cut = next((s for s in shapes if s['id']==issue.get('object') and s['layer']==issue['layer']
                    and bounds(s)==issue['bbox']),None)
        if cut:
            data.update(enclosure_evidence(shapes,cut,dict(conductor=issue['conductor'],minimum=issue['minimum_nm'])))
    return data


def on_finding(shape,issue):
    if shape['layer']!=issue.get('layer'):return False
    if issue['code']=='ENCLOSURE':return shape['id']==issue.get('object')
    db=kdb()
    return any(supporting_edge(shape,db.Edge(db.Point(*a),db.Point(*b))) for a,b in issue.get('edges',[]))


def via_repair(project, cid, cut_id, locked=()):
    cell = next(c for c in project['cells'] if c['id']==cid)
    cut = next((s for s in cell['shapes'] if s['id']==cut_id),None)
    if not cut or cut['kind']!='rect':
        raise ValueError('Select a rectangular via cut in its own cell.')
    if cut['layer'] in locked or any(cut.get(k) for k in ('via_group','pcell_id','device_id','generated_device','connected_lead')):
        raise ValueError('The via belongs to a locked layer or a generated group. Edit its owner first.')
    if any(i['cell']==cid for c in project['cells'] for i in c.get('layout_instances',[])):
        raise ValueError('This cell is instantiated elsewhere. Review the enclosing instances before moving its via.')
    shapes = flatten_layout(project,cid)
    rules = [r for r in enclosure_rules(technology(project)) if r['cut']==cut['layer']]
    if not rules:
        raise ValueError('The active technology has no via enclosure rule for this cut.')
    x,y,r,t = bounds(cut)
    intervals = []
    for rule in rules:
        pad = rectangular_pad(shapes,cut,rule)
        if pad is None:
            raise ValueError('A move needs one unambiguous rectangular landing pad on each conductor.')
        a,b,c,d = bounds(pad)
        m = rule['minimum']
        intervals.append((a+m-x,b+m-y,c-m-r,d-m-t))
    grid = project['pdk']['grid']
    def shift(axis):
        low = math.ceil(max(i[axis] for i in intervals)/grid)
        high = math.floor(min(i[axis+2] for i in intervals)/grid)
        if low > high:
            raise ValueError('No grid-aligned move fits inside both landing pads.')
        return max(low,min(high,0))*grid
    dx,dy = shift(0),shift(1)
    if not (dx or dy):
        raise ValueError('This via already meets the declared enclosure rules.')
    changed = clone(cut)
    changed['points'] = [[px+dx,py+dy] for px,py in cut['points']]
    before_issues = full(project,cid)['issues']
    after_issues = checked_change(project,cid,cut,changed,before_issues)
    def target(issues):
        return [i for i in issues if i['code']=='ENCLOSURE' and i.get('object')==cut_id]
    if not target(before_issues) or target(after_issues):
        raise ValueError('The geometry checker did not verify that this move clears the via enclosure finding.')
    return dict(original=cut, proposed=changed, dx=dx,dy=dy, before_count=len(before_issues),
                after_count=len(after_issues), cleared=len(target(before_issues)), origin=design_digest(project))


def inspect_selection(project,cid,selection,net,marker):
    from .live_geometry import check_enclosures
    from .spatial import SpatialIndex
    scope=LayoutScope(project,cid,selection,net,marker)
    if marker or (selection and not scope.selected_shapes) or not scope.shapes:return scope
    selected=SpatialIndex((bounds(s),s) for s in scope.selected_shapes)
    def related(issue):
        if not selection:return True
        return any(on_finding(s,issue) for s in selected.query(issue['bbox']))
    try:
        issues=check_enclosures(project,cid,scope.shapes) if any(s['layer'] in scope.cuts for s in (scope.selected_shapes or scope.shapes)) else []
        issues.extend(i for i in drc(project,cid) if i['code'] in ('WIDTH','SPACE'))
        scope.findings=[i for i in issues if related(i)]
    except ValueError as exc:
        scope.findings_note=str(exc)
    if selection and scope.findings:
        scope.marker=finding_evidence(project,scope.shapes,scope.findings[0])
    return scope


class LayoutScope:
    def __init__(self, project, cid, selection, net='', marker=None):
        self.project, self.cid = project,cid
        self.origin = design_digest(project)
        self.cell = next(c for c in project['cells'] if c['id']==cid)
        self.shapes = flatten_layout(project,cid)
        self.source_shapes = {s['id']:s for c in project['cells'] for s in c['shapes']} if self.cell.get('layout_instances') else {}
        self.by_net = defaultdict(list)
        self.devices = {d['id']:d for d in self.cell['devices']}
        from .physical_cells import terminals
        self.physical_pins = terminals(project,cid)
        self.cuts = {r['cut'] for r in enclosure_rules(technology(project))}
        check = connectivity(project,cid)
        resolved = {shape_key(s):g['net'] for g in check['net_regions'] for s in g['shapes']}
        ids = set(selection)
        self.selected_devices = set(self.devices) & ids
        for pin in self.physical_pins:
            if pin['device_id'] in self.devices and ('pin:'+pin['id'] in ids or pin['id'] in ids):
                self.selected_devices.add(pin['device_id'])
        self.selected_nets = set(filter(None,[net]))
        for dev_id in self.selected_devices & self.devices.keys():
            self.selected_nets.update(self.devices[dev_id]['nets'].values())
        for w in self.cell.get('wires',[]):
            if w['id'] in ids:
                self.selected_nets.add(w['net'])
        for item in self.cell.get('labels',[]):
            if item['id'] in ids:
                self.selected_nets.add(item['name'])
        for s in self.shapes:
            if s['id'] in ids and s.get('device_id') in self.devices:
                self.selected_devices.add(s['device_id'])
            name = resolved.get(shape_key(s)) or s.get('net')
            if name:
                self.by_net[name].append(s)
                if s['id'] in ids or s.get('device_id') in ids:
                    self.selected_nets.add(name)
        self.selection = sorted(ids)
        self.selected_shapes = [s for s in self.shapes if s['id'] in ids]
        self.net_names = sorted(set(self.by_net) | {n for d in self.devices.values() for n in d['nets'].values() if n})
        self.primary = net if net in self.net_names else next(iter(sorted(self.selected_nets & set(self.net_names))),'')
        self.marker = finding_evidence(project,self.shapes,marker) if marker else None
        self.findings = [marker] if marker else []
        self.findings_note = ''
        self.connectivity_issues = check['issues']

    def finding_nets(self,issue):
        from .spatial import SpatialIndex
        if not hasattr(self,'finding_index'):
            self.finding_index=SpatialIndex((bounds(s),(s,n)) for n,shapes in self.by_net.items() for s in shapes)
        return sorted({n for s,n in self.finding_index.query(issue['bbox']) if on_finding(s,issue)})

    def metrics(self, net):
        shapes = self.by_net.get(net,[])
        originals = [self.source_shapes.get(s.get('source_id'),s) for s in shapes]
        paths = [s for s in originals if s['kind']=='path']
        wires = [s for s in shapes if s['layer'] not in self.cuts]
        rectangles = Counter()
        for s in originals:
            if s['kind']=='rect' and s['layer'] not in self.cuts:
                a,b,c,d = bounds(s)
                rectangles[(s['layer'],min(c-a,d-b)/1000,max(c-a,d-b)/1000)] += 1
        return dict(net=net,path_length_um=sum(math.dist(a,b) for s in paths for a,b in zip(s['points'],s['points'][1:]))/1000,
                    path_count=len(paths), widths_um=sorted({s['width']/1000 for s in paths}),
                    layers=sorted({s['layer'] for s in wires}),via_cuts=sum(s['layer'] in self.cuts for s in shapes),
                    other_shapes=len(wires)-len([s for s in paths if s['layer'] not in self.cuts]),
                    rectangles=[dict(layer=l,width_um=w,span_um=v,count=count)
                                for (l,w,v),count in rectangles.most_common(12)])

    def terminal_ids(self, net):
        return [(d['id'],pin) for d in self.devices.values() for pin,n in d['nets'].items() if n==net]

    def sources(self, rows, nets):
        sources = []
        for row in reversed(rows):
            job,result = row.get('job',{}), row.get('result') or {}
            if (job.get('project',{}).get('id')!=self.project['id']
                    or row.get('state')!='Complete' or not result):
                continue
            traces = {k.casefold():k for k in result.get('traces',{})}
            for n in nets:
                if n.casefold() in traces and result.get('x') and result.get('cell_id',job.get('cell'))==self.cid:
                    sources.append((row,'waveform',traces[n.casefold()]))
            if self.selected_devices and result.get('cell_id',job.get('cell'))==self.cid:
                cell=next((c for c in job['project']['cells'] if c['id']==self.cid),{})
                currents={k.casefold():k for k in result.get('currents',{})}
                operating={k.casefold() for key in ('device_operating_point','operating_currents') for k in result.get(key,{})}
                for dev in cell.get('devices',[]):
                    if dev['id'] not in self.selected_devices:continue
                    name=dev['name'].casefold()
                    if name in operating:sources.append((row,'device operating point',dev['name']))
                    if name in currents and result.get('x'):sources.append((row,'device current',currents[name]))
            ext = result.get('extraction') or {}
            if (isinstance(ext,dict) and ext.get('design_hash')==self.origin and ext.get('cell_id')==self.cid
                    and ext.get('network_hash') and ext['network_hash']==result.get('provenance',{}).get('network_hash')
                    and ext['network_hash']==digest({k:v for k,v in ext.items() if k!='network_hash'})):
                sources.append((row,'extraction',''))
            lumped = result.get('physical_result') or ext
            if (isinstance(lumped,dict) and result.get('settings',{}).get('type') in ('parasitics','post_layout')
                    and result.get('cell_id')==self.cid and lumped.get('design_hash')==self.origin
                    and lumped.get('pdk_hash')==digest(self.project['pdk']) and lumped.get('capacitors')):
                sources.append((row,'ground capacitance',''))
        return sources


def net_rc(extraction, net):
    """Sum distributed segments on a connected extracted net; separate coupling from ground C."""
    links = defaultdict(set)
    for r in extraction['resistors']:
        links[r['p']].add(r['n'])
        links[r['n']].add(r['p'])
    seeds = {m['node'] for m in extraction['terminal_mapping'] if m['net']==net}
    nodes = {v for s in extraction['resistors']+extraction['capacitors'] for v in (s['p'],s['n'])}
    if net in nodes:
        seeds.add(net)
    if not seeds:
        return None
    group = set(seeds)
    while seeds:
        new = links[seeds.pop()]-group
        group.update(new)
        seeds.update(new)
    return dict(segment_resistance_ohm=sum(r['value'] for r in extraction['resistors'] if r['p'] in group),
                ground_cap_fF=1e15*sum(c['value'] for c in extraction['capacitors'] if c['kind']!='coupling' and c['p'] in group),
                coupling_cap_fF=1e15*sum(c['value'] for c in extraction['capacitors'] if c['kind']=='coupling'
                                        and ((c['p'] in group)!=(c['n'] in group))))
