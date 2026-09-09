"""Declared-coefficient interconnect RC: segmented Manhattan routes and ideal pads.

Same-layer parallel coupling uses the declared 1 µm gap coefficient scaled by
inverse edge gap. This is a geometric estimate, not a field solver or device extractor.
"""
import math
from .model import clone,digest,design_digest,scalar,device,validate
from .layout import polygon,kdb
from .spatial import SpatialIndex


def extract(p,cid,section_nm=5000,coupling_distance_nm=5000):
    from .physical import connectivity
    from .physical_cells import terminals
    c=next(c for c in p['cells'] if c['id']==cid)
    if c.get('layout_instances'):raise ValueError('The coefficient RC estimator requires a flat physical cell. Use the existing process extraction flow for hierarchy.')
    if not 100<=section_nm<=1000000:raise ValueError('RC section length must be 0.1–1,000 µm.')
    check=connectivity(p,cid)
    if check['issues']:raise ValueError('Resolve physical connectivity findings before RC extraction: '+check['issues'][0]['message'])
    coeff=p['pdk'].get('parasitics',{})
    for layer,data in coeff.items():
        for key in ('sheet_ohm','cap_f_per_um2','edge_f_per_um','coupling_f_per_um'):
            if scalar(data.get(key,0))<0:raise ValueError(layer+': RC coefficients cannot be negative.')
    if not 0<=coupling_distance_nm<=1000000:raise ValueError('Coupling distance must be 0–1,000 µm.')
    conductors=set(p['pdk'].get('connectivity',{}).get('conductors',['metal1','metal2']));netshapes=[(group['net'],s) for group in check['net_regions'] for s in group['shapes']];lines=[];pads=[];cuts=[]
    for net,s in netshapes:
        if s['layer'] not in conductors:cuts.append((net,s));continue
        if s['kind']!='path':pads.append((net,s));continue
        if s['layer'] not in coeff or scalar(coeff[s['layer']].get('sheet_ohm',0))<=0:raise ValueError(s['layer']+': declare positive sheet_ohm for distributed resistance.')
        for a,b in zip(s['points'],s['points'][1:]):
            if a==b:continue
            if a[0]!=b[0] and a[1]!=b[1]:raise ValueError('RC estimator supports Manhattan route centerlines only.')
            length=abs(a[0]-b[0])+abs(a[1]-b[1]);count=max(1,math.ceil(length/section_nm));pts={tuple(a),tuple(b)}
            for i in range(1,count):pts.add(tuple(a[k]+(b[k]-a[k])*i/count for k in (0,1)))
            lines.append({'net':net,'layer':s['layer'],'a':tuple(a),'b':tuple(b),'width':s['width'],'points':pts,'shape':s['id']})
    if not lines:raise ValueError('Draw at least one conducting path to estimate distributed RC. Rectangular and polygon pads are treated as ideal conductors.')
    if len(lines)>2000:raise ValueError('Use a process extractor for more than 2,000 route segments.')
    keys={};parents=[]
    def node(key):
        if key not in keys:keys[key]=len(parents);parents.append(len(parents))
        return keys[key]
    def root(i):
        while parents[i]!=i:parents[i]=parents[parents[i]];i=parents[i]
        return i
    def union(a,b):parents[root(a)]=root(b)
    def project(line,pt):
        a,b=line['a'],line['b'];axis=0 if a[1]==b[1] else 1;other=1-axis;v=min(max(pt[axis],min(a[axis],b[axis])),max(a[axis],b[axis]));q=list(a);q[axis]=v;return tuple(q)
    def linekey(line,pt):return ('point',line['layer'],round(pt[0],9),round(pt[1],9))
    lineboxes=[]
    for i,line in enumerate(lines):
        a,b=line['a'],line['b'];half=line['width']/2;lineboxes.append(((min(a[0],b[0])-half,min(a[1],b[1])-half,max(a[0],b[0])+half,max(a[1],b[1])+half),i))
    index=SpatialIndex(lineboxes)
    for i,line in enumerate(lines):
        a,b=line['a'],line['b'];axis=0 if a[1]==b[1] else 1
        for j in index.query(lineboxes[i][0]):
            if j<=i:continue
            other=lines[j]
            if other['layer']!=line['layer']:continue
            oa,ob=other['a'],other['b'];otheraxis=0 if oa[1]==ob[1] else 1
            candidates=[]
            if axis!=otheraxis:
                q=[0.,0.];q[axis]=oa[axis];q[otheraxis]=a[otheraxis];candidates=[tuple(q)]
            elif a[1-axis]==oa[1-axis]:
                overlap=min(max(a[axis],b[axis]),max(oa[axis],ob[axis]))-max(min(a[axis],b[axis]),min(oa[axis],ob[axis]))
                if overlap>0:raise ValueError('Overlapping route centerlines must be consolidated before RC extraction.')
                candidates=[a,b,oa,ob]
            for pt in candidates:
                if project(line,pt)==pt and project(other,pt)==pt:line['points'].add(pt);other['points'].add(pt)
    padrefs=[]
    for net,s in pads+cuts:
        key=node(('pad',s['id']));padrefs.append((net,s,key))
        poly=polygon(s);box=poly.bbox()
        for i in index.query((box.left,box.bottom,box.right,box.top)):
            line=lines[i]
            if line['layer']!=s['layer']:continue
            pt=project(line,((box.left+box.right)/2,(box.bottom+box.top)/2))
            if poly.inside(kdb().Point(round(pt[0]),round(pt[1]))):line['points'].add(pt);union(key,node(linekey(line,pt)))
    vias=p['pdk'].get('connectivity',{}).get('vias',[['metal1','via1','metal2']]);joins={(a,b) for a,v,b in vias for a,b in ((a,v),(v,a),(v,b),(b,v))};padindex=SpatialIndex([((b.left,b.bottom,b.right,b.top),i) for i,(_,s,_) in enumerate(padrefs) for b in [polygon(s).bbox()]])
    for i,(net,s,key) in enumerate(padrefs):
        r=kdb().Region(polygon(s));box=polygon(s).bbox()
        for j in padindex.query((box.left,box.bottom,box.right,box.top)):
            if j<=i:continue
            n,t,target=padrefs[j]
            if (s['layer']==t['layer'] or (s['layer'],t['layer']) in joins) and not r.interacting(kdb().Region(polygon(t))).is_empty():union(key,target)
    ds={d['id']:d for d in c['devices']};pins={};anchors={}
    for pin in terminals(p,cid):
        pt=pin['point'];net=ds[pin['device_id']]['nets'][pin['pin']];hits=[]
        for n,s,key in padrefs:
            if s['layer']==pin['layer'] and polygon(s).inside(kdb().Point(*pt)):hits.append(key)
        for i in index.query((pt[0],pt[1],pt[0],pt[1])):
            line=lines[i]
            if line['layer']!=pin['layer']:continue
            q=project(line,pt)
            if math.dist(q,pt)<=line['width']/2:line['points'].add(q);hits.append(node(linekey(line,q)))
        if not hits:raise ValueError('Terminal cannot be represented by the RC centerline/pad model.')
        for target in hits[1:]:union(hits[0],target)
        pins[(pin['device_id'],pin['pin'])]=hits[0];anchors.setdefault(net,hits[0])
    edges=[]
    for line in lines:
        points=sorted(line['points']);data=coeff[line['layer']];sheet=scalar(data['sheet_ohm'])
        for a,b in zip(points,points[1:]):
            length=math.dist(a,b)
            if length:edges.append({**{k:v for k,v in line.items() if k not in ('a','b','points')},'a':a,'b':b,'left':node(linekey(line,a)),'right':node(linekey(line,b)),'resistance':sheet*length/line['width']})
    if len(edges)>2000:raise ValueError('More than 2,000 RC sections. Increase section length or use process extraction.')
    # Named cell ports anchor the externally observable net at their physical location.
    for port in c.get('layout_ports',[]):
        pt=port['point']
        for net,s,key in padrefs:
            if s['layer']==port['layer'] and polygon(s).inside(kdb().Point(*pt)):anchors[port['name']]=key;break
    names={root(key):net for net,key in anchors.items()};counter=0
    used={n for d in c['devices'] for n in d['nets'].values()}
    def name(key):
        nonlocal counter
        key=root(key)
        if key not in names:
            counter+=1;candidate='rc_node_'+str(counter)
            while candidate in used:counter+=1;candidate='rc_node_'+str(counter)
            names[key]=candidate;used.add(candidate)
        return names[key]
    resistors=[];capacitors=[]
    def cap(a,b,value,kind,**extra):
        if value<0 or not math.isfinite(value):raise ValueError('Capacitance coefficients must be finite and non-negative.')
        if a!=b and value>0:capacitors.append({'p':a,'n':b,'value':value,'kind':kind,**extra})
    for edge in edges:
        left,right=name(edge['left']),name(edge['right']);data=coeff[edge['layer']];length=math.dist(edge['a'],edge['b'])*1e-3;width=edge['width']*1e-3
        if left!=right:resistors.append({'p':left,'n':right,'value':edge['resistance'],'shape':edge['shape'],'layer':edge['layer']})
        value=length*width*scalar(data.get('cap_f_per_um2',0))+2*length*scalar(data.get('edge_f_per_um',0));cap(left,'0',value/2,'ground');cap(right,'0',value/2,'ground')
    for net,s,key in padrefs:
        if s['layer'] not in coeff or s.get('pcell_id'):continue
        data=coeff[s['layer']];poly=polygon(s);value=poly.area()*1e-6*scalar(data.get('cap_f_per_um2',0))+poly.perimeter()*1e-3*scalar(data.get('edge_f_per_um',0));cap(name(key),'0',value,'pad')
    edgeindex=SpatialIndex([((min(e['a'][0],e['b'][0])-coupling_distance_nm,min(e['a'][1],e['b'][1])-coupling_distance_nm,max(e['a'][0],e['b'][0])+coupling_distance_nm,max(e['a'][1],e['b'][1])+coupling_distance_nm),i) for i,e in enumerate(edges)])
    for i,a in enumerate(edges):
        if not scalar(coeff[a['layer']].get('coupling_f_per_um',0)):continue
        axis=0 if a['a'][1]==a['b'][1] else 1;other=1-axis
        box=(min(a['a'][0],a['b'][0]),min(a['a'][1],a['b'][1]),max(a['a'][0],a['b'][0]),max(a['a'][1],a['b'][1]))
        for j in edgeindex.query(box):
            b=edges[j]
            if j<=i or a['net']==b['net'] or a['layer']!=b['layer'] or b['a'][other]!=b['b'][other]:continue
            gap=abs(a['a'][other]-b['a'][other])-(a['width']+b['width'])/2;overlap=min(max(a['a'][axis],a['b'][axis]),max(b['a'][axis],b['b'][axis]))-max(min(a['a'][axis],a['b'][axis]),min(b['a'][axis],b['b'][axis]))
            if not 0<gap<=coupling_distance_nm or overlap<=0:continue
            value=scalar(coeff[a['layer']]['coupling_f_per_um'])*(overlap*1e-3)/(gap*1e-3)
            cap(name(a['left']),name(b['left']),value/2,'coupling',shapes=[a['shape'],b['shape']]);cap(name(a['right']),name(b['right']),value/2,'coupling',shapes=[a['shape'],b['shape']])
    mapping=[{'device_id':did,'pin':pin,'node':name(key),'net':ds[did]['nets'][pin]} for (did,pin),key in pins.items()]
    # Every expected net must still connect through the extracted resistor graph.
    links={}
    for r in resistors:links.setdefault(r['p'],set()).add(r['n']);links.setdefault(r['n'],set()).add(r['p'])
    for net in anchors:
        reached={net};queue=[net]
        while queue:
            for target in links.get(queue.pop(),set())-reached:reached.add(target);queue.append(target)
        if any(m['node'] not in reached for m in mapping if m['net']==net) or any(name(e[k]) not in reached for e in edges if e['net']==net for k in ('left','right')):raise ValueError('Physical contact cannot be represented by the centerline RC model on '+net+'. Use process extraction for this geometry.')
    return {'schema':1,'design_hash':design_digest(p),'pdk_hash':digest(p['pdk']),'coefficient_hash':digest(coeff),'cell_id':cid,'resistors':resistors,'capacitors':capacitors,'terminal_mapping':mapping,'sections':len(edges),'settings':{'section_nm':section_nm,'coupling_distance_nm':coupling_distance_nm},'qualification':'Declared-coefficient Manhattan interconnect estimate: distributed path resistance, ground capacitance and same-layer parallel coupling. Pads are ideal; no device recognition, cross-layer coupling or field-solver qualification.'}


