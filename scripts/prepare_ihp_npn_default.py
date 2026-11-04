"""Add the reviewed NPN rule entry point while retaining every earlier asset."""
import argparse, hashlib, json, shutil, sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from icstudio.model import digest,file_digest
from icstudio.ihp_npn_rules import RELATIVE_PATH,BASE_SHA256,corrected
from scripts.ihp_npn_source import BASE,previous_npn

TECH='libs.tech/magic/ihp-sg13g2.tech'
TECH_SHA256='0a0e1666da3fa38d7faefe340576102ddc558727a3f6f7f666e92f50a1dc568d'
ENTRY='libs.tech/magic/icstudio-ihp-sg13g2.tech'
RULE='libs.tech/magic/icstudio-ihp-sg13g2-cifout.tech'
NOTE='ICSTUDIO-NPN-DEFAULT.json'
ORIGINAL=b'include ihp-sg13g2-cifout\n'
REPLACEMENT=b'# IC Design Studio: use the separately identified NPN traversal correction.\ninclude icstudio-ihp-sg13g2-cifout\n'


def prepare(source,output):
    output=Path(output).resolve()
    if output.exists():raise ValueError('Choose a new IHP default package directory.')
    with previous_npn(source) as source:
        source=Path(source).resolve()
        if file_digest(source/'package.json')!=BASE:raise ValueError('Use the exact reviewed IHP tap default.')
        package=json.loads((source/'package.json').read_bytes())
        for name,expected in package['files'].items():
            path=(source/name).resolve()
            if not path.is_relative_to(source) or not path.is_file() or file_digest(path)!=expected:
                raise ValueError('Changed IHP source asset: '+name)
        technology=(source/TECH).read_bytes()
        if hashlib.sha256(technology).hexdigest()!=TECH_SHA256 or technology.count(ORIGINAL)!=1:
            raise ValueError('Unexpected IHP technology entry point.')
        rule=corrected((source/RELATIVE_PATH).read_bytes())
        entry=technology.replace(ORIGINAL,REPLACEMENT)
        proof=dict(schema=1,source_manifest_sha256=BASE,source_revision=package['revision'],
            original_entry=dict(path=TECH,sha256=TECH_SHA256),original_rule=dict(path=RELATIVE_PATH,sha256=BASE_SHA256),
            corrected_entry=dict(path=ENTRY,sha256=hashlib.sha256(entry).hexdigest()),
            corrected_rule=dict(path=RULE,sha256=hashlib.sha256(rule).hexdigest()),
            change='Select the previously reviewed NPN connected-region traversal through a separate technology entry point. Every previous asset and all simulation settings remain byte-identical.',
            scope='Default integration of a local public DRC correction. Each design still needs full DRC/LVS; no complete PDK, device-envelope or foundry qualification.',
            license='Original Apache-2.0 source notices and license retained. Local changes explicitly identified in both derived files.')
        additions={ENTRY:entry,RULE:rule,NOTE:(json.dumps(proof,indent=2)+'\n').encode()}
        for name,data in additions.items():package['files'][name]=hashlib.sha256(data).hexdigest()
        package['technology'].setdefault('interoperability',{}).setdefault('tools',{}).setdefault('magic',{})['technology']=ENTRY
        package['technology']['revision']=''
        package['revision']=package['technology']['revision']=digest({'files':package['files'],'technology':package['technology']})[:16]
        output.mkdir(parents=True)
        for name,expected in package['files'].items():
            dest=output/name;dest.parent.mkdir(parents=True,exist_ok=True)
            if name in additions:dest.write_bytes(additions[name])
            else:shutil.copyfile(source/name,dest)
            if file_digest(dest)!=expected:raise ValueError('IHP source changed during transfer: '+name)
        (output/'package.json').write_bytes((json.dumps(package,sort_keys=True,indent=2)+'\n').encode())
        return dict(revision=package['revision'],manifest_sha256=file_digest(output/'package.json'),proof=proof)


if __name__=='__main__':
    ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--input',type=Path,default=ROOT/'icstudio/assets/pdks/ihp-sg13g2');ap.add_argument('--output',type=Path,required=True)
    a=ap.parse_args();print(json.dumps(prepare(a.input,a.output),indent=2))
