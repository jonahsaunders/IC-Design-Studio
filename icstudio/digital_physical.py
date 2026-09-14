"""Captured ORFS checkpoints and a bounded native DEF placement/route preview."""
from __future__ import annotations

import json
import math
import re
import shutil
from pathlib import Path

from .model import atomic_write, file_digest

STAGES = ('floorplan','place','cts','route','finish')
CHECKPOINTS = {'floorplan':'2_floorplan','place':'3_place','cts':'4_cts','route':'5_route','finish':'6_final'}
DEFAULTS = {'die_area':[0,0,100,100],'core_area':[10,10,90,90],'place_density':0.6,'threads':2}
OPTIONS = {'min_routing_layer','max_routing_layer','macro_halo_um','pin_constraints','macro_placements',
           'io_constraints_tcl','macro_placement_tcl','pdn_tcl'}


def validate_settings(settings):
    if not isinstance(settings,dict) or set(settings)-set(DEFAULTS)-OPTIONS:raise ValueError('Unknown physical implementation setting.')
    for name in ('die_area','core_area'):
        rect=settings.get(name,DEFAULTS[name])
        if not isinstance(rect,list) or len(rect)!=4 or any(type(x) not in (int,float) or not math.isfinite(x) for x in rect) or rect[0]>=rect[2] or rect[1]>=rect[3]:
            raise ValueError('Enter a valid '+name+' rectangle in micrometres.')
    die=settings.get('die_area',DEFAULTS['die_area']);core=settings.get('core_area',DEFAULTS['core_area'])
    if not (die[0]<=core[0]<core[2]<=die[2] and die[1]<=core[1]<core[3]<=die[3]):raise ValueError('The core must lie within the die.')
    density=settings.get('place_density',.6)
    if type(density) not in (int,float) or not .05<=density<=.95:raise ValueError('Placement density must be between 0.05 and 0.95.')
    threads=settings.get('threads',2)
    if type(threads) is not int or not 1<=threads<=64:raise ValueError('Use 1–64 implementation threads.')
    for key in ('min_routing_layer','max_routing_layer'):
        if settings.get(key) and not re.fullmatch(r'[A-Za-z0-9_]+',settings[key]):raise ValueError('Use a routing-layer identifier.')
    halo=settings.get('macro_halo_um',0)
    if type(halo) not in (int,float) or not math.isfinite(halo) or halo<0:raise ValueError('Macro halo must be nonnegative micrometres.')
    for key in ('io_constraints_tcl','macro_placement_tcl','pdn_tcl'):
        if not isinstance(settings.get(key,''),str) or len(settings.get(key,''))>1024*1024:raise ValueError('Physical Tcl must be at most 1 MiB.')
    pins=settings.get('pin_constraints',[])
    if not isinstance(pins,list) or len(pins)>256:raise ValueError('Use at most 256 pin groups.')
    for pin in pins:
        if not isinstance(pin,dict) or not isinstance(pin.get('pins'),str) or not pin['pins'].strip() or pin.get('edge') not in ('top','bottom','left','right'):
            raise ValueError('Pin groups need a pattern and top/bottom/left/right edge.')
    macros=settings.get('macro_placements',[])
    if not isinstance(macros,list) or len(macros)>1000:raise ValueError('Use at most 1,000 macro placements.')
    for macro in macros:
        if not isinstance(macro,dict) or not isinstance(macro.get('name'),str) or not macro['name'].strip():raise ValueError('Each macro needs its instance name.')
        if macro.get('orientation','R0') not in ('R0','R90','R180','R270','MX','MY','MXR90','MYR90'):raise ValueError('Invalid macro orientation.')
        if any(type(macro.get(k)) not in (int,float) or not math.isfinite(macro[k]) for k in ('x','y')):raise ValueError('Macro positions must be finite micrometres.')