def apply(p,cid,extraction):
    if extraction['design_hash']!=design_digest(p) or extraction['pdk_hash']!=digest(p['pdk']):raise ValueError('RC extraction is stale. Extract the current design again.')
    q=clone(p);c=next(c for c in q['cells'] if c['id']==cid)
    from .wiring import rebuild
    if 'wires' in c:rebuild(c,q)
    for key in ('wires','labels','junctions'):c.pop(key,None)
    by={d['id']:d for d in c['devices']}
    for row in extraction['terminal_mapping']:
        d=by[row['device_id']];d['nets'][row['pin']]=row['node']
        if d.get('net_labels') is not None:d['net_labels'][row['pin']]=row['node']
    names={d['name'].casefold() for d in c['devices']}
    for kind,rows in [('R',extraction['resistors']),('C',extraction['capacitors'])]:
        for i,row in enumerate(rows):
            name=kind+'ex'+str(i+1)
            while name.casefold() in names:name+='x'
            names.add(name.casefold());c['devices'].append(device(kind,name,value=str(row['value']),nets={'p':row['p'],'n':row['n']}))
    validate(q);return q


def compare_job(p,job,directory,progress=lambda *_:None):
    from .simulation import run
    from .engines import run_ngspice
    from .specifications import evaluate_rows,for_job
    cid=job['settings'].get('layout_cell',job['cell']);ext=extract(p,cid,int(job['settings'].get('section_nm',5000)));q=apply(p,cid,ext);analysis=job['settings']['analysis'];waves=[]
    for i,source in enumerate((p,q)):
        (directory/('before' if i==0 else 'after')).mkdir(parents=True,exist_ok=True)
        notify=lambda f,m,i=i:progress((i+f)/2,m)
        if job.get('testbench_id'):
            from .testbenches import simulate,get
            wave=simulate(source,get(source,job['testbench_id']),job['executable'],directory/('before' if i==0 else 'after'),progress=notify)
        else:wave=run(source,job['cell'],analysis,notify) if job['engine']=='builtin' else run_ngspice(source,job['cell'],analysis,job['executable'],directory/('before' if i==0 else 'after'),notify)
        waves.append(wave)
    specs=for_job(job);before,after=[evaluate_rows(specs,w) for w in waves]
    rows=[{'name':a['name'],'before':a,'after':b,'delta':b['value']-a['value'] if a['value'] is not None and b['value'] is not None else None} for a,b in zip(before,after)]
    result={**waves[1],'design_hash':design_digest(p),'revision':p['revision'],'settings':{'type':'rc_compare','analysis':analysis},'extraction':ext,'specifications':after,'rc_comparison':rows,'before_waveform':waves[0],'after_waveform':waves[1]};return result
