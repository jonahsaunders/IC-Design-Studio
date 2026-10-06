"""Explicit file locks for digital technology libraries and ORFS installations."""
from __future__ import annotations

import json
import gzip
import re
import shutil
from pathlib import Path

from .digital import relative_path
from .model import atomic_write, clone, file_digest, digest

MAX_PLATFORM_BYTES = 1024 * 1024 * 1024
MAX_LIBERTY_BYTES = 128 * 1024 * 1024
BUNDLED_PLATFORMS = ('sky130hd', 'gf180', 'ihp-sg13g2')
PLATFORM_LABELS = {'sky130hd':'SKY130 HD', 'gf180':'GF180 MCU 5 V', 'ihp-sg13g2':'IHP SG13G2'}

# Explicit library and physical options for the pinned ORFS platform layouts.
# Importing a profile does not assert arbitrary-design or foundry qualification.
ORFS_PROFILES = {
    'sky130hd': {
        'corners': {'typical': ['lib/sky130_fd_sc_hd__tt_025C_1v80.lib']},
        'tie_cells': {'high': ['sky130_fd_sc_hd__conb_1', 'HI'], 'low': ['sky130_fd_sc_hd__conb_1', 'LO']},
    },
    'nangate45': {'corners': {'typical': ['lib/NangateOpenCellLibrary_typical.lib']}},
    'gf180': {
        'corners': {
            'typical': ['lib/gf180mcu_fd_sc_mcu9t5v0__tt_025C_5v00.lib.gz'],
            'slow': ['lib/gf180mcu_fd_sc_mcu9t5v0__ss_125C_4v50.lib.gz'],
            'fast': ['lib/gf180mcu_fd_sc_mcu9t5v0__ff_n40C_5v50.lib.gz'],
        },
        'tie_cells': {'high': ['gf180mcu_fd_sc_mcu9t5v0__tieh', 'Z'], 'low': ['gf180mcu_fd_sc_mcu9t5v0__tiel', 'ZN']},
        'orfs': {
            # The pinned TC script omits cut-layer resistance; the captured LEF
            # has explicit resistance on these single-cut reference vias.
            'rc_file': 'setRC.tcl',
            'rc_vias': {'typical': {'Via1':'Via1_HH','Via2':'Via2_HH','Via3':'Via3_HH','Via4':'Via4_HH'}},
            'variables': {'TRACK_OPTION': '9t', 'METAL_OPTION': '5LM_1TM', 'KVALUE': '9', 'POWER_OPTION': '5v0'},
            'corners': {
                'typical': {'CORNER': 'TC', 'PWR_NETS_VOLTAGES': 'VDD 5.0'},
                'slow': {'CORNER': 'WC', 'PWR_NETS_VOLTAGES': 'VDD 4.5'},
                'fast': {'CORNER': 'BC', 'PWR_NETS_VOLTAGES': 'VDD 5.5'},
            },
        },
    },
    'ihp-sg13g2': {
        'corners': {
            'typical': ['lib/sg13g2_stdcell_typ_1p20V_25C.lib'],
            'slow': ['lib/sg13g2_stdcell_slow_1p08V_125C.lib'],
            'fast': ['lib/sg13g2_stdcell_fast_1p32V_m40C.lib'],
        },
        'tie_cells': {'high': ['sg13g2_tiehi', 'L_HI'], 'low': ['sg13g2_tielo', 'L_LO']},
        'orfs': {'variables': {}, 'corners': {
            'typical': {'PWR_NETS_VOLTAGES': 'VDD 1.2'},
            'slow': {'PWR_NETS_VOLTAGES': 'VDD 1.08'},
            'fast': {'PWR_NETS_VOLTAGES': 'VDD 1.32'},
        }},
    },
}
ORFS_VARIABLES = {'TRACK_OPTION', 'METAL_OPTION', 'KVALUE', 'POWER_OPTION', 'CORNER', 'PWR_NETS_VOLTAGES'}


