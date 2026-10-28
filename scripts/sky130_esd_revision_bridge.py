"""Isolated, unqualified ESD default candidate and strict historical comparison.

The bridge proves byte identity/derivation only. It never asserts a GUI selection,
installed acceptance, or that staged electrical models came from the selected GUI.
"""
import copy, hashlib, json, shutil, tempfile
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from contextlib import contextmanager
from icstudio.model import digest, file_digest
from scripts.verify_frozen_mim import unlinked
from scripts.prepare_sky130_esd_nvt import prepare as prepare_optional, BASE, KEY, MODEL, PREFIX

OPTIONAL = '5315d2d6ad7618047eeeb48a15f81f221e6f42864647208acfb65124ee5c9c7a'
MARKER = 'ICSTUDIO-ESD-NVT-PROMOTION-CANDIDATE.json'
OLD_MARKER = 'ICSTUDIO-ESD-NVT-CANDIDATE.json'
# This candidate is not a promoted default or evidence of installed acceptance.
PROOF = {'schema':1, 'predecessor_manifest_sha256':BASE, 'optional_candidate_manifest_sha256':OPTIONAL,
         'device':KEY, 'status':'proposed-default-candidate', 'default_promoted':False,
         'qualified':False, 'chunk_complete':False,
         'scope':'Corrected finite-bin electrical binding; no ESD rating, physical, family, or installed qualification.'}
CURRENT = '0087ec54098f3d60deaa08442b2553dbc864d855ddf8b206887c4b85e6e42324'
REVISION = '644fb6bb9e99708e'

def _bytes(value): return (json.dumps(value,sort_keys=True,indent=2)+'\n').encode()
def _hash(data): return hashlib.sha256(data).hexdigest()
def _unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result: raise ValueError('Duplicate JSON key: '+key)
        result[key] = value
    return result

def _json(data):
    return json.loads(data, object_pairs_hook=_unique_object,
                      parse_constant=lambda value: (_ for _ in ()).throw(ValueError('Non-finite JSON')))
def _asset(root, name, expected):
    if not isinstance(name,str) or '\\' in name or name.startswith('/') or any(p in ('','.', '..') for p in name.split('/')):
        raise ValueError('Unsafe package asset path')
    path = root.joinpath(*name.split('/'))
    cursor = root
    for part in name.split('/'):
        cursor = cursor / part
        unlinked(cursor)
    if not path.resolve().is_relative_to(root.resolve()) or not path.is_file() or file_digest(path)!=expected:
        raise ValueError('Changed or unsafe package asset: '+name)
    return path

def _verify(root, expected):
    root=unlinked(root).resolve()
    if (root/'package.json').is_symlink(): raise ValueError('Linked package manifest')
    if file_digest(root/'package.json') != expected: raise ValueError('Wrong manifest identity')
    package=_json((root/'package.json').read_bytes())
    for name, sha in package['files'].items(): _asset(root,name,sha)
    return package

def prepare(source, output):
    source=unlinked(source).resolve(); output=unlinked(output).resolve()
    if output.exists() or output.is_relative_to(source) or source.is_relative_to(output): raise ValueError('Output must be new and separate')
    with tempfile.TemporaryDirectory(prefix='esd-promotion-prep-') as tmp:
        folder=Path(tmp)/'optional'; prepare_optional(source,folder)
        package=_verify(folder,OPTIONAL)
        del package['files'][OLD_MARKER]; (folder/OLD_MARKER).unlink()
        proof=_bytes(PROOF); (folder/MARKER).write_bytes(proof)
        package['files'][MARKER]=_hash(proof)
        package['technology']['revision']=''
        package['revision']=package['technology']['revision']=digest(dict(files=package['files'],technology=package['technology']))[:16]
        (folder/'package.json').write_bytes(_bytes(package))
        if CURRENT is not None and (file_digest(folder/'package.json')!=CURRENT or package['revision']!=REVISION): raise ValueError('Candidate identity changed')
        shutil.copytree(folder,output)
    return {'status':'PREPARED_NOT_PROMOTED', 'manifest_sha256':file_digest(output/'package.json'), 'revision':package['revision']}

