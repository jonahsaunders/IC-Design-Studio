"""Mandatory local strict LVS for newly prepared SKY130 HD Finish jobs.

The reference comes from the final implementation database and a captured,
reviewed cell CDL, independently of extraction from the GDS being checked.
"""
import hashlib
import json
from pathlib import Path
import shutil
import tempfile

from .model import atomic_write, file_digest

ASSETS = Path(__file__).parent/'assets/verification/sky130/lvs'
ASSET_HASHES = {
    'BSD-2-Clause.txt': '879a976a181ce1e98b90b0c674b4ef55d72b7f90410b7d558f29c1e2d119e485',
    'original.lylvs': 'bcc7b27c6f118d9dbfa5db9fad01656cab2255673d18c50fe5002de6c1e41c61',
    'extraction-source.json': 'c6f615449e189a87a4a2014f2dd669e61cfc23380e90c4fc15f0be5e4aa0a5b5',
    'LICENSE': 'cfc7749b96f63bd31c3c42b5c471bf756814053e847c10f3eb003417bc523d30',
    'source-lock.json': '4dedcda67f6b354592277de70753c0d47de45f41ab58d5129520ae6952fd7e3c',
    'sky130_cdl_reader.rb': '9a137e976c29c03726a2f53d2da959f99b33050aa351b7579c53ec238147c0b8',
    'sky130_fd_sc_hd__diode_2.gds': '7198f35a0a4bde6ba7155242c567b21644b04696c39734b604490c09e6709c90',
    'sky130_fd_sc_hd__diode_2.spice': '67b980af74314791f0ea796118c740730958e5cb7083d58acab20c17781bee45',
}
POLICY = dict(recipe='sky130-hd-strict-device-port-lvs-v1',
    masters_sha256s=['ae02cdc40c81943bbc3f4a16a6760e01afd12764a94e7836b7e168edf40ae29c',
                    '35bdf5f2cd1c5d841dcc3d0fe4c34b3f0e8c57a3e25282aa1d716ad7cf2a1aa6'],
    deck_sha256='1afade11dd24ea4e64d1ffba54fc17a8f110286712ab942928d2f5e021bb3caf',
    assets=ASSET_HASHES)
SCOPE = ('Local final-GDS device, body and boundary-port connectivity against an independent final-OpenDB '
    'and reviewed HD CDL reference. Four-terminal 1.8 V NMOS/PMOS and the independently referenced '
    'diode_2 antenna cell are compared, including dimensions. Port labels are encoded on a '
    'mask-identical copy; pin annotations are not conductors. No blanket supply ties, port '
    'equivalences or device blackboxes. This does not establish complete device-family, density, '
    'parasitic, electrical, complete-chip or foundry qualification.')
FILES = ('masters.cdl', 'upstream.lylvs', 'library.gds', *ASSET_HASHES, 'capture.py', 'reference_engine.py',
    'capture-request.json', 'raw-reference.cdl', 'database.json', 'reference.cdl', 'aliases.json',
    'conversion.json', 'library-binding.json', 'labelled.gds', 'label-audit.json', 'strict.lvs',
    'request.json', 'native.log', 'report.lvsdb', 'extracted.cir', 'audit.json')


def require(condition, message):
    if not condition: raise ValueError('SKY130 strict LVS: '+message)


def resources():
    for name, digest in ASSET_HASHES.items():
        require((ASSETS/name).is_file() and file_digest(ASSETS/name) == digest, 'missing or changed resource: '+name)
    return ASSETS


def normalized_digest(content):
    return hashlib.sha256(content.replace(b'\r\n', b'\n')).hexdigest()


