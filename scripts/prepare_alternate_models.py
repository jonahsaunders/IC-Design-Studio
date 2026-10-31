"""Expose reviewed, source-listed model choices as immutable catalog identities.

These are electrical model views. Availability of a model does not establish
layout support or compatibility with a selected fabrication metal option.
Original symbols, models, notices and existing catalog bindings are preserved.
"""
import argparse,json,shutil,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from icstudio.model import clone,digest,file_digest
from icstudio.catalog import create_device,validate_catalog
from scripts.inventory_device_models import inventory
from scripts.alternate_model_source import base_input

BASE={
    'sky130A':'ac79988e7ccf06ef550966de9ffc7ab394d934c5ddda861d1fb01e0813337f4b',
    'gf180mcuC':'408fa5e9d94e5e91d482988c26938bfb3b2a47dbfef68d8e5077144ba6eae1f0',
    'gf180mcuD':'ec95eefadaade5459b0bae8ac6d3d01d23927507ec10b86801fa4f2cf9f14bc2',
}
NOTE='ICSTUDIO-ALTERNATE-MODELS.json'


def alias_key(key,model):
    return key.removesuffix('.sym')+'__'+model+'.sym'


def expand(package,review):
    """Require reviewed interfaces; never infer terminal meaning from count."""
    catalog=package['technology']['simulation']['catalog']
    definitions={d['id']:d for d in review['definitions']};added=[]
    for choice in review['alternatives']:
        if choice['current_default']:continue
        parent=choice['device'];model=choice['model'];key=alias_key(parent,model)
        if key in catalog:raise ValueError('Alternate identity already exists.')
        entry=clone(catalog[parent]);entry['label']=model.removeprefix('sky130_fd_pr__')+' ('+Path(parent).stem+')'
        entry['model']=model;entry['alternate_of']=parent
        # Keep declarations on their original source view, not every derived view.
        entry['symbol']['attributes'].pop('available_models',None)
        entry['notes'].append('Explicit source-listed electrical model choice. Physical geometry, metal-option applicability and full operating range are not qualified by this binding.')
        matched=[definitions[i] for i in choice['definitions']]
        proof=dict(device=key,parent=parent,model=model,source_symbol=entry['source'],
                   source_symbol_sha256=package['files'][entry['source']],
                   namespace_normalized=choice['requires_namespace_adapter'],
                   definitions=choice['definitions'],absent_in_corners=choice['absent_in_corners'])
        if choice['absent_in_corners'] or not matched:
            entry['unavailable']='The source symbol lists this model, but its definition is absent from the locked simulation libraries. No substitute is selected.'
            entry.pop('model_source',None)
            proof['status']='UNAVAILABLE'
        else:
            sources=sorted({d['source'] for d in matched})
            if len(sources)!=1:raise ValueError('Alternate has an unreviewed multi-file interface.')
            if parent in ('sky130_fd_pr/diode.sym','sky130_fd_pr/lvsdiode.sym'):
                if entry['prefix']!='D' or entry['pin_order']!=['d0','d1'] or any(d.get('model_type')!='d' for d in matched):
                    raise ValueError('Unreviewed primitive diode interface.')
                proof['terminal_contract']=['anode','cathode']
            elif parent=='sky130_fd_pr/vpp_cap.sym':
                if entry['prefix']!='X' or entry['pin_order']!=['c0','c1','sub','top'] or set(entry['parameters'])!={'mult'}:
                    raise ValueError('Unreviewed VPP base binding.')
                orders={tuple(d.get('pins',[])) for d in matched}
                if len(orders)!=1 or next(iter(orders)) not in (('c0','c1','b','m4'),('c0','c1','b','m5')):
                    raise ValueError('Unreviewed VPP terminal interface.')
                proof['terminal_contract']=list(next(iter(orders)))
                entry['notes'].append('Fixed source geometry; top is the '+proof['terminal_contract'][-1].upper()+' shield, sub is substrate b. W/L are not adjustable.')
            elif parent=='symbols/cap_mim_analog.sym':
                if entry['prefix']!='X' or entry['pin_order']!=['g','b'] or any(d.get('pins')!=['1','2'] or not {'c_length','c_width'}<=set(d.get('parameters',[])) for d in matched):
                    raise ValueError('Unreviewed GF180 MIM interface.')
                proof['terminal_contract']=['1','2']
            else:raise ValueError('Unreviewed alternate source symbol.')
            entry['model_source']=sources[0]
            proof.update(status='AVAILABLE',source_model=sources[0],source_model_sha256=package['files'][sources[0]])
        catalog[key]=entry;added.append(proof)
    validate_catalog(package['technology'])
    tech=clone(package['technology']);tech['package_lock']={'id':package['id'],'revision':package['revision']}
    for row in added:
        if row['status']=='AVAILABLE':create_device(tech,row['device'],'CHECK')
    return added


@base_input
def prepare(source,output):
    source,output=Path(source).resolve(),Path(output).resolve()
    if output.exists():raise ValueError('Choose a new package directory; the output already exists.')
    original_hash=file_digest(source/'package.json')
    target=next((t for t,h in BASE.items() if h==original_hash),None)
    if target is None:raise ValueError('Input is not an exact reviewed alternate-model base.')
    package=json.loads((source/'package.json').read_bytes())
    review=inventory(source)
    if review['status']!='PASS':raise ValueError('Base model closure is incomplete.')
    added=expand(package,review)
    output.mkdir(parents=True)
    for rel,h in package['files'].items():
        src=(source/rel).resolve();dest=(output/rel).resolve()
        if not src.is_relative_to(source) or not dest.is_relative_to(output) or file_digest(src)!=h:
            raise ValueError('Changed or unsafe source asset: '+rel)
        dest.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(src,dest)
        if file_digest(dest)!=h:raise ValueError('Changed copied source asset: '+rel)
    note=dict(schema=1,base_manifest_sha256=original_hash,base_revision=package['revision'],choices=added,
              scope=__doc__,qualified=False)
    path=output/NOTE;path.write_bytes((json.dumps(note,sort_keys=True,indent=2)+'\n').encode())
    package['files'][NOTE]=file_digest(path);package['technology']['revision']=''
    package['revision']=package['technology']['revision']=digest({'files':package['files'],'technology':package['technology']})[:16]
    (output/'package.json').write_bytes((json.dumps(package,sort_keys=True,indent=2)+'\n').encode())
    return dict(revision=package['revision'],manifest_sha256=file_digest(output/'package.json'),
                base_manifest_sha256=original_hash,added=len(added),available=sum(r['status']=='AVAILABLE' for r in added),
                unavailable=sum(r['status']=='UNAVAILABLE' for r in added))


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--input',type=Path,required=True);p.add_argument('--output',type=Path,required=True)
    a=p.parse_args();print(json.dumps(prepare(a.input,a.output),indent=2))