def validate_options(platform):
    ties=platform.get('tie_cells',{})
    if not isinstance(ties,dict) or ties and set(ties)!={'high','low'}:
        raise ValueError('Specify both high and low tie cells.')
    for pair in ties.values():
        if not isinstance(pair,list) or len(pair)!=2 or any(not isinstance(s,str) or not re.fullmatch(r'[A-Za-z_][A-Za-z0-9_]*',s) for s in pair):
            raise ValueError('A tie cell needs a cell and output-pin identifier.')
    options=platform.get('orfs',{})
    if not isinstance(options,dict) or set(options)-{'variables','corners','rc_file','rc_vias'}:
        raise ValueError('Invalid ORFS platform options.')
    vias=options.get('rc_vias',{})
    if not isinstance(vias,dict) or set(vias)-set(platform.get('corners',{})):
        raise ValueError('Via-resistance references must use captured corners.')
    for references in vias.values():
        if not isinstance(references,dict) or not references or any(
            not isinstance(s,str) or not re.fullmatch(r'[A-Za-z_][A-Za-z0-9_]*',s)
            for pair in references.items() for s in pair):
            raise ValueError('Via resistance requires cut-layer and reference-via identifiers.')
    if vias or options.get('rc_file'):
        name=relative_path(options.get('rc_file',''))
        prefix=platform.get('directory','.')
        name=name if prefix=='.' else prefix+'/'+name
        if name not in {r['path'] for r in platform.get('files',[])}:
            raise ValueError('The RC script must be a captured platform file.')
    by_corner=options.get('corners',{})
    if not isinstance(by_corner,dict) or by_corner and set(by_corner)!=set(platform.get('corners',{})):
        raise ValueError('ORFS corner options must match every captured Liberty corner.')
    for values in [options.get('variables',{}),*by_corner.values()]:
        if not isinstance(values,dict) or set(values)-ORFS_VARIABLES:
            raise ValueError('Unsupported ORFS platform variable.')
        if any(not isinstance(value,str) or not re.fullmatch(r'[A-Za-z0-9_. -]{1,120}',value) or value!=value.strip() for value in values.values()):
            raise ValueError('ORFS platform values must be literal identifiers or numbers.')


def implementation_options(platform):
    validate_options(platform)
    options=platform.get('orfs',{})
    return {**options.get('variables',{}),**options.get('corners',{}).get(platform['corner'],{})}


def bind(config, platform):
    """Explicit imports select the new platform's complete corner set."""
    validate(platform)
    result=clone(config);result['platform']=clone(platform)
    result['timing_corners']=list(platform['corners'])
    return result


def inventory(root, paths):
    root = Path(root).resolve(); records = []; total = 0
    for name in sorted(set(paths)):
        relative_path(name); path = (root/name).resolve()
        if not path.is_relative_to(root) or not path.is_file():raise ValueError('Platform file is missing or escapes its root: '+name)
        total += path.stat().st_size
        if total>MAX_PLATFORM_BYTES or len(records)>=10000:raise ValueError('Platform capture exceeds 1 GiB or 10,000 files.')
        records.append({'path':name,'sha256':file_digest(path),'bytes':path.stat().st_size})
    return records


def validate(platform):
    if not isinstance(platform,dict) or platform.get('version') != 1:raise ValueError('Choose a version-1 digital platform manifest.')
    if not re.fullmatch(r'[A-Za-z0-9_-]{1,80}',platform.get('name','')):raise ValueError('Invalid platform name.')
    if not isinstance(platform.get('revision'),str) or not platform['revision'].strip():raise ValueError('A digital platform needs a revision label.')
    if not isinstance(platform.get('root'),str) or not platform['root']:raise ValueError('A digital platform needs its installation root.')
    relative_path(platform.get('directory','.'),directory=True)
    records = platform.get('files',[])
    if not isinstance(records,list) or not 1<=len(records)<=10000:raise ValueError('Digital platform has no captured files.')
    names=set();exact_names=set()
    for item in records:
        if not isinstance(item,dict) or type(item.get('bytes')) is not int or item['bytes']<0:raise ValueError('Invalid platform file lock.')
        name=relative_path(item['path'])
        if name.casefold() in names or not re.fullmatch('[0-9a-f]{64}',item.get('sha256','')):raise ValueError('Invalid platform file lock.')
        names.add(name.casefold())
        exact_names.add(name)
    if sum(item['bytes'] for item in records)>MAX_PLATFORM_BYTES:raise ValueError('Platform capture exceeds 1 GiB.')
    corners=platform.get('corners',{})
    if not isinstance(corners,dict) or not 1<=len(corners)<=20:raise ValueError('Define 1–20 named Liberty corners.')
    for name, files in corners.items():
        if not re.fullmatch('[A-Za-z0-9_-]{1,80}',name) or not isinstance(files,list) or not files:raise ValueError('Invalid Liberty corner.')
        if any(not isinstance(f,str) or f not in exact_names for f in files):raise ValueError('A Liberty corner references an uncaptured file; use its exact captured spelling.')
    if platform.get('corner') not in corners:raise ValueError('Choose a captured Liberty corner.')
    validate_options(platform)
    if platform.get('fingerprint') != digest(records):raise ValueError('Digital platform manifest checksum changed. Import the platform again.')
    return platform


def verify(platform):
    validate(platform); root=Path(platform['root']).resolve()
    for record in platform['files']:
        path=(root/record['path']).resolve()
        if not path.is_relative_to(root) or not path.is_file() or file_digest(path)!=record['sha256']:
            raise ValueError('The locked digital platform changed: '+record['path']+'. Import the intended revision explicitly.')
    return platform['fingerprint']


def read_manifest(path):
    path=Path(path).resolve(); data=json.loads(path.read_text())
    paths=data.pop('files',[])
    if not all(isinstance(p,str) for p in paths):raise ValueError('The import manifest lists relative platform filenames.')
    data['root']=str(path.parent);data['files']=inventory(path.parent,paths)
    data['fingerprint']=digest(data['files']);return validate(data)