def platform_sources(platform, root):
    """Select the captured original or matched PVT physical views explicitly."""
    root = Path(root).resolve(); prefix = platform.get('directory', '.')
    files = {x['path']: x for x in platform['files']}
    pvt = (Path(prefix)/'pvt/upstream-lock.json').as_posix() in files
    paths = dict(masters='pvt/sky130_fd_sc_hd.cdl' if pvt else 'cdl/sky130hd.cdl',
                 library='pvt/sky130_fd_sc_hd.gds' if pvt else 'gds/sky130_fd_sc_hd.gds',
                 deck='lvs/sky130hd.lylvs')
    result = {}
    for key, relative in paths.items():
        relative = (Path(prefix)/relative).as_posix(); path = (root/relative).resolve()
        require(relative in files and path.is_relative_to(root) and path.is_file() and
                file_digest(path) == files[relative]['sha256'], 'missing or changed platform '+key)
        result[key] = path
    for key in ('masters', 'deck'):
        expected = POLICY['masters_sha256s'] if key == 'masters' else [POLICY['deck_sha256']]
        require(normalized_digest(result[key].read_bytes()) in expected,
                'unreviewed '+key+' revision; this library needs a qualified connectivity adapter')
    return result


def measurements(folder, top):
    from . import digital_sky130_lvs_core as core
    folder = Path(folder)
    observed = json.loads((folder/'database.json').read_bytes())
    masters = (folder/'masters.cdl').read_bytes()
    reference, aliases, conversion = core.prepare_reference((folder/'raw-reference.cdl').read_text(), masters, observed)
    spice = (folder/(core.CELL+'.spice')).read_bytes()
    binding = core.verify_library(spice, folder/(core.CELL+'.gds'), folder/'library.gds')
    reference = core.enrich_reference(reference, spice)
    require(aliases['top'] == top, 'reference top differs from the job')
    return reference, aliases, conversion, binding


def execute(r):
    if r.platform['name'] != 'sky130hd': return None
    from . import digital_sky130_lvs_core as core
    resources(); sources = platform_sources(r.platform, r.root/'platform')
    folder = r.root/'sky130-lvs'; folder.mkdir()
    for key, name in (('masters', 'masters.cdl'), ('deck', 'upstream.lylvs'), ('library', 'library.gds')):
        shutil.copyfile(sources[key], folder/name)
    # Native OpenROAD's CDL parser handles LF consistently on both host paths.
    (folder/'masters.cdl').write_bytes((folder/'masters.cdl').read_bytes().replace(b'\r\n', b'\n'))
    for name in ASSET_HASHES: shutil.copyfile(ASSETS/name, folder/name)
    engine = {name:dict(path=r.tools[name], version=r.versions[name], sha256=file_digest(r.tools[name]))
              for name in ('openroad','klayout')}
    inputs = {key:dict(r.artifacts[key]) for key in ('gds','checkpoint','database')}
    for key,item in inputs.items():require(file_digest(r.root/item['path']) == item['sha256'], key+' changed before comparison')
    capture = dict(schema=1, top=r.config['top'],
        checkpoint=dict(path=str(r.root/inputs['checkpoint']['path']),sha256=inputs['checkpoint']['sha256']),
        masters=[dict(path=str(folder/'masters.cdl'),sha256=file_digest(folder/'masters.cdl'))],
        raw_cdl=str(folder/'raw-reference.cdl'),output=str(folder/'database.json'))
    atomic_write(folder/'capture-request.json',json.dumps(capture,indent=2)+'\n')
    shutil.copyfile(Path(__file__).with_name('digital_lvs_engine.py'),folder/'reference_engine.py')
    atomic_write(folder/'capture.py','import runpy\nrunpy.run_path('+repr(str(folder/'reference_engine.py'))+
                 ',init_globals={"REQUEST_PATH":'+repr(str(folder/'capture-request.json'))+'})\n')
    r.command([r.tools['openroad'],'-no_init','-exit','-python',str(folder/'capture.py')],
              'Capturing the independent SKY130 connectivity reference',cwd=folder,fraction=.98)
    observed = json.loads((folder/'database.json').read_bytes())
    require(observed['checkpoint_sha256'] == inputs['checkpoint']['sha256'] and
            observed['database'] == json.loads((r.root/inputs['database']['path']).read_bytes()),
            'independent database readback differs from the final implementation')
    reference, aliases, conversion, binding = measurements(folder, r.config['top'])
    atomic_write(folder/'reference.cdl', reference)
    for name,value in (('aliases',aliases),('conversion',conversion),('library-binding',binding)):
        atomic_write(folder/(name+'.json'),json.dumps(value,indent=2)+'\n')
    labels = core.label_copy(r.root/inputs['gds']['path'],folder/'labelled.gds',aliases)
    atomic_write(folder/'label-audit.json',json.dumps(labels,indent=2)+'\n')
    atomic_write(folder/'strict.lvs',core.strict_deck((folder/'upstream.lylvs').read_bytes(),r.config['top']))
    command = [r.tools['klayout'],'-b','-r',str(folder/'strict.lvs')]
    for name,value in dict(in_gds=folder/'labelled.gds',report_file=folder/'report.lvsdb',
                           cdl_file=folder/'reference.cdl',target_netlist=folder/'extracted.cir').items():
        command += ['-rd',name+'='+str(value)]
    request = dict(policy=POLICY,inputs=inputs,command=command,
        labelled_sha256=file_digest(folder/'labelled.gds'),reference_sha256=file_digest(folder/'reference.cdl'))
    atomic_write(folder/'request.json',json.dumps(request,indent=2)+'\n')
    log = r.command(command,'Checking SKY130 transistor, body, diode and port connectivity',cwd=folder,fraction=.99)
    atomic_write(folder/'native.log',log)
    require('ICSTUDIO_SKY130_LVS_COMPLETE' in log.splitlines(), 'native comparison did not finish')
    checked = core.audit(folder/'report.lvsdb',r.config['top'],list(aliases['ports'].values()))
    atomic_write(folder/'audit.json',json.dumps(checked,indent=2)+'\n')
    for key,item in inputs.items():require(file_digest(r.root/item['path']) == item['sha256'],key+' changed during comparison')
    for name,item in engine.items():require(file_digest(r.tools[name]) == item['sha256'],'engine changed during comparison')
    evidence = {}
    for name in FILES:
        key = 'sky130_lvs_'+name.replace('.','_').replace('-','_')
        r.add_artifact(key,folder/name);evidence[name]=key
    report = dict(schema=1,policy=POLICY,top=r.config['top'],status='PASS' if checked['matched'] else 'FAIL',
        qualified=False,scope=SCOPE,inputs={key:item['sha256'] for key,item in inputs.items()},
        platform_fingerprint=r.platform['fingerprint'],engine=engine,evidence=evidence,audit=checked)
    r.save_json('sky130_lvs',report,'sky130-lvs/report.json')
    require(checked['matched'],'final layout does not match its independent device/body/port reference; inspect the retained report')
    return report