def write_options(r, settings):
    """Translate reviewed physical intent into captured ORFS inputs."""
    from .digital_implementation import tcl_word
    lines=[]
    for key,var in (('min_routing_layer','MIN_ROUTING_LAYER'),('max_routing_layer','MAX_ROUTING_LAYER')):
        if settings.get(key):lines.append('export '+var+' = '+settings[key])
    if settings.get('macro_halo_um'):
        halo=str(settings['macro_halo_um']);lines += ['export MACRO_PLACE_HALO = '+halo+' '+halo, 'export MACRO_BLOCKAGE_HALO = '+halo]
    pins=['set_io_pin_constraint -pin_names '+tcl_word(p['pins'])+' -region '+tcl_word(p['edge']+':*') for p in settings.get('pin_constraints',[])]
    macros=['place_macro -macro_name '+tcl_word(m['name'])+' -location '+tcl_word(str(m['x'])+' '+str(m['y']))+' -orientation '+m.get('orientation','R0') for m in settings.get('macro_placements',[])]
    scripts={'IO_CONSTRAINTS':'\n'.join(pins)+'\n'+settings.get('io_constraints_tcl',''),
             'MACRO_PLACEMENT_TCL':'\n'.join(macros)+'\n'+settings.get('macro_placement_tcl',''),
             'PDN_TCL':settings.get('pdn_tcl','')}
    for variable,text in scripts.items():
        if text.strip():
            path=r.root/(variable.lower()+'.tcl');atomic_write(path,text+'\n');r.add_artifact(variable.lower(),path)
            lines.append('export '+variable+' = '+str(path))
    return lines


def preview(def_file, lefs):
    path=Path(def_file)
    if path.stat().st_size>128*1024*1024:raise ValueError('DEF exceeds the 128 MiB native preview limit.')
    sizes={}
    for lef in lefs:
        text=Path(lef).read_text()
        for match in re.finditer(r'(?m)^\s*MACRO\s+(\S+)(.*?)(?=^\s*END\s+\1\s*$)',text,re.S):
            size=re.search(r'\bSIZE\s+([\d.]+)\s+BY\s+([\d.]+)',match[2])
            if size:sizes[match[1]]=[float(size[1]),float(size[2])]
    text=path.read_text();unit=re.search(r'UNITS\s+DISTANCE\s+MICRONS\s+(\d+)',text)
    if not unit:raise ValueError('DEF preview requires declared distance units.')
    scale=int(unit[1]);die=re.search(r'DIEAREA\s*\(\s*(-?\d+)\s+(-?\d+)\s*\)\s*\(\s*(-?\d+)\s+(-?\d+)\s*\)',text)
    if not die:raise ValueError('DEF preview currently requires a rectangular die.')
    components=[];block=re.search(r'(?ms)^COMPONENTS\b(.*?)^END COMPONENTS',text)
    if block:
        for record in block[1].split(';'):
            match=re.search(r'-\s+(\S+)\s+(\S+).*?\+\s+(?:PLACED|FIXED|COVER)\s*\(\s*(-?\d+)\s+(-?\d+)\s*\)\s+(\S+)',record,re.S)
            if match:
                name,master,x,y,orientation=match.groups();width,height=sizes.get(master,[1,1])
                if orientation in ('E','W','FE','FW'):width,height=height,width
                components.append({'name':name,'master':master,'x':int(x)/scale,'y':int(y)/scale,'width':width,'height':height,'orientation':orientation})
                if len(components)>100000:raise ValueError('Preview supports at most 100,000 placed instances.')
    nets=[];segments=[];block=re.search(r'(?ms)^NETS\b(.*?)^END NETS',text)
    if block:
        for record in block[1].split(';'):
            match=re.search(r'-\s+(\S+)',record)
            if not match:continue
            name=match[1];connections=re.findall(r'\(\s*(\S+)\s+(\S+)\s*\)',record.split('+')[0])
            nets.append({'name':name,'connections':connections})
            for route in re.finditer(r'(?:\+\s*ROUTED|\bNEW)\s+(\S+)(.*?)(?=\bNEW|\+|$)',record,re.S):
                last=None
                for point in re.finditer(r'\(\s*(-?\d+|\*)\s+(-?\d+|\*)\s*\)',route[2]):
                    if '*' in point.groups() and last is None:continue
                    current=[last[i] if v=='*' else int(v)/scale for i,v in enumerate(point.groups())]
                    if last and current!=last:segments.append({'net':name,'layer':route[1],'points':[last,current]})
                    last=current
                    if len(segments)>500000:raise ValueError('Preview supports at most 500,000 routed segments.')
    pins=[];block=re.search(r'(?ms)^PINS\b(.*?)^END PINS',text)
    if block:
        for record in block[1].split(';'):
            name=re.search(r'-\s+(\S+)',record);use=re.search(r'\+ USE\s+(\S+)',record)
            placement=re.search(r'\+ (?:PLACED|FIXED)\s*\(\s*(-?\d+)\s+(-?\d+)\s*\)\s+(\S+)',record)
            rect=re.search(r'\+ LAYER\s+(\S+)\s*\(\s*(-?\d+)\s+(-?\d+)\s*\)\s*\(\s*(-?\d+)\s+(-?\d+)\s*\)',record)
            if name and placement and rect:
                x=(int(rect[2])+int(rect[4]))/2;y=(int(rect[3])+int(rect[5]))/2
                rotations={'N':(x,y),'S':(-x,-y),'E':(y,-x),'W':(-y,x),'FN':(-x,y),'FS':(x,-y),'FE':(y,x),'FW':(-y,-x)}
                if placement[3] not in rotations:raise ValueError('Unsupported DEF terminal orientation.')
                x,y=rotations[placement[3]]
                pins.append({'name':name[1],'use':use[1] if use else 'SIGNAL','layer':rect[1],
                    'point':[(int(placement[1])+x)/scale,(int(placement[2])+y)/scale]})
    return {'version':1,'units':'um','die':[int(die[i])/scale for i in range(1,5)],'components':components,'nets':nets,'segments':segments,'pins':pins,
            'scope':'DEF placement and signal-route preview. Cell outlines and centerlines are not a DRC view; inspect final GDS in the layout editor.'}


