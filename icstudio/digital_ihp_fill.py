"""Application integration for verified IHP signal-clearance block fill."""
import json
from pathlib import Path
import shutil
import sys

from .model import atomic_write, file_digest
from .digital_ihp_geometry import PATTERNS, require

RECIPE = 'ihp-signal-clearance-block-fill-v1'


def validate(platform):
    policy = platform.get('ihp_fill')
    if policy is None:
        return
    from .digital import relative_path
    require(platform.get('name') == 'ihp-sg13g2' and isinstance(policy,dict) and
            set(policy) == {'recipe','directory','preparation_sha256'} and policy['recipe'] == RECIPE,
            'Unsupported IHP block-fill policy.')
    directory = relative_path(policy['directory'],directory=True)
    locks = {r['path']:r['sha256'] for r in platform.get('files',[])}
    require(locks.get(directory+'/preparation.json') == policy['preparation_sha256'],
            'IHP fill resources are not bound to the platform.')


def implementation_options(r, settings):
    if not settings.get('ihp_fill'):
        return []
    validate(r.platform)
    require(r.platform.get('ihp_fill') and r.platform['name']=='ihp-sg13g2' and
            not r.platform.get('extraction') and not r.config.get('macros'),
            'IHP fill requires its captured standard-cell platform and nominal extraction.')
    require(not settings.get('gf180_fill') and not settings.get('pdn_tcl','').strip() and
            not settings.get('macro_placements') and not settings.get('macro_placement_tcl','').strip(),
            'IHP fill requires standard cells and the captured power grid.')
    return []


def abstract(source, target, gds, inventory):
    """Retain ports and original obstructions; add every metal-fill rectangle."""
    import re
    import klayout.db as k
    from .digital_ihp_geometry import METALS
    text=Path(source).read_text(); top=inventory['top']
    require(re.findall(r'^MACRO (\S+)\s*$',text,re.M)==[top] and
            not re.search(r'^\s*ORIGIN\s+',text,re.M), 'Unsupported macro origin or hierarchy.')
    ending='END '+top+'\nEND LIBRARY'
    require(text.count(ending)==1 and text.count('\n  OBS\n')==1,
            'Expected the captured OpenROAD abstract format.')
    start=text.index('\n  OBS\n')+len('\n  OBS\n'); end=text.index('\n  END\n',start)
    layout=k.Layout();layout.read(str(gds));cell=layout.top_cell()
    x0,y0,_,_=inventory['die_nm']; lines=[]; count=0
    for name,layer in METALS.items():
        index=layout.find_layer(layer,22);require(index is not None,'A required metal-fill mask is missing.')
        polygons=list(k.Region(cell.begin_shapes_rec(index)).merged().each())
        require(polygons and all(p.is_box() for p in polygons),'Expected rectangular metal fill.')
        lines.append('    LAYER '+name+' ;')
        for p in polygons:
            b=p.bbox(); coordinates=(b.left-x0,b.bottom-y0,b.right-x0,b.top-y0)
            lines.append('     RECT '+' '.join(f'{v/1000:.3f}' for v in coordinates)+' ;')
        count+=len(polygons)
    changed=text[:end]+'\n'+'\n'.join(lines)+text[end:]
    require(not Path(target).exists(),'Preserve the existing filled abstract.')
    atomic_write(target,changed)
    require(Path(target).read_text()==changed,'Filled abstract changed during serialization.')
    return count


