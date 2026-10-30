"""Build an opt-in corrected SKY130 ESD symbol package from exact public sources.

This does not replace the bundled default or rewrite existing project revisions.
The finite source-bin centers are simulation bindings, not ESD protection ratings.
"""
import argparse, hashlib, json, re, shutil, sys, tempfile
from contextlib import contextmanager
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from icstudio.model import clone,digest,file_digest
from icstudio.catalog import validate_catalog,create_device,parameter_values
from icstudio.symbol_io import import_symbol
from icstudio.pdk_import import template_values
from scripts.verify_frozen_mim import unlinked
SOURCES=ROOT/'icstudio/assets/qualification/sky130-esd-nvt-source-v1'
SOURCE_FILES = {
    "LICENSE.skywater": "cfc7749b96f63bd31c3c42b5c471bf756814053e847c10f3eb003417bc523d30",
    "LICENSE.xschem": "cce5dea3ff2bf1730e2dfb96c2170f7ec25ec15ef4b51ddfb691acf556072141",
    "corrected.sym": "71b1095bfeae82ad432fd32e530835352db14dbfbd8cf56cc864da74f6c12694",
    "correction-commit.json": "c9e016cc1990f620a8dc31f7e9a09e8cb28f3306c6c01fbe822bb5c093734c31",
    "esd_nfet_05v0_nvt.pm3.spice": "e2d6f3d08fa664eb5e6f875ea0c02e207b31fbbc29e65c1a522a29eb32412b25",
    "previous.sym": "06f2e73c4dd7fdfb7cbaa4c53b21f55ea712a6805e1d6c67a25105371e0caed7",
    "received-source-meta.json": "4b9a0795ee0e9edd2b948f32f1826f4bfdaf092b4c8f57cffcd6bf93127ba9c3",
    "test_nmos.sch": "c8bca703130fb584afbcb77e5176ec3960435cdc9b05b1619533599658997c5d",
    "verified-sources.json": "1dc1dbce469ad0fb3eb614983b0cef46da1732ad3f80efe80546597a8572126d"
}
BASE='840f7af802b07346650c50a5967e532a4cb1716623cf0c9d6fd6c58eaf35fcbe'
KEY='sky130_fd_pr/nfet_g5v0d10v5_nvt_esd.sym'
MODEL='sky130_fd_pr__esd_nfet_05v0_nvt'
PREFIX='libs.tech/ngspice/icstudio-esd-nvt/'
DEFAULT_CANDIDATE='125cde7c313ee18a05a7ec5c280d514b99aea521d6b39476e44f486ae494153b'
PREDECESSOR=ROOT/'icstudio/assets/qualification/sky130-esd-predecessor-v1/package.json'

@contextmanager
def predecessor(source, manifest=None):
    """Recover the reviewed predecessor only from the exact promoted candidate."""
    source=unlinked(source).resolve()
    unlinked(source/'package.json')
    from scripts.sky130_pw2dn_source import CURRENT as PW2DN_CURRENT, predecessor as pw2dn_predecessor
    if file_digest(source/'package.json') == PW2DN_CURRENT:
        with pw2dn_predecessor(source) as previous:
            with predecessor(previous, manifest) as original:
                yield original
        return
    if manifest is not None and file_digest(unlinked(manifest))!=BASE:
        raise ValueError('Wrong predecessor manifest identity.')
    if file_digest(source/'package.json')==BASE:
        yield source
        return
    manifest=unlinked(manifest or PREDECESSOR).resolve()
    if file_digest(source/'package.json')!=DEFAULT_CANDIDATE or file_digest(manifest)!=BASE:
        raise ValueError('Input is not the exact reviewed SKY130 default or candidate.')
    current=json.loads((source/'package.json').read_bytes())
    old=json.loads(manifest.read_bytes())
    with tempfile.TemporaryDirectory(prefix='esd-predecessor-') as tmp:
        out=Path(tmp)
        for name,sha in old['files'].items():
            path=unlinked(source/name).resolve()
            if not path.is_relative_to(source) or current['files'].get(name)!=sha or file_digest(path)!=sha:
                raise ValueError('Changed predecessor asset: '+name)
            dest=out/name;dest.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(path,dest)
        shutil.copyfile(manifest,out/'package.json')
        yield out

