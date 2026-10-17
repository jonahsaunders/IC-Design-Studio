"""Build a separate SKY130 HD PVT/RC platform from checksum-pinned archives."""
import argparse
import json
from pathlib import Path
import shutil
import sys
import tarfile
import tempfile

ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from icstudio import digital_platform
from icstudio.model import file_digest
from scripts.fetch_sky130_reference import download_archive

LIBRARIES={'typical':'sky130_fd_sc_hd__tt_025C_1v80.lib',
           'slow':'sky130_fd_sc_hd__ss_100C_1v60.lib','fast':'sky130_fd_sc_hd__ff_n40C_1v95.lib'}
RC={'minimum':'min','nominal':'nom','maximum':'max'}


def required_files():
    cell='sky130A/libs.ref/sky130_fd_sc_hd/'
    names=[cell+'lib/'+name for name in LIBRARIES.values()]
    names += [cell+'techlef/sky130_fd_sc_hd__'+name+'.tlef' for name in RC.values()]
    names += [cell+name for name in ('lef/sky130_fd_sc_hd.lef','lef/sky130_ef_sc_hd.lef',
        'gds/sky130_fd_sc_hd.gds','cdl/sky130_fd_sc_hd.cdl')]
    names += ['sky130A/libs.tech/openlane/rules.openrcx.sky130A.'+name+'.spef_extractor' for name in RC.values()]
    return {name:'sky130hd/pvt/'+Path(name).name for name in names}


def prepare(orfs,output,cache):
    out=Path(output).resolve();cache=Path(cache).resolve()
    if out.exists() and any(out.iterdir()):raise ValueError('Choose an empty platform destination.')
    original=digital_platform.from_orfs(orfs,'sky130hd')
    lock=json.loads((ROOT/'examples/sky130-reference-assets.json').read_text())
    cache.mkdir(parents=True,exist_ok=True);archives={}
    for name in ('common.tar.zst','sky130_fd_sc_hd.tar.zst'):
        path=cache/name;expected=lock['files'][name]
        if not path.is_file() or file_digest(path)!=expected:
            download_archive(f'https://github.com/{lock["repository"]}/releases/download/{lock["release"]}/{name}',path,expected)
        archives[name]=path
    from backports import zstd
    out.parent.mkdir(parents=True,exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='sky130-digital-',dir=out.parent) as temporary:
        staging=Path(temporary)/'platform';digital_platform.stage(original,staging)
        wanted=required_files();captured={}
        for archive_name,path in archives.items():
            with zstd.open(path,'rb') as stream,tarfile.open(fileobj=stream,mode='r|') as archive:
                for member in archive:
                    if member.name not in wanted:continue
                    if member.name in captured or not member.isfile() or not 0<member.size<=digital_platform.MAX_LIBERTY_BYTES:
                        raise ValueError('Duplicate, unsupported or oversized PDK member: '+member.name)
                    target=staging/wanted[member.name];target.parent.mkdir(parents=True,exist_ok=True)
                    with archive.extractfile(member) as source,target.open('wb') as dest:shutil.copyfileobj(source,dest)
                    captured[member.name]={'archive':archive_name,'path':wanted[member.name],'sha256':file_digest(target),'bytes':target.stat().st_size}
        if set(captured)!=set(wanted):raise ValueError('The pinned archives omit required digital PVT/RC collateral.')
        directory=staging/'sky130hd';pvt=directory/'pvt'
        config=(directory/'config.mk').read_text();(pvt/'orfs-config.mk').write_text(config,newline='\n')
        overrides={'TECH_LEF':'sky130_fd_sc_hd__nom.tlef',
            'SC_LEF':'sky130_fd_sc_hd.lef','ADDITIONAL_LEFS':'sky130_ef_sc_hd.lef','GDS_FILES':'sky130_fd_sc_hd.gds',
            'CDL_FILE':'sky130_fd_sc_hd.cdl','RCX_RULES':'rules.openrcx.sky130A.nom.spef_extractor'}
        config+='\n# IC Design Studio: matched physical views from the pinned PVT/RC archive.\n'
        for key,value in overrides.items():
            config+='export '+key+(' += ' if key=='ADDITIONAL_LEFS' else ' = ')+' '.join('$(PLATFORM_DIR)/pvt/'+name for name in value.split())+'\n'
        (directory/'config.mk').write_text(config,newline='\n')
        shutil.copy2(ROOT/'licenses/Apache-2.0.txt',pvt/'LICENSE-Apache-2.0.txt')
        provenance={'release':lock['release'],'repository':lock['repository'],
            'archives':{name:lock['files'][name] for name in archives},
            'orfs_revision':original['revision'],'original_orfs_platform_fingerprint':original['fingerprint'],
            'captured_files':captured,'physical_overrides':overrides,
            'scope':'Separate integration candidate; no process, design or foundry qualification is implied.'}
        (pvt/'upstream-lock.json').write_text(json.dumps(provenance,indent=2)+'\n',newline='\n')
        manifest={k:v for k,v in original.items() if k not in ('root','files','fingerprint')}
        manifest['revision']=original['revision']+' + '+lock['release']
        manifest['corners']={key:['sky130hd/pvt/'+name] for key,name in LIBRARIES.items()}
        manifest['extraction']={'cell_lefs':['sky130hd/pvt/sky130_fd_sc_hd.lef','sky130hd/pvt/sky130_ef_sc_hd.lef'],
            'coupling_threshold_ff':0.1,'corners':{key:{
                'rules':'sky130hd/pvt/rules.openrcx.sky130A.'+name+'.spef_extractor',
                'technology_lef':'sky130hd/pvt/sky130_fd_sc_hd__'+name+'.tlef'} for key,name in RC.items()}}
        manifest['files']=sorted(p.relative_to(staging).as_posix() for p in directory.rglob('*') if p.is_file())
        path=staging/'platform.json';path.write_text(json.dumps(manifest,indent=2)+'\n',newline='\n')
        digital_platform.verify(digital_platform.read_manifest(path))
        if out.exists():out.rmdir()
        staging.replace(out)
    return out/'platform.json'


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--orfs',type=Path,required=True);parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--cache',type=Path,required=True);args=parser.parse_args()
    print(prepare(args.orfs,args.output,args.cache))


if __name__=='__main__':main()