def validate_saved(data, root):
    from . import digital_sky130_lvs_core as core
    root = Path(root).resolve();files = data['artifacts'];policy = data.get('environment',{}).get('sky130_lvs')
    declared = data.get('physical',{}).get('sky130_lvs')
    present = any(key == 'sky130_lvs' or key.startswith('sky130_lvs_') for key in files)
    if (root/'input.json').is_file():
        captured = json.loads((root/'input.json').read_bytes()).get('environment',{})
        require(captured.get('sky130_lvs') == policy,'policy differs from captured inputs')
    if policy is None and declared is None and not present: return None
    require(policy == POLICY and data.get('platform',{}).get('name') == 'sky130hd','missing or changed policy')
    resources()
    def read(key):
        require(key in files,'missing retained artifact: '+key)
        item = files[key];path = (root/item['path']).resolve()
        require(path.is_relative_to(root) and path.is_file() and file_digest(path) == item['sha256'], 'changed artifact: '+key)
        return path
    report = json.loads(read('sky130_lvs').read_bytes())
    require(report == declared and report.get('schema') == 1 and report.get('policy') == POLICY and
            report.get('status') == 'PASS' and report.get('scope') == SCOPE and report.get('qualified') is False,
            'missing, failed or changed declaration')
    require(report.get('platform_fingerprint') == data['platform']['fingerprint'],'platform identity differs')
    require(set(report.get('inputs',{})) == {'gds','checkpoint','database'},'incomplete checked inputs')
    for key,digest in report['inputs'].items():
        read(key);require(files[key]['sha256'] == digest,'comparison belongs to another '+key)
    evidence = report.get('evidence',{})
    require(set(evidence) == set(FILES) and len(set(evidence.values())) == len(FILES),'incomplete raw evidence')
    paths = {name:read(key) for name,key in evidence.items()}
    execution = data.get('execution',{}).get('native_environment',data.get('environment',{}))
    require(file_digest(paths['reference_engine.py']) == execution.get('sources',{}).get('digital_lvs_engine.py'),
            'reference capture worker differs from the executed source')
    for name,digest in ASSET_HASHES.items():require(file_digest(paths[name]) == digest,'changed resource: '+name)
    require(normalized_digest(paths['upstream.lylvs'].read_bytes()) == POLICY['deck_sha256'] and
            normalized_digest(paths['masters.cdl'].read_bytes()) in POLICY['masters_sha256s'],'changed library or extraction deck')
    observed = json.loads(paths['database.json'].read_bytes());capture = json.loads(paths['capture-request.json'].read_bytes())
    require(observed['top'] == report['top'] and observed['checkpoint_sha256'] == files['checkpoint']['sha256'] and
            observed['raw_cdl_sha256'] == file_digest(paths['raw-reference.cdl']) and
            observed['database'] == json.loads(read('database').read_bytes()),'reference database differs from the final implementation')
    require(capture['top'] == report['top'] and capture['checkpoint']['sha256'] == files['checkpoint']['sha256'] and
            len(capture['masters']) == 1 and capture['masters'][0]['sha256'] == file_digest(paths['masters.cdl']), 'capture request differs')
    reference,aliases,conversion = core.prepare_reference(paths['raw-reference.cdl'].read_text(),paths['masters.cdl'].read_bytes(),observed)
    spice = paths[core.CELL+'.spice'].read_bytes()
    binding = core.verify_library(spice,paths[core.CELL+'.gds'],paths['library.gds'])
    reference = core.enrich_reference(reference,spice)
    require(paths['reference.cdl'].read_text() == reference and json.loads(paths['aliases.json'].read_bytes()) == aliases and
            json.loads(paths['conversion.json'].read_bytes()) == conversion and
            json.loads(paths['library-binding.json'].read_bytes()) == binding,'reference conversion changed')
    require(paths['strict.lvs'].read_text() == core.strict_deck(paths['upstream.lylvs'].read_bytes(),report['top']),
            'native comparison settings changed')
    with tempfile.TemporaryDirectory(prefix='studio-sky130-lvs-') as temporary:
        target = Path(temporary)/'labels.gds';labels = core.label_copy(read('gds'),target,aliases)
        require(file_digest(target) == file_digest(paths['labelled.gds']) and
                labels == json.loads(paths['label-audit.json'].read_bytes()),'comparison layout or port placement changed')
    require('ICSTUDIO_SKY130_LVS_COMPLETE' in paths['native.log'].read_text().splitlines(),'native comparison incomplete')
    checked = core.audit(paths['report.lvsdb'],report['top'],list(aliases['ports'].values()))
    require(checked['matched'] and checked == report['audit'] == json.loads(paths['audit.json'].read_bytes()),'native connectivity comparison failed or changed')
    request = json.loads(paths['request.json'].read_bytes());command = request.get('command',[])
    require(request.get('policy') == POLICY and set(request.get('inputs',{})) == set(report['inputs']) and
            all(request['inputs'][k]['sha256'] == digest for k,digest in report['inputs'].items()) and
            request['labelled_sha256'] == file_digest(paths['labelled.gds']) and
            request['reference_sha256'] == file_digest(paths['reference.cdl']), 'execution input bindings changed')
    require(isinstance(command,list) and len(command) == 12 and command[1:3] == ['-b','-r'] and
            command[4::2] == ['-rd']*4,'invalid native command')
    require(command[0] == report['engine']['klayout']['path'] and Path(command[3]).name == 'strict.lvs',
            'native executable or recipe target changed')
    variables = dict(value.split('=',1) for value in command[5::2])
    expected = dict(in_gds='labelled.gds',report_file='report.lvsdb',cdl_file='reference.cdl',target_netlist='extracted.cir')
    require(set(variables) == set(expected) and all(Path(variables[k]).name == v for k,v in expected.items()),'native command targets changed')
    for name in ('openroad','klayout'):
        require(report['engine'][name]['version'] == data.get('versions',{}).get(name) and
                report['engine'][name]['sha256'] == execution.get('executables',{}).get(name),'engine identity changed')
    return report