def prepare(source, output, sources=None):
    source=Path(source).resolve(); output=Path(output).resolve()
    if output.is_relative_to(source) or source.is_relative_to(output):
        raise ValueError('Output must be separate from the source package.')
    with predecessor(source) as original:
        return _prepare(original, output, sources)

def _prepare(source, output, sources=None):
    source=Path(source).resolve(); output=Path(output).resolve()
    if output.is_relative_to(source) or source.is_relative_to(output):
        raise ValueError('Output must be separate from the source package.')
    sources=Path(sources).resolve() if sources is not None else SOURCES
    for name,expected in SOURCE_FILES.items():
        if file_digest(sources/name)!=expected:raise ValueError('Changed public ESD source: '+name)
    if output.exists():raise ValueError('Choose a new output directory.')
    if not (file_digest(source/'package.json')==BASE):raise ValueError('Input is not the exact reviewed SKY130 default.')
    original=json.loads((source/'package.json').read_bytes()); package=clone(original)
    for rel,sha in original['files'].items():
        path=source/rel
        if not (path.resolve().is_relative_to(source.resolve()) and file_digest(path)==sha):raise ValueError('Changed or unsafe original SKY130 asset: ' + rel + '')
    lock=json.loads((sources/'verified-sources.json').read_bytes())
    for row in lock['files']:
        if not (file_digest(sources/row['file'])==row['sha256']):raise ValueError('Changed public source lock asset.')
    symbol,meta,notes=import_symbol(sources/'corrected.sym')
    values=template_values(meta['template'])
    if not (values['model']=='esd_nfet_05v0_nvt' and values['w']=='10' and values['l']=='2'):raise ValueError('Unexpected corrected symbol model or defaults.')
    if not (symbol['pin_order']==['d','g','s','b'] and meta['type']=='nmos'):raise ValueError('Unexpected corrected symbol pin order or type.')
    pm=(sources/'esd_nfet_05v0_nvt.pm3.spice').read_text(encoding='utf-8')
    if not (re.search(r'(?m)^\.subckt\s+'+MODEL+r'\s+d g s b\s*$',pm)):raise ValueError('Unexpected ESD model terminals.')
    if not (len(re.findall(r'(?m)^\.model '+MODEL+r'__model\.[012] nmos$',pm))==3):raise ValueError('Unexpected ESD model bin count.')
    if not ([tuple(map(float,m)) for m in re.findall(r'lmin = ([^ ]+) lmax = ([^ ]+) wmin = ([^ ]+) wmax = ([^\n]+)',pm)]==[(1.995e-6,2.005e-6,9.995e-6,1.0005e-5),(3.995e-6,4.005e-6,9.995e-6,1.0005e-5),(8.95e-7,9.05e-7,9.995e-6,1.0005e-5)]):raise ValueError('Unexpected ESD model bin domains.')
    entry=clone(original['technology']['simulation']['catalog']['sky130_fd_pr/nfet_05v0_nvt.sym'])
    if not (original['technology']['simulation']['catalog'][KEY]['unavailable']):raise ValueError('Expected the historical symbol to be unavailable.')
    expected={'w','l','nf','mult','ad','as','pd','ps','nrd','nrs','sa','sb','sd'}
    if not (set(entry['parameters'])==expected):raise ValueError('Unexpected baseline parameter set.')
    for key in expected:
        if not (key in values):raise ValueError('Corrected source parameter is missing.')
        entry['parameters'][key]['default']=values[key].lower()
    # Finite newly supported source bin centers, not process geometry/voltage ratings.
    entry['parameters']['w'].update(fixed='10',unit='um')
    entry['parameters']['l'].update(choices={'0.9':0.9,'2':2.0,'4':4.0},unit='um')
    entry['parameters']['nf'].update(fixed='1')
    entry.update(model=MODEL,label='esd_nfet_05v0_nvt (corrected native ESD symbol)',
        source=PREFIX+'nfet_g5v0d10v5_nvt_esd.sym',model_source=PREFIX+MODEL+'.pm3.spice',symbol=symbol,
        unavailable='',notes=['Official Xschem correction08367118 changes this symbol to esd_nfet_05v0_nvt with default W10/L2. Three explicit public model-bin centers W10/L0.9,2,4 and nf1 only. Electrical simulation binding; not ESD protection, reliability, layout or whole-family qualification. Historical unavailable models/revisions are unchanged.'])
    package['technology']['simulation']['catalog'][KEY]=entry
    package['technology']['simulation']['includes'].append({'path':PREFIX+MODEL+'.pm3.spice'})
    additions={PREFIX+'nfet_g5v0d10v5_nvt_esd.sym':(sources/'corrected.sym').read_bytes(),
        PREFIX+MODEL+'.pm3.spice':(sources/'esd_nfet_05v0_nvt.pm3.spice').read_bytes(),
        PREFIX+'LICENSE.xschem':(sources/'LICENSE.xschem').read_bytes(),
        PREFIX+'LICENSE.skywater':(sources/'LICENSE.skywater').read_bytes(),
        PREFIX+'source-lock.json':(sources/'verified-sources.json').read_bytes()}
    proof={'schema':1,'source_manifest_sha256':BASE,'device':KEY,'old_binding':original['technology']['simulation']['catalog'][KEY],
        'upstream_correction':'https://github.com/StefanSchippers/xschem_sky130/commit/08367118f8ad7311b9264b856fb4d5f1f58b45f9',
        'change':'Adopt exact corrected source-listed symbol/model with original model equations and licenses; finite supported bin centers.',
        'default_promoted':False,'qualified':False,'chunk_complete':False,'scope':'Separate exploratory candidate, not installed or ESD rating evidence.'}
    additions['ICSTUDIO-ESD-NVT-CANDIDATE.json']=(json.dumps(proof,indent=2)+'\n').encode()
    for rel,data in additions.items():
        if rel in original['files']:raise ValueError('New ESD asset would replace an original.')
        package['files'][rel]=hashlib.sha256(data).hexdigest()
    validate_catalog(package['technology'])
    package['technology']['revision']=''
    package['revision']=package['technology']['revision']=digest(dict(files=package['files'],technology=package['technology']))[:16]
    output.mkdir(parents=True)
    for rel,sha in package['files'].items():
        dest=output/rel;dest.parent.mkdir(parents=True,exist_ok=True)
        if rel in additions:dest.write_bytes(additions[rel])
        else:shutil.copyfile(source/rel,dest)
        if not (file_digest(dest)==sha):raise ValueError('ESD output changed during preparation.')
    (output/'package.json').write_bytes((json.dumps(package,sort_keys=True,indent=2)+'\n').encode())
    if not ({k:v for k,v in package['technology']['simulation']['catalog'].items() if k!=KEY}=={k:v for k,v in original['technology']['simulation']['catalog'].items() if k!=KEY}):raise ValueError('An unrelated catalog binding changed.')
    tech=clone(package['technology']);tech.update(package_root=str(output),package_lock={k:package[k] for k in ('id','revision','files')})
    d=create_device(tech,KEY,'M1');parameters=parameter_values(entry,d)
    if not (parameters['w']==10 and parameters['l']==2 and parameters['nf']==1):raise ValueError('Fresh ESD placement differs from corrected source defaults.')
    if file_digest(output/'package.json') != '5315d2d6ad7618047eeeb48a15f81f221e6f42864647208acfb65124ee5c9c7a':
        raise ValueError('Rebuilt candidate differs from the reviewed package identity.')
    result=dict(status='PREPARED_NOT_QUALIFIED',revision=package['revision'],manifest_sha256=file_digest(output/'package.json'),parameters=parameters,model=MODEL,original_assets_unchanged=True,default_promoted=False)
    return result

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--input',type=Path,default=ROOT/'icstudio/assets/pdks/sky130A')
    p.add_argument('--output',type=Path,required=True)
    a=p.parse_args();print(json.dumps(prepare(a.input,a.output),indent=2))
