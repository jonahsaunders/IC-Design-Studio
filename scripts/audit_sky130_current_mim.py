"""Independent source-only v2 reader: actual Qt selected package and MiM closure.
Not an installed, electrical, physical or family acceptance reader.
"""
import json, re
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from icstudio.model import file_digest, load_project, design_digest, digest
from icstudio.catalog import binding_for, parameter_values
from icstudio.mim_desktop_probe import verified_package
from scripts.installed_mim_inputs import inventory
from scripts.audit_sky130_mim_passive_corners import verify_models
from scripts.verify_frozen_mim import circuit
from icstudio.pdks import model_lines
from scripts import sky130_esd_revision_bridge as bridge
from scripts.qualify_sky130_current_mim import sources

CONTRACT_SHA='b324813599a364c83e76e63f583e7b74da50ab8182640a1cb907796a3ce1c209'

def require(c,m):
    if not c: raise ValueError(m)

def verify_exports(schematic, reference, tech, plate):
    """Check circuit content and selected model directives, independent of receipt hashes."""
    circuit(reference.read_text(encoding='utf-8'), 'device_coupon', plate)
    lines = [line.strip() for line in schematic.read_text(encoding='utf-8').splitlines()
             if line.strip() and not line.lstrip().startswith('*')]
    elements = [line for line in lines if not line.startswith('.')]
    require(len(elements) == 1, 'Schematic element count differs')
    circuit('.subckt device_coupon P N\n'+elements[0]+'\n.ends device_coupon\n', 'device_coupon', plate)
    directives = [line for line in lines if line.lower().startswith(('.include ', '.lib '))]
    require(directives == model_lines(tech, 'nominal'), 'Schematic model includes differ')
    require(all(not line.startswith('.') or line in directives or line.lower().startswith(('.temp ', '.tran ')) or line.lower()=='.end' for line in lines), 'Unexpected schematic directive')

