"""Versioned GF180 native-MOS and IHP clamp corrections, with unchanged models.

Original packages/projects retain their exact bindings. Corrections are gated by
the reviewed public source hashes; no model coefficients are fitted or replaced.
"""
import argparse, hashlib, json, shutil, sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from icstudio.model import clone, digest, file_digest
from icstudio.catalog import validate_catalog
MANIFESTS={'gf180mcuC':'92ed3a348c93cde49bf48f2edf37a4f41bee6a0d3741b04f7c5ebfbdbc23ac7f',
           'gf180mcuD':'b4200b48f3fe59e961a4f514cdcb7166d21c231bccef586f01a7fa6b5f2ed738',
           'ihp-sg13g2':'63616ff9b0af1ec391e325d8f5a44ec7a5a45b420ce9a1e0946fbb14b028057c'}
GF_SYMBOL_SHA='ab5c69d892be9acba70cbcbf2788dc5a8601be90a11565c9507bae6c74e91fad'
GF_MODEL_SHA='c08ee93073665b6c1f43a3523bb38d5b561bcee2b7e056a927175f5da8e96ba9'
IHP_MODEL_SHA='84ec57080b9dd4666417f05db6f7b34c8dd3f12118929f9b308018613bece16e'
IHP_SYMBOL_SHA={'nmoscl_2':'f132a6a8314844f9d63d8b9bb2704511220e190fc89995f41b6209c4e29e2596',
                'nmoscl_4':'f5d805eb1dc3d0adcc224c94ff59756d22ef5d2cb66f24dd442b3f80bef3a0d6'}


def correct_native(entry, symbol, model):
    if hashlib.sha256(symbol).hexdigest()!=GF_SYMBOL_SHA or hashlib.sha256(model).hexdigest()!=GF_MODEL_SHA:
        raise ValueError('Unreviewed native-MOS source.')
    if entry['model']!='nfet_06v0' or entry['pin_order']!=['d','g','s','b']:
        raise ValueError('Unexpected native-MOS binding.')
    entry['model']='nfet_06v0_nvt';entry['model_source']='libs.tech/ngspice/sm141064.ngspice'
    entry['symbol']['attributes']['template']=entry['symbol']['attributes']['template'].replace('model=nfet_06v0\n','model=nfet_06v0_nvt\n')
    entry['notes'].append('Select the public nfet_06v0_nvt native-threshold model. The original symbol incorrectly selected nfet_06v0. This changes metadata only; public model equations and available corner sections are unchanged.')


def correct_clamp(entry, symbol, model):
    name=entry['model']
    if name not in IHP_SYMBOL_SHA or hashlib.sha256(symbol).hexdigest()!=IHP_SYMBOL_SHA[name] or hashlib.sha256(model).hexdigest()!=IHP_MODEL_SHA:
        raise ValueError('Unreviewed clamp source.')
    if entry['pin_order']!=['vss','vdd']:raise ValueError('Unexpected clamp terminal order.')
    entry['pin_order']=['vdd','vss'];entry['symbol']['pin_order']=['vdd','vss']
    entry['notes'].append('Model order VDD VSS agrees with explicit symbol sim_pinnumber 1/2. Terminal locations and labels are unchanged. This is a connection correction, not an ESD robustness rating.')


def prepare(source, output):
    source,output=Path(source).resolve(),Path(output).resolve()
    if output.exists():raise ValueError('Choose a new MOS correction directory.')
    original=json.loads((source/'package.json').read_bytes())
    manifest=file_digest(source/'package.json')
    target=next((t for t,h in MANIFESTS.items() if h==manifest),None)
    if target is None:raise ValueError('Use an exact reviewed MOS source package.')
    for rel,h in original['files'].items():
        p=(source/rel).resolve()
        if not p.is_relative_to(source) or file_digest(p)!=h:raise ValueError('Changed MOS source asset: '+rel)
    if target=='ihp-sg13g2':
        from scripts.prepare_ihp_svaricap_binding import prepare as parent_prepare
        parent=parent_prepare(source,output);package=json.loads((output/'package.json').read_bytes())
    else:
        parent=None;package=clone(original);output.mkdir(parents=True)
        for rel,h in original['files'].items():
            p=output/rel;p.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(source/rel,p)
            if file_digest(p)!=h:raise ValueError('MOS source changed during copy: '+rel)
    catalog=package['technology']['simulation']['catalog'];changed={}
    keys=['symbols/nfet_06v0_nvt.sym'] if target.startswith('gf180') else ['sg13g2_pr/'+n+'.sym' for n in IHP_SYMBOL_SHA]
    for key in keys:
        entry=catalog[key];changed[key]=clone(entry)
        symbol=(source/entry['source']).read_bytes()
        if target.startswith('gf180'):correct_native(entry,symbol,(source/'libs.tech/ngspice/sm141064.ngspice').read_bytes())
        else:correct_clamp(entry,symbol,(source/entry['model_source']).read_bytes())
    validate_catalog(package['technology'])
    note=dict(schema=1,original_manifest_sha256=manifest,parent=parent,original_bindings=changed,
              scope='Explicit source-backed model/terminal corrections only. Upstream asset bytes retained. No complete operating envelope, physical, RF accuracy or ESD qualification.')
    path=output/'ICSTUDIO-MOS-BINDINGS.json';path.write_bytes((json.dumps(note,indent=2)+'\n').encode());package['files'][path.name]=file_digest(path)
    package['technology']['revision']='';package['revision']=package['technology']['revision']=digest({'files':package['files'],'technology':package['technology']})[:16]
    (output/'package.json').write_bytes((json.dumps(package,sort_keys=True,indent=2)+'\n').encode())
    return dict(revision=package['revision'],manifest_sha256=file_digest(output/'package.json'),original_manifest_sha256=manifest,changed_bindings=keys,parent=parent)


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--input',type=Path,required=True);p.add_argument('--output',type=Path,required=True)
    a=p.parse_args();print(json.dumps(prepare(a.input,a.output),indent=2))
