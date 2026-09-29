"""Actual-engine smoke for transformed hierarchy flattening in Magic RC extraction.

This compares native hierarchy to an independently flattened KLayout reference;
it does not establish fabrication signoff or broad process-extraction accuracy.
"""
import argparse
import json
from pathlib import Path
import re
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from icstudio.model import clone, uid, device, validate, save_project, file_digest
from icstudio.sky130_layout import reference_project, generate_inverter
from icstudio.physical_cells import place, ports, transform, assign_port
from icstudio.interchange import export_layout
from icstudio.layout import kdb
from icstudio.external_tools import extraction_commands, executable_info
from icstudio.silicon_flow import magic_script
from icstudio.engines import netgen_lvs, require_lvs_match


def fixture(technology):
    project, leaf_id = reference_project(technology)
    generate_inverter(project, leaf_id)
    leaf = next(c for c in project['cells'] if c['id'] == leaf_id)
    root = {'id': uid(), 'name': 'hierarchy_rc_coupon', 'ports': ['A0','Y0','P0','A1','Y1','P1','VGND'],
            'devices': [], 'shapes': []}
    project['cells'] = [leaf, root]; project['top'] = root['id']
    for index, (x,y,rotation,mirror) in enumerate(((0,0,0,False),(30000,30000,90,True))):
        mapping = {'A':f'A{index}','Y':f'Y{index}','VPWR':f'P{index}','VGND':'VGND'}
        item = device('X', f'XINV{index}', x=300+index*300,y=200,cell=leaf_id,nets=mapping)
        root['devices'].append(item)
        instance = place(project,root['id'],item['id'],x,y,rotation,mirror)
        for pin in ports(project,leaf_id):
            if index and pin['name']=='VGND': continue
            pt = transform(instance) * kdb().Point(*pin['point'])
            assign_port(project,root['id'],mapping[pin['name']],pin['layer'],[pt.x,pt.y])
    return validate(project), root['id']