def execute(r):
    from .digital_implementation import mapped,verify_upstream,tcl_word,quote
    from .digital_platform import verify_flow
    from .digital import source_hash
    stage=r.settings['stage'];settings={**DEFAULTS,**r.config.get('physical',{})};validate_settings(settings)
    for path in [str(r.root),*r.tools.values()]:
        if any(c.isspace() for c in path):raise ValueError('ORFS requires run and tool paths without spaces. Choose a space-free jobs folder.')
    data=mapped(r);flow=r.settings['flow'];verify_flow(flow)
    flow_root=r.root/'flow';flow_root.mkdir()
    for record in flow['files']:
        target=flow_root/record['path'];target.parent.mkdir(parents=True,exist_ok=True)
        shutil.copy2(Path(flow['root'])/record['path'],target)
        if file_digest(target)!=record['sha256']:raise ValueError('ORFS changed during capture.')
    work=r.root/'physical';result_dir=work/'results'/r.platform['name']/r.config['top']/'base'
    previous=r.settings.get('upstream',{});resume=False
    expected_source=r.settings.get('host_source_hash',source_hash(r.config))
    old = verify_upstream(previous) if previous else None
    from .digital_identity import stage_key
    compatible = bool(old and (old['digital_result'].get('input_key') == stage_key(r.config, previous['stage'])
                              if old['digital_result'].get('input_key') else previous['source_hash'] == expected_source))
    if previous.get('stage') in STAGES and STAGES.index(previous['stage'])<STAGES.index(stage) and compatible:
        if old['digital_result']['physical']['flow_fingerprint']!=flow['fingerprint']:
            raise ValueError('The ORFS version changed. Start a new floorplan before resuming physical implementation.')
        old_tools=old['digital_result']['environment']['executables']
        current_tools=r.settings.get('host_environment',r.job['environment'])['executables']
        if (old_tools.get('openroad') or old_tools.get('sha256'))!=(current_tools.get('openroad') or current_tools.get('sha256')):
            raise ValueError('OpenROAD changed. Start a new floorplan before resuming physical implementation.')
        for item in previous['artifacts'].values():
            if item['path'].startswith('physical/'):
                target=r.root/item['path'];target.parent.mkdir(parents=True,exist_ok=True)
                shutil.copy2(Path(previous['root'])/item['path'],target)
        resume=True
    for folder in ('results','reports','logs','objects'):(work/folder/r.platform['name']/r.config['top']/'base').mkdir(parents=True,exist_ok=True)
    seed=result_dir/'1_2_yosys.v'
    if not resume:shutil.copy2(r.root/'netlist.v',seed)
    seed_sdc=result_dir/'1_2_yosys.sdc'
    if not resume:shutil.copy2(r.constraints(),seed_sdc)
    seed_hash=file_digest(seed)
    lines=['export DESIGN_NAME = '+r.config['top'],'export PLATFORM = '+r.platform['name'],
           'export VERILOG_FILES = '+' '.join(str(r.sources/f['path']) for f in r.config['files'] if f['role']=='rtl'),
           'export SDC_FILE = '+str(r.constraints()),
           'export PLATFORM_DIR = '+str(r.root/'platform'/r.platform.get('directory','.')),
           'export LIB_FILES = '+' '.join(str(p) for p in r.libraries()),
           'export DIE_AREA = '+' '.join(str(v) for v in settings['die_area']),
           'export CORE_AREA = '+' '.join(str(v) for v in settings['core_area']),
           'export PLACE_DENSITY = '+str(settings['place_density']),
           'export NUM_CORES = '+str(settings['threads']), 'export SKIP_REPORT_METRICS = 0']
    lines += write_options(r,settings)
    atomic_write(r.root/'config.mk','\n'.join(lines)+'\n')
    command=[r.tools['make'],'-f',str(flow_root/'Makefile'),'DESIGN_CONFIG='+str(r.root/'config.mk'),
             'WORK_HOME='+str(work),'OPENROAD_EXE='+r.tools['openroad'],'YOSYS_EXE='+r.tools['yosys'],
             'NUM_CORES='+str(settings['threads']),'-o',str(seed),'-o',str(seed_sdc)]
    if 'klayout' in r.tools:command.append('KLAYOUT_CMD='+r.tools['klayout'])
    if resume:
        name=CHECKPOINTS[previous['stage']]
        command+=['-o',str(result_dir/(name+'.odb')),'-o',str(result_dir/(name+'.sdc'))]
    # GNU make's explicit assume-old input prevents ORFS from silently synthesizing a different netlist.
    r.command(command+[stage],'Running ORFS '+stage,cwd=flow_root,fraction=.45)
    if file_digest(seed)!=seed_hash:raise ValueError('ORFS replaced the captured mapped input. The physical run cannot be accepted.')
    checkpoint=result_dir/(CHECKPOINTS[stage]+'.odb')
    if not checkpoint.is_file():raise ValueError('ORFS did not produce the expected '+stage+' checkpoint.')
    script='\n'.join('read_liberty '+tcl_word(p) for p in r.libraries())+'\nread_db '+tcl_word(checkpoint)+'\n'
    script+='''set physical_only {}
foreach library [[ord::get_db] getLibs] {
  foreach master [$library getMasters] {
    if {[$master getType] in {COVER COVER_BUMP RING PAD_SPACER CORE_FEEDTHROUGH CORE_SPACER CORE_ANTENNACELL CORE_WELLTAP} || [$master isEndCap]} {
      lappend physical_only [$master getName]
    }
  }
}
'''
    script+='write_def '+tcl_word(r.root/'snapshot.def')+'\nwrite_verilog -remove_cells $physical_only '+tcl_word(r.root/'physical.v')+'\n'
    from .digital_odb import script as database_script
    script += database_script(r.root/'database.json')
    if stage=='finish':script+='write_abstract_lef '+tcl_word(r.root/'macro.lef')+'\n'
    atomic_write(r.root/'snapshot.tcl','if {[catch {\n'+script+'\n} message]} {puts stderr $message; exit 1}\n')
    r.command([r.tools['openroad'],'-no_init','-exit',str(r.root/'snapshot.tcl')],'Reading the '+stage+' layout checkpoint',fraction=.9)
    r.add_artifact('checkpoint',checkpoint);r.add_artifact('def',r.root/'snapshot.def')
    r.add_artifact('database',r.root/'database.json')
    r.add_artifact('mapped_input',seed)
    shutil.copy2(r.root/'physical.v',r.root/'netlist.v');r.add_artifact('netlist',r.root/'netlist.v')
    lefs=[r.root/'platform'/f['path'] for f in r.platform['files'] if f['path'].endswith('.lef')]
    geometry=preview(r.root/'snapshot.def',lefs)
    from .digital_odb import merge_preview
    geometry=merge_preview(geometry,r.root/'database.json')
    # Record the stream layer mapping beside the DEF; attachment never guesses GDS layer numbers.
    stream_layers={}
    for record in r.platform['files']:
        if record['path'].endswith('.lyt'):
            text=(r.root/'platform'/record['path']).read_text()
            for name,layer,datatype in re.findall(r"'([\w-]+)\.drawing\s*:\s*(\d+)/(\d+)'",text):stream_layers[name]=[int(layer),int(datatype)]
    for pin in geometry['pins']:
        if pin['layer'] in stream_layers:pin['gds_layer']=stream_layers[pin['layer']]
    r.save_json('layout_preview',geometry,'layout_preview.json')
    # Re-index the physical netlist so inserted buffers and renamed cells are represented accurately.
    script='\n'.join('read_liberty -lib -ignore_miss_func '+quote(p) for p in r.libraries())+'\n'
    script+='read_verilog ../netlist.v\nhierarchy -check -top '+r.config['top']+'\nwrite_json ../netlist.json\ntee -o ../statistics.json stat -json\n'
    atomic_write(r.root/'physical_index.ys',script);r.command([r.tools['yosys'],'-s',str(r.root/'physical_index.ys')],'Indexing physical cells',fraction=.95)
    from .digital_reports import netlist_index
    netlist=json.loads((r.root/'netlist.json').read_text());index=netlist_index(netlist,r.config['files'])
    previous_index=json.loads((r.root/'netlist_index.json').read_text())
    locations={(i['module'],i['kind'],i['name']):i['locations'] for i in previous_index}
    for item in index:
        item['locations']=locations.get((item['module'],item['kind'],item['name']),[])
        item['mapping'] = 'retained name' if item['locations'] else 'unmapped physical object'
    r.save_json('netlist_index',index,'netlist_index.json');r.add_artifact('hierarchy',r.root/'netlist.json');r.add_artifact('statistics',r.root/'statistics.json')
    if stage=='finish':
        r.add_artifact('lef',r.root/'macro.lef')
        for key,suffix in (('gds','.gds'),('spef','.spef')):r.add_artifact(key,result_dir/('6_final'+suffix))
    metrics={}
    for path in sorted(work.rglob('*.json')):
        if path.stat().st_size>8*1024*1024:continue
        try:value=json.loads(path.read_text())
        except (ValueError,UnicodeError):continue
        if isinstance(value,dict):metrics[path.relative_to(work).as_posix()]=value
    r.save_json('physical_metrics',metrics,'physical_metrics.json')
    files=[p for p in work.rglob('*') if p.is_file()]
    if len(files)>10000 or sum(p.stat().st_size for p in files)>1024**3:raise ValueError('Physical checkpoint exceeds the 1 GiB / 10,000-file capture limit.')
    from .digital_flow import artifact
    for i,path in enumerate(sorted(files)):r.artifacts['physical_file_'+str(i)]=artifact(r.root,path,allow_empty=True)
    return {**data,'physical':{'stage':stage,'resumed':resume,'upstream':previous.get('root'),
            'flow_fingerprint':flow['fingerprint'],'settings':settings,'scope':'Engine implementation; timing, equivalence and physical rule qualification remain explicit checks.'},
            'statistics':{'cells':len(geometry['components']),'area_um2':sum(c['width']*c['height'] for c in geometry['components'])},
            'summary':'Physical '+stage+' complete · '+str(len(geometry['components']))+' placed cells'}