def from_orfs(root, name='sky130hd'):
    """Capture the complete selected platform, not Studio's analog model subset."""
    import subprocess
    root=Path(root).resolve()
    if root.name == 'flow':root=root.parent
    folder=root/'flow/platforms'/name
    if name not in ORFS_PROFILES:raise ValueError('Choose '+', '.join(ORFS_PROFILES)+', or use a platform manifest.')
    if not folder.is_dir():raise ValueError('Choose an OpenROAD Flow Scripts checkout with the complete platform.')
    revision=subprocess.run(['git','-C',str(root),'rev-parse','HEAD'],capture_output=True,text=True,check=True).stdout.strip()
    tracked=subprocess.run(['git','-C',str(root),'ls-files','--stage','-z','--','flow/platforms/'+name],
                           capture_output=True,text=True,check=True).stdout
    for entry in tracked.split('\0'):
        if entry.startswith('120000 '):
            path=root/entry.split('\t',1)[1]
            if not path.is_symlink():
                raise ValueError('ORFS has an unresolved symbolic link: '+str(path.relative_to(root))+
                                 '. Use a checkout with symbolic links enabled or the included digital runtime.')
            if not path.is_file():
                raise ValueError('ORFS has a missing symbolic-link target: '+str(path.relative_to(root))+
                                 '. Include the linked sibling platform when checking out ORFS.')
    paths=[p.relative_to(folder.parent).as_posix() for p in folder.rglob('*') if p.is_file()]
    files=inventory(folder.parent,paths)
    profile=clone(ORFS_PROFILES[name])
    corners={corner:[name+'/'+path for path in paths] for corner,paths in profile.pop('corners').items()}
    data={'version':1,'name':name,'revision':'ORFS '+revision,'root':str(folder.parent),'directory':name,'corner':'typical',
          'corners':corners,'files':files,'fingerprint':digest(files),**profile}
    return validate(data)


def liberty_files(platform, staged_root, destination, corner=None):
    """Materialize captured gzip libraries for engines that require plain Liberty."""
    validate(platform)
    corner=corner or platform['corner'];root=Path(staged_root).resolve()
    if corner not in platform['corners']:raise ValueError('Choose a captured Liberty corner.')
    locks={item['path']:item for item in platform['files']};result=[]
    for name in platform['corners'][corner]:
        path=(root/name).resolve()
        if not path.is_relative_to(root) or not path.is_file() or file_digest(path)!=locks[name]['sha256']:
            raise ValueError('A captured Liberty library is missing or changed: '+name)
        if name.endswith('.gz'):
            try:
                with gzip.open(path,'rb') as stream:content=stream.read(MAX_LIBERTY_BYTES+1)
            except (OSError,EOFError) as exc:raise ValueError('Invalid compressed Liberty library: '+name) from exc
            if not content or len(content)>MAX_LIBERTY_BYTES:
                raise ValueError('A decompressed Liberty library must be nonempty and at most 128 MiB.')
            path=Path(destination)/ (locks[name]['sha256']+'.lib')
            atomic_write(path,content)
        elif path.stat().st_size==0 or path.stat().st_size>MAX_LIBERTY_BYTES:
            raise ValueError('A Liberty library must be nonempty and at most 128 MiB.')
        result.append(path)
    return result


def stage(platform, destination):
    verify(platform); destination=Path(destination);destination.mkdir(parents=True,exist_ok=True)
    for record in platform['files']:
        target=destination/record['path'];target.parent.mkdir(parents=True,exist_ok=True)
        shutil.copy2(Path(platform['root'])/record['path'],target)
        if file_digest(target)!=record['sha256']:raise ValueError('Platform changed during capture: '+record['path'])


def pin_flow(path):
    root=Path(path).resolve();root=root/'flow' if (root/'flow/Makefile').is_file() else root
    if not (root/'Makefile').is_file():raise ValueError('Select the OpenROAD Flow Scripts checkout or its flow directory.')
    names=['Makefile']
    for folder in ('scripts','util'):
        names += [p.relative_to(root).as_posix() for p in (root/folder).rglob('*') if p.is_file() and '__pycache__' not in p.parts]
    for name in names:
        with (root/name).open('rb') as stream:first=stream.readline(4096)
        if first.startswith(b'#!') and first.endswith(b'\r\n'):
            raise ValueError('ORFS executable scripts require LF line endings: '+name+
                             '. Use a checkout with core.autocrlf=false or the included digital runtime.')
    files=inventory(root,names)
    return {'root':str(root),'files':files,'fingerprint':digest(files)}


def verify_flow(flow):
    if digest(flow['files']) != flow['fingerprint']:raise ValueError('Invalid ORFS source lock.')
    root=Path(flow['root']).resolve()
    for record in flow['files']:
        path=(root/relative_path(record['path'])).resolve()
        if not path.is_relative_to(root) or not path.is_file() or file_digest(path)!=record['sha256']:
            raise ValueError('OpenROAD Flow Scripts changed. Prepare a new run with the intended checkout.')
    return flow['fingerprint']
