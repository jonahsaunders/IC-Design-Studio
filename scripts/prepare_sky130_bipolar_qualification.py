"""Prepare public NPN corner inputs alongside the tested resistor correction.

Only nominal/tt, ss and ff are enabled. This is an explicit local test package;
it does not silently guess NPN corners for mixed, mismatch or Monte Carlo modes.
"""
import argparse,hashlib,json,os,sys,tempfile
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from icstudio.model import digest,file_digest
from scripts.prepare_sky130_resistor_qualification import prepare as prepare_resistors
SOURCES=ROOT/'icstudio/assets/qualification/sky130-npn'
COMMIT='f62031a1be9aefe902d6d54cddd6f59b57627436'
BASE_MODEL_SHA256='82488580473c62809bc20ac4a0c31c27e1d65cb7c01493482d6f13645c99a478'


def inputs(source):
    lock=json.loads((SOURCES/'UPSTREAM-LOCK.json').read_bytes())
    if lock['commit']!=COMMIT or lock['license']!='Apache-2.0':raise ValueError('Changed NPN source provenance.')
    for name,expected in lock['files'].items():
        p=(SOURCES/name).resolve()
        if not p.is_relative_to(SOURCES.resolve()) or file_digest(p)!=expected:raise ValueError('Changed public NPN source: '+name)
    model='sky130_fd_pr__npn_05v5_W1p00L2p00.model.spice';installed=Path(source)/'libs.ref/sky130_fd_pr/spice'/model
    if file_digest(installed)!=BASE_MODEL_SHA256:raise ValueError('Use the reviewed bundled NPN model.')
    original=(SOURCES/model).read_bytes()
    adapted=original
    for parameter in ('is','bf'):
        adapted=adapted.replace(('sky130_fd_pr__npn_05v5_W1p00L2p00__'+parameter+'_slope_spectre*').encode(),b'MC_MM_SWITCH*AGAUSS(0,1.0,1)*')
    if adapted!=installed.read_bytes():raise ValueError('Bundled NPN equations differ from the reviewed public source.')
    return lock


def prepare(source,output):
    source=Path(source).resolve();output=Path(output).resolve();lock=inputs(source)
    if output.exists():raise ValueError('Choose a new bipolar adapter directory.')
    output.parent.mkdir(parents=True,exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='icstudio-npn-',dir=output.parent) as temp:
        stage=Path(temp)/'package';base=prepare_resistors(source,stage);package=json.loads((stage/'package.json').read_bytes());parts=[]
        additions={'qualification-sources/bipolar/'+name:(SOURCES/name).read_bytes() for name in [*lock['files'],'UPSTREAM-LOCK.json']}
        for corner in ('t','s','f'):
            name='sky130_fd_pr__npn_05v5__'+corner+'.corner.spice';text=(SOURCES/name).read_text()
            if text.count('.include')!=3:raise ValueError('Unexpected NPN include structure.')
            parts += ['* IC Design Studio modification: retain public corner parameters; locked models already supply definitions.',
                '.lib '+corner,text.split('.include',1)[0],'.endl '+corner,'']
        rel='libs.tech/ngspice/icstudio-npn-corners.lib';additions[rel]='\n'.join(parts).encode()
        sections={'nominal':'t','tt':'t','ss':'s','ff':'f'}
        # Restrict the visible source selection as well as the added include;
        # unsupported corners must fail rather than inherit a guessed NPN value.
        includes=package['technology']['simulation']['includes']
        for item in includes:
            if item.get('sections'):item['sections']={k:v for k,v in item['sections'].items() if k in sections}
        includes.append(dict(path=rel,sections=sections))
        provenance=dict(schema=1,source_repository=lock['repository'],source_commit=COMMIT,source_files=lock['files'],resistor_adapter=base,
            original_bundled_model_sha256=BASE_MODEL_SHA256,model_comparison='Only the two already-present open_pdks mismatch-expression adaptations differ. Deterministic coefficients match the public model; mismatch remains unqualified.',
            change='Copy original corner parameters and license notices; omit include lines to avoid replacing or duplicating existing locked models. Explicit NPN t/s/f selections accompany nominal/ss/ff for this test package.',
            scope='Selected deterministic NPN integration; no mixed/mismatch/Monte Carlo corner, full envelope, physical or foundry qualification.')
        additions['ICSTUDIO-NPN-PROVENANCE.json']=(json.dumps(provenance,indent=2)+'\n').encode()
        for rel,data in additions.items():
            p=stage/rel;p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(data);package['files'][rel]=hashlib.sha256(data).hexdigest()
        package['technology']['revision']='';package['revision']=package['technology']['revision']=digest(dict(files=package['files'],technology=package['technology']))[:16]
        (stage/'package.json').write_bytes((json.dumps(package,sort_keys=True,indent=2)+'\n').encode())
        if output.exists():raise ValueError('The new output directory was created during preparation.')
        os.rename(stage,output)
    return dict(id=package['id'],revision=package['revision'],manifest_sha256=file_digest(output/'package.json'),files=len(package['files']))


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--input',type=Path,default=ROOT/'icstudio/assets/pdks/sky130A');p.add_argument('--output',type=Path,required=True);a=p.parse_args();print(json.dumps(prepare(a.input,a.output),indent=2))