def execute(r, settings):
    if not settings.get('ihp_fill'):
        return
    implementation_options(r,settings)
    source={key:dict(r.artifacts[key]) for key in ('gds','spef','checkpoint','def','netlist','lef')}
    folder=r.root/'ihp-fill';folder.mkdir()
    inventory=folder/'inventory.json'
    shutil.copyfile(Path(__file__).with_name('digital_ihp_inventory.py'),folder/'inventory.py')
    r.command([r.tools['openroad'],'-no_init','-exit','-python',str(folder/'inventory.py'),
               str(r.root/source['checkpoint']['path']),str(inventory)],
              'Reading signal clearances for IHP fill',cwd=folder,fraction=.96)
    policy=r.platform['ihp_fill'];resources=r.root/'platform'/policy['directory']
    request=dict(resources=str(resources),preparation_sha256=policy['preparation_sha256'],
                 gds=str(r.root/source['gds']['path']),gds_sha256=source['gds']['sha256'],
                 inventory=str(inventory),inventory_sha256=file_digest(inventory),
                 pattern=settings.get('ihp_fill_pattern','balanced'),output=str(folder/'verified'),
                 magic=r.tools['magic'],klayout=r.tools['klayout'])
    atomic_write(folder/'request.json',json.dumps(request,indent=2)+'\n')
    bootstrap='import sys\nsys.path.insert(0,'+repr(str(Path(__file__).resolve().parents[1]))+')\n'
    bootstrap+='import json\nfrom pathlib import Path\nfrom icstudio.digital_ihp_fill_worker import execute\nexecute(json.loads(Path(sys.argv[1]).read_text()))\n'
    atomic_write(folder/'run.py',bootstrap)
    r.command([sys.executable,str(folder/'run.py'),str(folder/'request.json')],
              'Generating and verifying IHP block fill',cwd=folder,fraction=.97)
    record=json.loads((folder/'verified/record.json').read_text())
    require(record['status']=='generated_and_verified' and record['source_gds_sha256']==source['gds']['sha256'] and
            record['checkpoint_sha256']==source['checkpoint']['sha256'], 'IHP fill evidence is incomplete or stale.')
    count=abstract(r.root/source['lef']['path'],folder/'filled.lef',folder/'verified/filled.gds',json.loads(inventory.read_text()))
    for key,item in source.items():
        require(file_digest(r.root/item['path'])==item['sha256'],'An implementation input changed during IHP fill.')
        r.artifacts['ihp_fill_original_'+key]=item
    for index,path in enumerate(sorted(p for p in folder.rglob('*') if p.is_file())):
        r.add_artifact('ihp_fill_file_'+str(index),path,allow_empty=True)
    r.add_artifact('gds',folder/'verified/filled.gds');r.add_artifact('lef',folder/'filled.lef')
    evidence={key:value for key,value in r.artifacts.items() if key.startswith('ihp_fill_')}
    r.save_json('ihp_fill',dict(schema=1,recipe=RECIPE,status='generated_and_verified',scope=record['scope'],
        platform_fingerprint=r.platform['fingerprint'],settings=settings,source=source,
        gds=r.artifacts['gds'],spef=r.artifacts['spef'],lef=r.artifacts['lef'],
        record_sha256=file_digest(folder/'verified/record.json'),metal_fill_obstructions=count,
        model_artifacts=evidence,capacitance=record['capacitance'],
        timing_handoff='Original SPEF and Liberty retained only after unchanged circuit masks, exact native circuit capacitance and physical-device/resistance checks. No pin capacitance is added twice.',
        acceptance='Required layout, connectivity, equivalence and timing checks remain bound to this final result.'),'ihp_fill.json')


def verify(upstream, config):
    artifacts=upstream.get('artifacts',{})
    requested=config.get('physical',{}).get('ihp_fill')
    if not requested and 'ihp_fill' not in artifacts:
        return
    require(requested and 'ihp_fill' in artifacts,'Run physical finish with IHP fill before extracted timing or export.')
    report=json.loads((Path(upstream['root'])/artifacts['ihp_fill']['path']).read_text())
    from .digital_physical import DEFAULTS
    expected={**DEFAULTS,**config.get('physical',{})}
    require({k:v for k,v in report.get('settings',{}).items() if k!='threads'}==
            {k:v for k,v in expected.items() if k!='threads'},'IHP fill settings changed after implementation.')
    require(report.get('schema')==1 and report.get('recipe')==RECIPE and
            report.get('status')=='generated_and_verified' and
            report.get('platform_fingerprint')==config.get('platform',{}).get('fingerprint') and
            all(report.get(k)==artifacts.get(k) for k in ('gds','spef','lef')) and
            report.get('source',{}).get('netlist')==artifacts.get('netlist') and
            report.get('source',{}).get('spef')==artifacts.get('spef') and
            report.get('capacitance',{}).get('status')=='cell-capacitance-subnetwork-identical',
            'IHP fill evidence does not match the final geometry, circuit and nominal parasitics.')
    require(report.get('model_artifacts') and all(artifacts.get(k)==v for k,v in report['model_artifacts'].items()),
            'IHP fill verification artifacts are incomplete.')