def devices_and_terminals(deck):
    text = re.sub(r'\n\s*\+\s*',' ',Path(deck).read_text())
    parent = {}; mos = []; counts={'mos':0,'resistors':0,'capacitors':0}
    def find(node):
        parent.setdefault(node,node)
        if parent[node]!=node: parent[node]=find(parent[node])
        return parent[node]
    def union(a,b): parent[find(a)] = find(b)
    for line in text.splitlines():
        fields=line.split()
        if not fields or fields[0].startswith(('*','.')): continue
        kind=fields[0][0].lower()
        if kind=='r':
            counts['resistors']+=1;union(fields[1],fields[2])
        elif kind=='c':counts['capacitors']+=1
        elif kind in ('m','x') and len(fields)>5 and ('nfet' in fields[5] or 'pfet' in fields[5]):
            counts['mos']+=1;mos.append((fields[5],fields[1:5]))
    external=['A0','Y0','P0','A1','Y1','P1','VGND']
    names={find(name):name for name in external}
    if len(names)!=len(external):raise AssertionError('Resistance network shorts independent external terminals.')
    normalized=[]
    for model,nodes in mos:
        try:nets=[names[find(node)] for node in nodes]
        except KeyError as exc:raise AssertionError('Device terminal has no resistance path to a declared port: '+str(nodes)) from exc
        # Drain/source are interchangeable for these symmetric MOS fixtures.
        normalized.append([model,nets[1],sorted((nets[0],nets[2])),nets[3]])
    expected=[]
    for index in (0,1):
        expected.extend([['sky130_fd_pr__nfet_01v8',f'A{index}',sorted((f'Y{index}','VGND')),'VGND'],
                         ['sky130_fd_pr__pfet_01v8',f'A{index}',sorted((f'Y{index}',f'P{index}')),f'P{index}']])
    if sorted(normalized)!=sorted(expected):raise AssertionError('Transformed hierarchy changed transistor terminal nets: '+str(normalized))
    if counts['resistors']<1 or counts['capacitors']<1:raise AssertionError('No distributed RC network extracted.')
    return {'counts':counts,'terminal_nets':sorted(normalized)}


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--pdk',type=Path,required=True);parser.add_argument('--magic',type=Path,required=True)
    parser.add_argument('--netgen',type=Path,required=True);parser.add_argument('--out',type=Path,required=True)
    args=parser.parse_args();out=args.out.resolve()
    if out.exists() and any(out.iterdir()):raise ValueError('Choose an empty qualification folder.')
    out.mkdir(parents=True,exist_ok=True)
    pdk=args.pdk.resolve();manifest=json.loads((pdk/'package.json').read_text());technology=clone(manifest['technology'])
    technology.update(package_root=str(pdk),package_lock={key:manifest[key] for key in ('id','revision','files')})
    project,cid=fixture(technology);cell=next(c for c in project['cells'] if c['id']==cid)
    save_project(project,out/'input.icproj');export_layout(project,out/'hierarchical.gds')
    layout=kdb().Layout();layout.read(str(out/'hierarchical.gds'));top=layout.cell(cell['name'])
    for child in layout.each_cell():
        if child.cell_index()==top.cell_index():continue
        for layer in layout.layer_indexes():
            for shape in list(child.shapes(layer).each()):
                if shape.is_text():shape.delete()
    top.flatten(-1,False);layout.write(str(out/'reference-flat.gds'))
    commands,settings=extraction_commands('rc')
    results={}
    for name,source in [('hierarchical','hierarchical.gds'),('reference','reference-flat.gds')]:
        directory=out/name
        log=magic_script(str(args.magic.resolve()),str(pdk/'libs.tech/magic/sky130A.tech'),out/source,
                         cell['name'],cell['ports'],directory,commands+'ext2spice -o extracted.spice')
        normalization=json.loads((directory/'rc-normalization.json').read_text())
        flattened=normalization['physical_hierarchy']['flattened']
        if flattened!=(name=='hierarchical'):raise AssertionError('Unexpected hierarchy flatten marker for '+name)
        results[name]={**devices_and_terminals(directory/'extracted.spice'),
                       'flattened':flattened,'normalization':normalization,
                       'deck_sha256':file_digest(directory/'extracted.spice')}
    if results['hierarchical']['counts']!=results['reference']['counts']:
        raise AssertionError('Hierarchical and independent flat reference device/RC inventories differ.')
    log=netgen_lvs(str(args.netgen.resolve()),out/'hierarchical/extracted.spice',cell['name'],
                   out/'reference/extracted.spice',cell['name'],pdk/'libs.tech/netgen/sky130A_setup.tcl',out/'equivalence')
    require_lvs_match(log)
    report={'status':'passed','scope':'Two generated SKY130 inverters, one mirrored/rotated, independent local input/output/power nets and common substrate. Native Magic hierarchy flattening compared to independently flattened KLayout geometry. This is a bounded integration smoke, not foundry signoff.',
            'checks':['actual Magic hierarchy flatten marker','four MOS and distributed RC inventory','every transistor terminal retains its intended external net through the resistor graph','no accidental joining of repeated child-local labels','strict Netgen unique match against independent flat reference'],
            'tools':{'magic':executable_info(args.magic),'netgen':executable_info(args.netgen)},
            'technology_sha256':file_digest(pdk/'libs.tech/magic/sky130A.tech'),
            'netgen_setup_sha256':file_digest(pdk/'libs.tech/netgen/sky130A_setup.tcl'),
            'script_sha256':file_digest(Path(__file__)), 'results':results}
    (out/'report.json').write_text(json.dumps(report,indent=2,allow_nan=False)+'\n')
    print(json.dumps({'status':'passed','counts':results['hierarchical']['counts'],'report':str(out/'report.json')}))


if __name__=='__main__':main()