def read(root, expected_report_sha, expected_nonce, contract, expected_sources):
    root=Path(root).resolve();report_path=root/'report.json'
    require(re.fullmatch('[0-9a-f]{64}',expected_report_sha or '') and re.fullmatch('[0-9a-f]{32}',expected_nonce or ''),'Trusted report identity and nonce required')
    require(report_path.is_file() and file_digest(report_path)==expected_report_sha,'Missing or stale GUI report')
    report=bridge._json(report_path.read_bytes())
    require(isinstance(expected_sources, dict) and bool(expected_sources), 'External expected source identities required')
    require(report.get('source_files') == expected_sources == sources(), 'Application or script source identities differ')
    require(report.get('schema')=='mim-current-source-probe-v2' and report.get('status')=='PASS' and report.get('nonce')==expected_nonce and report.get('execution_root')==str(root) and report.get('mode')=='source-qt','GUI identity differs')
    require(report.get('qualified') is False and report.get('installed_acceptance') is False,'Scope overstatement')
    require(file_digest(contract)==CONTRACT_SHA,'Historical MiM contract changed')
    cur=report['current'];prev=report['predecessor']; current=bridge.unlinked(cur['path']).resolve()
    require(cur['revision']==bridge.REVISION and prev['manifest_sha256']==bridge.BASE and prev['revision']=='b26f7f28e659ddc1','Current or predecessor identity differs')
    require(current.is_relative_to(root/'profile') and current.name==cur['registry_key'] and cur['registry_key']!=prev['registry_key'],'Actual GUI registry selection differs')
    require(file_digest(root/'contract-sources/package')==cur['manifest_sha256'] and file_digest(root/'contract-sources/candidate')==bridge.CURRENT and file_digest(root/'contract-sources/predecessor')==bridge.BASE,'Captured package identities differ')
    verified_package(current,cur['manifest_sha256'])
    proof=bridge.compare_registry(current,report['source_candidate_path'],root/'contract-sources/predecessor')
    require(file_digest(current/'package.json')==cur['manifest_sha256'] and proof['registry_manifest_sha256']==cur['manifest_sha256'],'Actual registry manifest differs')
    require(report['source_manifest']==bridge.CURRENT,'Source candidate differs')
    for name in ('old_before','old_after'):
        row=report[name]; path=Path(row['project']).resolve()
        require(path.is_relative_to(root) and path.is_file() and file_digest(path)==row['project_sha256'],'Missing old GUI project')
        p=load_project(path); oldtech=p['pdk']; oldroot=bridge.unlinked(oldtech['package_root']).resolve()
        oldmanifest=bridge.unlinked(oldroot/'package.json')
        oldpackage=bridge._json(oldmanifest.read_bytes())
        require(verified_package(oldroot)==oldpackage, 'Old registry package parsing differs')
        require(oldroot.is_relative_to(root/'profile') and oldroot.name==prev['registry_key'] and oldpackage==bridge._json((root/'contract-sources/predecessor').read_bytes()),'Old registry differs')
        require({k:v for k,v in oldtech.items() if k not in ('package_root','package_lock')}==oldpackage['technology'] and oldtech['package_lock']=={**{k:oldpackage[k] for k in ('id','revision','files')},'manifest_hash':digest(oldpackage)} and oldtech['revision']=='b26f7f28e659ddc1' and oldtech['package_lock']==row['package_lock'] and design_digest(p)==row['design_hash'],'Old GUI project identity differs')
    require(report['old_before']['package_lock']==report['old_after']['package_lock'],'Old saved revision migrated')
    require(report['old_before']['design_hash']==report['old_after']['design_hash'],'Old saved design changed')
    require([x.get('plate') for x in report['current_projects']]==[1,2],'Missing current GUI projects')
    for row in report['current_projects']:
        path=Path(row['project']).resolve();require(path.is_relative_to(root) and path.is_file() and file_digest(path)==row['project_sha256'],'Missing current GUI project')
        p=load_project(path); tech=p['pdk'];lock=tech['package_lock'];
        require(tech['revision']==bridge.REVISION and Path(tech['package_root']).resolve()==current and lock==row['package_lock'] and lock['revision']==bridge.REVISION and design_digest(p)==row['design_hash'],'GUI project selected a different package')
        package=json.loads((current/'package.json').read_bytes());require({k:v for k,v in tech.items() if k not in ('package_root','package_lock')}==package['technology'],'GUI technology differs');require(lock=={**{k:package[k] for k in ('id','revision','files')}, 'manifest_hash':digest(package)},'GUI package lock differs')
        devices=p['cells'][0]['devices'];require(len(devices)==1,'Expected one MiM')
        dev=devices[0];binding=binding_for(tech,dev);values=parameter_values(binding,dev)
        require(binding['model']==f"sky130_fd_pr__cap_mim_m3_{row['plate']}" and dev['model_ref']['revision']==bridge.REVISION and dev['nets']=={'c0':'P','c1':'N'} and all(values[k]==v for k,v in dict(w=2,l=10,mf=1).items()),'GUI MiM binding differs')
        for field in ('schematic','reference'):
            f=Path(row[field]).resolve();require(f.is_relative_to(root) and f.is_file() and file_digest(f)==row['export_sha256'][field],'Missing or changed GUI export')
        verify_exports(Path(row['schematic']), Path(row['reference']), tech, row['plate'])
    # Recalculate inventories from actual files; the existing independent source reader
    # checks every source and rewritten include and all five selected mappings.
    manifest=inventory(root)
    staged=verify_models(root,dict(execution_root=root.as_posix(),simulation_package={'manifest_sha256':cur['manifest_sha256'],'revision':bridge.REVISION}),manifest)
    require(list(staged)==['tt','ll','hh','hl','lh'] and report['staged_sections']==list(staged),'Missing corner coverage')
    return dict(status='PASS_SOURCE_QT_AND_STAGING_ONLY',nonce=expected_nonce,current=cur,predecessor=prev,
                retained_assets=proof['retained_assets'],corners=list(staged),installed_acceptance=False,qualified=False)






if __name__ == '__main__':
    import argparse
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--root',required=True); ap.add_argument('--report-sha256',required=True)
    ap.add_argument('--nonce',required=True); ap.add_argument('--contract',required=True)
    ap.add_argument('--expected-sources',required=True,help='External JSON map of exact source file SHA-256 identities')
    a=ap.parse_args()
    print(json.dumps(read(a.root,a.report_sha256,a.nonce,Path(a.contract),bridge._json(Path(a.expected_sources).read_bytes())),indent=2))
