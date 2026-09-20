"""Reviewable native forms for process guards and electrically explicit dummies."""
from .model import clone, scalar
from .sky130_devices import layers, install_guard, install_dummy
from .layout import polygon


def check_layers(studio,candidate,cid):
    before={s['id']:s for c in studio.project['cells'] if c['id']==cid for s in c['shapes']}
    after={s['id']:s for c in candidate['cells'] if c['id']==cid for s in c['shapes']}
    edited=[s for table in (before,after) for key,s in table.items() if before.get(key)!=after.get(key)]
    locked={s['layer'] for s in edited}&studio.layout.locked_layers
    if locked:raise ValueError('Unlock the affected layers before generating: '+', '.join(sorted(locked)))


def apply_candidate(studio,cid):
    def apply(project,candidate):
        # Layer locks can change without changing the project revision while
        # the preview is open, so check them again at the commit boundary.
        check_layers(studio,candidate,cid);project.clear();project.update(clone(candidate))
    return apply


def guard_dialog(studio):
    if not studio.idle_edit():return
    ls=layers(studio.project['pdk']);cid=studio.cid;c=studio.cell;devices={d['id']:d for d in c['devices']}
    ties={}
    for pin in c.get('layout_pins',[]):
        if pin['layer']!=ls['m1'] or pin['device_id'] not in devices:continue
        d=devices[pin['device_id']];net=d['nets'][pin['pin']]
        label=d['name']+'.'+pin['pin']+' · '+net+' ('+', '.join(f'{v/1000:g}' for v in pin['point'])+' µm)'
        ties[label]=(net,dict(layer=pin['layer'],point=clone(pin['point'])))
    if not ties:raise ValueError('Generate a device with a metal1 terminal, then select its existing reference-net terminal for the guard tie.')
    selected=set(studio.selection);members={d['id'] for d in c['devices'] if d['id'] in selected}
    members.update(s.get('generated_device') for s in c['shapes'] if s['id'] in selected and s.get('generated_device'))
    if members-{s.get('generated_device') for s in c['shapes']}:
        raise ValueError('Generate physical footprints for every selected device first.')
    shapes=[s for s in c['shapes'] if s.get('generated_device') in members] if members else c['shapes']
    boxes=[polygon(s).bbox() for s in shapes]
    if not boxes:raise ValueError('Generate physical footprints for the selected devices first.')
    x=min(b.left for b in boxes)-3000;y=min(b.bottom for b in boxes)-3000
    width=max(b.right for b in boxes)-x+3000;height=max(b.top for b in boxes)-y+3000
    fields=[('kind','Guard type',['p+ substrate','n+ well']),('tie','Reference terminal',list(ties)),
            ('x','Outer X (µm)',x/1000),('y','Outer Y (µm)',y/1000),('width','Outer width (µm)',width/1000),
            ('height','Outer height (µm)',height/1000),('thickness','Ring thickness (µm)','0.8')]
    def submit(values):
        spec={key:round(scalar(values[key])*1000) for key in ('x','y','width','height','thickness')}
        spec['kind']='psub' if values['kind']=='p+ substrate' else 'nwell';net,tie=ties[values['tie']]
        def build():
            p=clone(studio.project);record=install_guard(p,cid,spec,net,tie=tie,members=sorted(members));check_layers(studio,p,cid)
            return p,f"Generate a contacted {values['kind']} guard tied to {net} through {values['tie']}.\n{len(record['shape_ids'])} process shapes; {len(members)} selected devices receive an enclosure constraint.\n\nThe ring includes tap, implant, local-interconnect, contacts and metal1; an n+ well guard includes nwell. Review the clear metal1 tie corridor and run process DRC/LVS."
        studio.review_dialog('Generate contacted SKY130 guard',build,apply_candidate=apply_candidate(studio,cid))
    return studio.workflow_form('Contacted SKY130 guard',fields,submit,'The guard surrounds the selected physical devices, or the current cell when nothing is selected. Its existing reference terminal determines the net. An n+ well guard is intended for devices sharing that well.')


def dummy_dialog(studio):
    if not studio.idle_edit():return
    layers(studio.project['pdk']);cid=studio.cid
    nets=sorted({net for d in studio.cell['devices'] for net in d['nets'].values()}|set(studio.cell['ports'])) or ['0']
    names={d['name'].casefold() for d in studio.cell['devices']};index=1
    while ('MDUMMY'+str(index)).casefold() in names:index+=1
    fields=[('name','Schematic name','MDUMMY'+str(index)),('kind','MOS type',['NMOS','PMOS']),('net','Tie all terminals to',nets),
            ('w','Total width (µm)','1'),('l','Length (µm)','1'),('x','X (µm)','0'),('y','Y (µm)','0')]
    def submit(values):
        def build():
            p=clone(studio.project);d=install_dummy(p,cid,values['name'].strip(),values['kind'],values['net'],
                w=str(scalar(values['w'])*1e-6),l=str(scalar(values['l'])*1e-6),
                x=round(scalar(values['x'])*1000),y=round(scalar(values['y'])*1000));check_layers(studio,p,cid)
            return p,f"Add schematic {d['name']} and its contacted layout. D, G, S and B are all explicitly tied to {values['net']}.\nW={values['w']} µm, L={values['l']} µm.\n\nThe dummy remains part of simulation and LVS. Its terminal straps regenerate during a layout ECO. Review nearby spacing and run process DRC/LVS."
        studio.review_dialog('Add tied SKY130 MOS dummy',build,apply_candidate=apply_candidate(studio,cid))
    return studio.workflow_form('Tied SKY130 MOS dummy',fields,submit,'Adds one real schematic MOS and its physical layout in one undoable change. All four terminals are connected to the selected reference net; there are no hidden extracted devices.')
