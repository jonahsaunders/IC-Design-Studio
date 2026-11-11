"""Prepare the original 20 PMOS cases for Studio's managed WSL native view.
No simulation runs. Explicit XDUT/source text is not graphical parameter support.
"""
from pathlib import Path
import argparse,json,sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from scripts.read_ihp_pmos_measured_v3 import verify,require,sha
from scripts.prepare_ihp_wsl_research_payload import unlinked,encoded

LIB='.lib "../pdk/libs.tech/ngspice/models/cornerMOSlv.lib" mos_tt'

def split_deck(text):
 lines=text.splitlines();inside=False;kept=[]
 for line in lines:
  if line=='.control':require(not inside,'Nested controls');inside=True;continue
  if line=='.endc':require(inside,'Unmatched controls');inside=False;continue
  if inside:
   require(line in ('pre_osdi runtime/psp103.osdi','pre_osdi runtime/psp103_nqs.osdi'),'Unexpected control');continue
  kept.append(line)
 require(not inside,'Unclosed control')
 require(sum(x.startswith('.lib ') for x in kept)==1,'Library count')
 require('.lib "pdk/libs.tech/ngspice/models/cornerMOSlv.lib" mos_tt' in kept,'Original library')
 require('.dc VD 0 -1.35 -0.05' in kept and '.temp 27' in kept,'Original sweep')
 require('.option reltol=1e-8 abstol=1e-16 vntol=1e-13' in kept and '.option gminsteps=0 srcsteps=0' in kept,'Original accuracy')
 require(sum(x.startswith('XDUT ') for x in kept)==1,'DUT count')
 # Import only independent voltage sources; retain exact explicit device/options.
 sources=[x for x in kept if x.startswith(('VD ','VG ','VS ','VB '))]
 require(len(sources)==4,'Source count')
 statements=[LIB]+[x for x in kept if x.startswith(('.option ','XDUT '))]
 return sources,statements

def prepare(evidence,output):
 root,manifest=verify(evidence);out=unlinked(output);require(not out.exists(),'Fresh project output')
 from scripts.qualify_standard_mos import load_technology
 from icstudio.spice_import import import_spice
 from icstudio.model import save_project
 tech,identity=load_technology('ihp-sg13g2')
 run=root/'measured-v3/attempt-1';r=json.loads((run/'run.json').read_text())
 out.mkdir(parents=True);records=[]
 for record in r['runs']:
  key=f"{record['route']}-{record['gate_index']}";original=run/'runs'/key/'input.cir'
  sources,statements=split_deck(original.read_text())
  p,report=import_spice(out/'not-read.cir',tech,text='* Research imported sources\n'+'\n'.join(sources)+'\n.end\n')
  p['name']='RESEARCH WSL '+key;p['spice']={'version':1,'assets':{}}
  p['cells'][0]['spice_statements']=statements;p.pop('simulation_runtime',None)
  p['analysis'].update(type='dc',source='VD',dc_start='0',dc_stop='-1.35',dc_step='-0.05',temperature=27,timeout=90,dc_startup=False)
  target=out/(key+'.icproj');save_project(p,target)
  records.append({'case':key,'project':target.name,'sha256':sha(target),'original_deck_sha256':sha(original),'original_sources':sources,'expected_statements':statements})
 require(len(records)==20 and len({x['case'] for x in records})==20,'Original selection')
 contract={'schema':1,'scope':'WINDOWS_STUDIO_MANAGED_WSL_RESEARCH','qualified':False,'deadline_seconds':90,
  'evidence_manifest_sha256':sha(root/'MANIFEST.json'),'pdk_identity':identity,'cases':records,
  'representation_changes':['Only native title, source rendering adds explicit DC/AC0, analysis regenerates .temp/.dc, output selection may add node voltages.','PDK library resolves ../pdk from physical_backend native work/output, not a Windows absolute path.','Managed preload stages all six exact libraries; historical research loaded two. This difference requires reviewed explicit runtime approval before execution.'],
  'pre_native_review_required':True}
 (out/'projects.json').write_bytes(encoded(contract));return contract

def main():
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('--evidence',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args();print(json.dumps(prepare(a.evidence,a.output),indent=2))
if __name__=='__main__':main()
