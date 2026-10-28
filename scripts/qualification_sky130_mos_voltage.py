"""Qualification-only source-defined SKY130 MOS voltage screen.

This library classifies model-source validity; it does not restrict simulator
execution, assert ratings, or qualify a continuous operating envelope.
"""
from pathlib import Path
import hashlib,json,math
from scripts.qualification_sky130_mos_voltage_core import VoltageScreen
REPO=Path(__file__).resolve().parents[1]
HERE=REPO/'docs/qualification/sky130-mos-voltage-v1'
CATALOG_LOCK_SHA='4731c93a5acc43ea014cc383e1aff4e707dd56e07f2494c8bd8b2105fefdecbc'
PACKAGE_SHA='840f7af802b07346650c50a5967e532a4cb1716623cf0c9d6fd6c58eaf35fcbe'
DEFAULT_PACKAGE=REPO/'icstudio/assets/pdks/sky130A'
def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def safe_file(root,relative):
 p=(root/relative).resolve()
 if not p.is_relative_to(root.resolve()) or p==root.resolve():raise ValueError('model resource escapes package')
 return p
class QualificationVoltageContract:
 def __init__(self,package_root=DEFAULT_PACKAGE,contract_root=HERE):
  self.root=Path(contract_root);self.package_root=Path(package_root);lock=self.root/'catalog-source-lock.json'
  if sha(lock)!=CATALOG_LOCK_SHA:raise ValueError('catalog-source contract changed')
  self.lock=json.loads(lock.read_bytes());self.underlying=VoltageScreen(self.root);manifest=self.package_root/'package.json'
  if sha(manifest)!=PACKAGE_SHA:raise ValueError('current package identity changed')
  self.package=json.loads(manifest.read_bytes());self.aliases={};catalog=self.package['technology']['simulation']['catalog'];files=self.package['files']
  if self.package['revision']!=self.lock['package_revision'] or len(self.lock['models'])!=17:raise ValueError('package/contract model revision differs')
  for model,identity in self.lock['models'].items():
   if model not in self.underlying.rows or self.underlying.rows[model]['model_voltage_limits_v'] is None:raise ValueError('unsupported model in catalog lock')
   observed={key for key,b in catalog.items() if b.get('model')==model}
   if observed!=set(identity['aliases']):raise ValueError('catalog alias inventory changed')
   for key,alias in identity['aliases'].items():
    b=catalog[key];rel=alias['model_source'];symbol=alias['symbol_source']
    if b.get('model')!=model or b.get('model_source')!=rel or b.get('pin_order')!=alias['pin_order'] or b.get('kind')!=alias['kind'] or b.get('source')!=symbol:raise ValueError('catalog binding changed: '+key)
    if files.get(rel)!=alias['model_source_sha256'] or files.get(symbol)!=alias['symbol_sha256']:raise ValueError('catalog manifest changed')
    if sha(safe_file(self.package_root,rel))!=alias['model_source_sha256'] or sha(safe_file(self.package_root,symbol))!=alias['symbol_sha256']:raise ValueError('catalog source changed: '+key)
    if key in self.aliases:raise ValueError('ambiguous catalog key')
    self.aliases[key]=model
   for path,digest in identity['package_model_files'].items():
    if files.get(path)!=digest or sha(safe_file(self.package_root,path))!=digest:raise ValueError('model source changed: '+path)
  if len(self.aliases)!=40:raise ValueError('catalog coverage differs')
 def model_inventory(self):
  result=[]
  for model,identity in sorted(self.lock['models'].items()):
   row=self.underlying.rows[model];facts=[]
   for axis,(lower,upper) in row['model_voltage_limits_v'].items():
    facts.append({'quantity':axis.upper(),'relation':{'vds':'V(d)-V(s)','vgs':'V(g)-V(s)','vbs':'V(b)-V(s)'}[axis],'units':'V','lower':lower,'upper':upper,'lower_inclusive':True,'upper_inclusive':True,'conditions':'ordinary or conducting case' if axis=='vds' and row['off_state_vds_v'] else 'all stated model cases','semantic_kind':'model_validity','source':row['source_anchor']})
   if row['off_state_vds_v']:
    lower,upper=row['off_state_vds_v'];facts.append({'quantity':'VDS','relation':'V(d)-V(s)','units':'V','lower':lower,'upper':upper,'lower_inclusive':True,'upper_inclusive':True,'conditions':'V(g)-V(s) == 0 exactly; source additionally requires separate SOA','semantic_kind':'model_validity','source':row['source_anchor']})
   result.append({'source_model':model,'catalog_status':identity['catalog_status'],'catalog_bindings':identity['aliases'],'package_revision':self.lock['package_revision'],'model_source_files':identity['package_model_files'],'published_facts':facts,'unresolved':{'absolute_ratings':{'value':None,'reason':'No model-specific absolute rating established by reviewed source.'},'rated_operating_voltage':{'value':None,'reason':'Model validity is not a rated operating limit.'},'temperature_validity':{'value':None,'reason':'Nominal TNOM and sampled temperatures do not establish a validity range.'},'soa':{'value':None,'reason':'Separate SOA required' if row['soa_source_required'] else 'Not established by this voltage screen.'},'pcell_geometry':{'value':None,'reason':'PCell/generator constraints are separate and not assessed here.'},'fifth_terminal':{'value':None,'reason':'Separate substrate bias has no documented bound in this source.'} if model.endswith('nfet_20v0_iso') else None},'evidence_references':{'historical_native_bias':identity['historical_native_bias']},'qualified':False})
  return result
 def screen(self,point):
  if not isinstance(point,dict):raise ValueError('expected point object')
  ids=set(point)&{'model','catalog_key'}
  if len(ids)!=1 or set(point)!=ids|{'vds','vgs','vbs','temperature_c'}:raise ValueError('require exactly one identifier and vds/vgs/vbs/temperature_c')
  field=next(iter(ids));identifier=point[field]
  if not isinstance(identifier,str):raise ValueError('identifier must be text')
  if field=='catalog_key':
   if identifier not in self.aliases:raise ValueError('unreviewed or unavailable catalog key')
   model=self.aliases[identifier];binding=self.lock['models'][model]['aliases'][identifier]
  else:
   model=identifier;binding=None
   if model not in self.lock['models']:raise ValueError('unreviewed or unresolved exact model')
  request={k:point[k] for k in ('vds','vgs','vbs','temperature_c')};request['model']=model
  result=self.underlying.check(request);identity=self.lock['models'][model]
  result.update(identifier_kind=field,requested_identifier=identifier,catalog_binding=binding,package_revision=self.lock['package_revision'],package_manifest_sha256=PACKAGE_SHA,catalog_source_lock_sha256=CATALOG_LOCK_SHA,package_model_files=identity['package_model_files'],catalog_status=identity['catalog_status'],historical_native_bias=identity['historical_native_bias'],point_was_natively_exercised='NOT_ESTABLISHED',current_package_native_coverage='NOT_ESTABLISHED',absolute_maximum_ratings='NOT_ESTABLISHED',pcell_geometry_bounds='NOT_ASSESSED',validity_vs_ratings='Published SPICE model-validity limits only; not absolute maximum ratings, safe operating area, PCell geometry or full qualification.',simulator_restriction=False)
  return result

