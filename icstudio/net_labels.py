"""Electrical labels with explicit attachment and independently movable artwork."""
import math
from .model import uid, NET

def point(label, cell, project=None):
    from .wiring import pins
    a=label['anchor']
    return pins(cell,project)[(a['id'],a['pin'])] if a['kind']=='pin' else list(a['point'])

def target(label):
    a=label['anchor']
    return (a['id'],a['pin']) if a['kind']=='pin' else ('wire',a['id']) if a['kind']=='wire' else None

def entries(cell):
    for d in cell['devices']:
        for pin,name in list(d.get('net_labels',{}).items()):yield (d['id'],pin),d['net_labels'],pin,name
    for label in cell.get('labels',[]):yield ('label',label['id']),label,'name',label['name']

def add(cell,name,anchor,project=None,kind='net_label'):
    from .wiring import rebuild,migrate
    migrate(cell,project)
    if 'wires' not in cell:raise ValueError('Move overlapping pins apart before placing labels in this legacy cell.')
    if not isinstance(name,str) or not NET.fullmatch(name):raise ValueError('Use a net name such as VDD, out, or 0 for ground.')
    if kind=='ground':name='0'
    label={'id':uid(),'kind':kind,'name':name,'anchor':anchor,'offset':[10,-12] if kind=='net_label' else [0,0],'rotation':0}
    cell.setdefault('labels',[]).append(label)
    try:rebuild(cell,project)
    except Exception:cell['labels'].remove(label);raise
    return label['id']

def rename(cell,ident,name,project=None,whole_net=False):
    from .wiring import graph,rebuild
    if not isinstance(name,str) or not NET.fullmatch(name):raise ValueError('Invalid net name. Ground is 0.')
    groups=graph(cell,project,labels=whole_net);root=groups[('label',ident)]
    for key,obj,field,old in entries(cell):
        if groups[key]==root:
            obj[field]=name
            if obj.get('kind')=='ground' and name!='0':obj['kind']='net_label';obj['offset']=[10,-12]
    rebuild(cell,project)

def reconcile(cell,old,project=None):
    """Keep attached labels on edited geometry; delete with their target."""
    from .wiring import pins,nearest,on_segment
    positions=pins(cell,project);wires={w['id']:w for w in cell.get('wires',[])};kept=[]
    for label in cell.get('labels',[]):
        a=label['anchor']
        if a['kind']=='pin' and (a['id'],a['pin']) not in positions:continue
        if a['kind']=='wire':
            w=wires.get(a['id'])
            if w is None:continue
            if not any(on_segment(a['point'],x,y) for x,y in zip(w['points'],w['points'][1:])):
                a['point']=min((nearest(a['point'],x,y) for x,y in zip(w['points'],w['points'][1:])),key=lambda p:math.dist(p,a['point']))
        kept.append(label)
    cell['labels']=kept

def validate(cell,objid,project):
    from .wiring import pins,on_segment
    labels=cell.get('labels',[]);positions=pins(cell,project);wires={w['id']:w for w in cell.get('wires',[])}
    if not isinstance(labels,list) or len(labels)>5000:raise ValueError('A cell supports at most 5,000 labels.')
    def coord(p):
        if not isinstance(p,list) or len(p)!=2 or any(not isinstance(v,(int,float)) or not math.isfinite(v) or abs(v)>1e7 for v in p):raise ValueError('Invalid label coordinate.')
    case_names={}
    for _,_,_,name in entries(cell):
        if isinstance(name,str):
            if name.casefold() in case_names and case_names[name.casefold()]!=name:raise ValueError('Net names differing only by case are not portable to SPICE.')
            case_names[name.casefold()]=name
    for l in labels:
        objid(l['id'])
        if l.get('kind') not in ('net_label','ground') or not isinstance(l.get('name'),str) or not NET.fullmatch(l['name']):raise ValueError('Invalid placed net label.')
        if l['kind']=='ground' and l['name']!='0':raise ValueError('Ground symbols must name net 0.')
        if l.get('rotation') not in (0,90,180,270):raise ValueError('Invalid label rotation.')
        coord(l.get('offset'));a=l.get('anchor',{})
        if a.get('kind')=='pin':
            if (a.get('id'),a.get('pin')) not in positions:raise ValueError('Label is attached to a missing pin.')
        elif a.get('kind') in ('wire','point'):
            coord(a.get('point'))
            if a['kind']=='wire':
                w=wires.get(a.get('id'))
                if not w or not any(on_segment(a['point'],x,y) for x,y in zip(w['points'],w['points'][1:])):raise ValueError('Label anchor is not on its wire.')
        else:raise ValueError('Invalid label attachment.')

def describe(cell,name,project=None):
    from .wiring import graph
    physical=graph(cell,project,labels=False);members=[];ids=set();roots=set()
    for d in cell['devices']:
        for pin,net in d['nets'].items():
            if net==name:members.append({'device_id':d['id'],'device':d['name'],'pin':pin});ids.add(d['id']);roots.add(physical[(d['id'],pin)])
    wires=[w for w in cell.get('wires',[]) if w.get('net')==name];labels=[l for l in cell.get('labels',[]) if l['name']==name]
    for w in wires:ids.add(w['id']);roots.add(physical[('wire',w['id'])])
    for l in labels:ids.add(l['id']);roots.add(physical[('label',l['id'])])
    return {'name':name,'pins':members,'wires':len(wires),'labels':len(labels),'conductors':len(roots),'ids':sorted(ids)}
