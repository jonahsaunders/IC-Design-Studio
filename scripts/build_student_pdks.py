"""Prepare redistributable teaching subsets from exact upstream PDK checkouts.

No GDS libraries, installed binaries, or complete PDK trees are bundled.
The existing GF180 simulation subset is retained; C/D use distinct full decks.
"""
import argparse
import json
from pathlib import Path
import shutil
import subprocess
import sys

ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from icstudio.model import atomic_write, file_digest
from icstudio.pdk_import import scan_local

IHP='5e6d592e4002946a4616f798c357f0f3c06cf3b6'
OPEN_PDKS='aa3fc215a80d32437b8cca1cb3fdee819d18c4c9'


def pinned(path, commit, inputs):
    actual=subprocess.check_output(['git','-c','safe.directory='+str(path.resolve()),'-C',str(path),'rev-parse','HEAD'],text=True).strip()
    if actual!=commit:raise ValueError('Use the pinned source commit '+commit)
    if subprocess.run(['git','-c','core.safecrlf=false','-c','safe.directory='+str(path.resolve()),'-C',str(path),'diff','--quiet','HEAD','--',*inputs],check=False).returncode:
        raise ValueError('Upstream source checkout must be unchanged.')


def build(ihp, open_pdks, output):
    pinned(ihp,IHP,['ihp-sg13g2/libs.tech','LICENSE'])
    pinned(open_pdks,OPEN_PDKS,['common/preproc.py','gf180mcu/magic/gf180mcu.tech','gf180mcu/netgen/gf180mcu_setup.tcl','LICENSE'])
    output.mkdir(parents=True,exist_ok=True)
    for variant in ('gf180mcuC','gf180mcuD','ihp-sg13g2'):
        target=output/variant
        if target.exists():raise ValueError('Use a fresh output directory: '+str(target))
        if variant.startswith('gf180'):
            shutil.copytree(ROOT/'icstudio/assets/pdks/gf180mcuD',target,
                            ignore=shutil.ignore_patterns('magic','netgen','package.json','PHYSICAL-SOURCE-LOCK.json','OPEN_PDKS_LICENSE'))
            for kind,source,destination in (
                ('magic','gf180mcu.tech',variant+'.tech'),('netgen','gf180mcu_setup.tcl',variant+'_setup.tcl')):
                folder=target/'libs.tech'/kind;folder.mkdir(exist_ok=True)
                subprocess.run([sys.executable,str(open_pdks/'common/preproc.py'),
                    str(open_pdks/'gf180mcu'/kind/source),str(folder/destination),
                    '-DTECHNAME='+variant,'-DREVISION='+OPEN_PDKS,'-DMETALS5','-DMIM',
                    '-DTHICKMET'+('0P9' if variant.endswith('C') else '1P1'),'-DHRPOLY1K','-DMAGIC_CURRENT=8.3'],check=True)
            shutil.copyfile(open_pdks/'LICENSE',target/'OPEN_PDKS_LICENSE')
            atomic_write(target/'PHYSICAL-SOURCE-LOCK.json',json.dumps({'repository':'https://github.com/fossi-foundation/open-pdks','commit':OPEN_PDKS,'variant':variant},indent=2))
        else:
            for folder in ('ngspice/models','verilog-a','magic','netgen','xschem/sg13g2_pr','klayout/tech'):
                source=ihp/variant/'libs.tech'/folder
                if folder=='klayout/tech':
                    destination=target/'libs.tech'/folder;destination.mkdir(parents=True)
                    for lyp in source.glob('*.lyp'):shutil.copyfile(lyp,destination/lyp.name)
                else:
                    shutil.copytree(source,target/'libs.tech'/folder,ignore=shutil.ignore_patterns('*.osdi','*.so','*.pyc','__pycache__','.git'))
            shutil.copyfile(ihp/'LICENSE',target/'LICENSE')
            atomic_write(target/'UPSTREAM-LOCK.json',json.dumps({'repository':'https://github.com/IHP-GmbH/IHP-Open-PDK','commit':IHP,'subset':'ngspice models and Verilog-A sources, symbols, layer map, Magic and Netgen decks'},indent=2))
        # These subsets contain text only. Normalize Git checkout line endings
        # before hashing so Linux and Windows builds get identical identities.
        for asset in target.rglob('*'):
            if asset.is_file():asset.write_bytes(asset.read_bytes().replace(b'\r\n',b'\n'))
        manifest=scan_local(target);manifest.pop('source_root',None)
        # Additional source attribution is part of the immutable package.
        for name in ('OPEN_PDKS_LICENSE','PHYSICAL-SOURCE-LOCK.json'):
            if (target/name).is_file():manifest['files'][name]=file_digest(target/name)
        from icstudio.model import digest
        manifest['technology']['revision']=''
        manifest['revision']=digest({'files':manifest['files'],'technology':manifest['technology']})[:16]
        manifest['technology']['revision']=manifest['revision']
        atomic_write(target/'package.json',json.dumps(manifest,indent=2)+'\n')
        print(variant,manifest['revision'],len(manifest['files']),flush=True)


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--ihp',type=Path,required=True);parser.add_argument('--open-pdks',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args();build(args.ihp.resolve(),args.open_pdks.resolve(),args.output.resolve())