def compare(current, historical_manifest):
    """Validate the exact candidate against exact predecessor and all its assets.

    Caller must separately bind current to actual GUI selection and staging; this
    function deliberately does not accept a receipt as a substitute for bytes.
    """
    if CURRENT is None: raise ValueError('Candidate identity not frozen')
    current=unlinked(current).resolve(); historical_manifest=unlinked(historical_manifest).resolve()
    new=_verify(current,CURRENT)
    if new['revision']!=REVISION or new['technology']['revision']!=REVISION: raise ValueError('Wrong revision')
    if file_digest(historical_manifest)!=BASE: raise ValueError('Wrong historical manifest')
    old=_json(historical_manifest.read_bytes())
    if old['revision']!='b26f7f28e659ddc1': raise ValueError('Wrong predecessor revision')
    for name, sha in old['files'].items():
        if new['files'].get(name)!=sha: raise ValueError('Historical asset manifest changed: '+name)
        _asset(current,name,sha)
    expected_added={MARKER, PREFIX+'LICENSE.skywater',PREFIX+'LICENSE.xschem', PREFIX+'nfet_g5v0d10v5_nvt_esd.sym',PREFIX+MODEL+'.pm3.spice',PREFIX+'source-lock.json'}
    if set(new['files'])-set(old['files']) != expected_added: raise ValueError('Unexpected additions')
    if (current/MARKER).read_bytes()!=_bytes(PROOF): raise ValueError('Changed promotion marker')
    a,b=copy.deepcopy(old['technology']),copy.deepcopy(new['technology'])
    if b['simulation']['includes'].pop() != {'path':PREFIX+MODEL+'.pm3.spice'}: raise ValueError('Changed ESD include')
    b['simulation']['catalog'][KEY]=a['simulation']['catalog'][KEY]
    b['revision']=a['revision']
    if a!=b: raise ValueError('Changed predecessor technology, catalog, model or corner mapping')
    return {'status':'BYTE_DERIVATION_ONLY', 'actual_package_path':str(current), 'actual_manifest_sha256':CURRENT,
            'actual_revision':REVISION, 'historical_manifest_sha256':BASE,
            'historical_revision':old['revision'], 'retained_assets':len(old['files']),
            'installed_acceptance':False, 'gui_selection_verified':False, 'staging_verified':False}

@contextmanager
def reconstruct(current, historical_manifest):
    proof=compare(current,historical_manifest)
    current=unlinked(current).resolve(); historical_manifest=unlinked(historical_manifest).resolve()
    old=_json(historical_manifest.read_bytes())
    with tempfile.TemporaryDirectory(prefix='esd-predecessor-') as tmp:
        out=Path(tmp)
        for name, sha in old['files'].items():
            src=_asset(current,name,sha); dest=out.joinpath(*name.split('/')); dest.parent.mkdir(parents=True,exist_ok=True)
            shutil.copyfile(src,dest); _asset(out,name,sha)
        shutil.copyfile(historical_manifest,out/'package.json'); _verify(out,BASE)
        yield out, proof


def compare_registry(registry_root, source_candidate, historical_manifest):
    """Bind Studio's reserialized installed registry to the exact candidate bytes."""
    registry_root=unlinked(registry_root).resolve(); source_candidate=unlinked(source_candidate).resolve()
    proof=compare(source_candidate,historical_manifest)
    expected=json.loads((source_candidate/'package.json').read_bytes())
    if (registry_root/'package.json').is_symlink(): raise ValueError('Linked registry manifest')
    actual=_json((registry_root/'package.json').read_bytes())
    if actual != expected: raise ValueError('Selected registry package differs from candidate')
    for name,sha in actual['files'].items(): _asset(registry_root,name,sha)
    return {**proof, 'actual_package_path':str(registry_root), 'registry_manifest_sha256':file_digest(registry_root/'package.json'),
            'source_manifest_sha256':CURRENT}

if __name__ == '__main__':
    import argparse
    ap=argparse.ArgumentParser(description=__doc__)
    sub=ap.add_subparsers(dest='action',required=True)
    prep=sub.add_parser('prepare'); prep.add_argument('--source',required=True); prep.add_argument('--output',required=True)
    check=sub.add_parser('compare'); check.add_argument('--current',required=True); check.add_argument('--predecessor',required=True)
    a=ap.parse_args()
    print(json.dumps(prepare(a.source,a.output) if a.action=='prepare' else compare(a.current,a.predecessor),indent=2))
