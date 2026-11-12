"""Consumer gate: prepared result alone never establishes clean preparation."""
from pathlib import Path
import argparse,json,sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from scripts.prepare_ihp_wsl_research_payload import unlinked,encoded,file_sha
from scripts.read_ihp_pmos_measured_v3 import require

def check_records(result,completion):
 require(result['status']=='PREPARED_PENDING_WINDOWS_NATIVE_REVIEW' and result['qualified'] is False and result['pmos_executed'] is False,'Preparation result not successful research-only')
 require(completion['failure'] is None and completion['cleanup_failed'] is False and completion['pmos_executed'] is False,'Preparation finally/cleanup failed')
 require(completion['cleanup']['collector']['status'] in ('removed','absent'),'Collector cleanup incomplete')
 require(completion['cleanup']['export_container']['status']=='removed','Export container cleanup incomplete')
 require(completion['source_policy_sha256']==result['policy_sha256'],'Preparation policy differs')
 return True

def check(root):
 root=unlinked(root);r=json.loads((root/'result.json').read_text());c=json.loads((root/'completion.json').read_text());check_records(r,c)
 require(file_sha(root/'experimental-payload/manifest.json')==r['payload_manifest_sha256'],'Payload manifest changed')
 require(file_sha(root/'host-contract.json')==r['host_contract_sha256'],'Host contract changed')
 manifest=json.loads((root/'experimental-payload/manifest.json').read_text());host=json.loads((root/'host-contract.json').read_text())
 require(manifest['archive']=='runtime.tar.gz' and type(manifest['bytes']) is int and manifest['bytes']>0,'Payload archive declaration')
 archive=unlinked(root/'experimental-payload/runtime.tar.gz')
 require(archive.is_file() and archive.stat().st_size==manifest['bytes'] and file_sha(archive)==manifest['sha256'],'Payload archive missing/changed')
 require(host['base_archive_sha256']==r['base_archive_sha256'] and manifest['experimental_research']['base_archive_sha256']==r['base_archive_sha256'],'Base identity join')
 require(manifest['experimental_research']['host_contract_sha256']==r['host_contract_sha256'],'Host policy identity join')
 return {'status':'CLEAN_BUILD_PREPARATION_ONLY','native_authorized':False,'qualified':False,'bindings':{n:file_sha(root/n) for n in ('result.json','completion.json','host-contract.json','experimental-payload/manifest.json','experimental-payload/runtime.tar.gz')}}
def main():
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('--root',type=Path,required=True);a=p.parse_args();r=check(a.root)
 out=unlinked(a.root/'prepared-validation.json');require(not out.exists(),'Fresh validation output')
 with out.open('xb') as f:f.write(encoded(r))
 print(json.dumps(r))
if __name__=='__main__':main()
