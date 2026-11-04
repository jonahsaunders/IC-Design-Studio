"""Independent reader for a candidate frozen pw2dn GUI lifecycle report."""
import hashlib,json,os,re
from pathlib import Path
from icstudio.model import file_digest,load_project
from icstudio.interchange import spice
from icstudio.catalog import parameter_values
from scripts.verify_frozen_mim import unlinked

REV='47dbd4fe43bfa7e4';OLD='5dda725c94efe3c2'
KEY='sky130_fd_pr/diode__sky130_fd_pr__model__parasitic__rf_diode_pw2dn.sym'
MODEL='sky130_fd_pr__model__parasitic__rf_diode_pw2dn'
REL='libs.tech/ngspice/icstudio-rf-pw2dn/'+MODEL+'.model.spice'
def require(value,message):
    if not value:raise ValueError(message)

def inventory(root):
    root=unlinked(root).resolve();files={}
    for folder,dirs,names in os.walk(root,followlinks=False):
        for name in dirs:unlinked(Path(folder)/name)
        for name in names:
            path=unlinked(Path(folder)/name);require(path.is_file(),'Unexpected producer file.')
            files[path.relative_to(root).as_posix()]=file_digest(path)
    return files

def package(root,sha):
    root=unlinked(root).resolve();path=unlinked(root/'package.json')
    require(file_digest(path)==sha,'Package manifest identity differs.')
    data=json.loads(path.read_bytes())
    for name,expected in data['files'].items():
        asset=unlinked(root/name);resolved=asset.resolve()
        require(resolved.is_relative_to(root) and asset.is_file() and file_digest(asset)==expected,'Package asset differs: '+name)
    return data

def staging(stage,root,locked,export):
    mapping=json.loads((stage/'pdk-model-files.json').read_bytes());reverse={v:k for k,v in mapping.items()}
    require(len(reverse)==len(mapping) and mapping,'Duplicate or missing staged sources.')
    pattern=re.compile(r'(?im)^[^\S\n]*(\.include|\.inc|\.lib)[^\S\n]+("[^"\n]+"|\'[^\'\n]+\'|[^\s]+)([^\n]*)')
    root=Path(root).resolve()
    edges={}
    def rewrite(text,parent):
        dependencies=set()
        def replacement(match):
            if match[1].lower()=='.lib' and not match[3].strip():return match[0]
            ref=match[2].strip('"\'');absolute=(parent/ref).resolve()
            if not absolute.is_relative_to(root):
                require(parent==stage,'Staged include escaped locked package.')
                return match[0]
            relative=absolute.relative_to(root).as_posix();require(relative in reverse,'Missing staged dependency.')
            dependencies.add(reverse[relative])
            return match[1]+' '+reverse[relative]+match[3]
        return pattern.sub(replacement,text),dependencies
    for name,source in mapping.items():
        require(source in locked,'Unbound staged source.')
        desired='pdk-models/'+hashlib.sha256((source+'\0'+locked[source]).encode()).hexdigest()[:24]+'.spice'
        require(name==desired,'Wrong staged filename.')
        original=unlinked(root/source);require(file_digest(original)==locked[source],'Changed staged source.')
        lines=[]
        for line in original.read_bytes().splitlines(keepends=True):
            try:lines.append(line.decode('utf-8'))
            except UnicodeDecodeError:
                require(line.lstrip().startswith(b'*'),'Non-UTF8 model statement.');lines.append(line.decode('latin-1'))
        normalized,edges[name]=rewrite(''.join(lines),original.parent)
        require(unlinked(stage/name).read_text(encoding='utf-8')==normalized,'Changed staged model: '+source)
    top,reachable=rewrite(export,stage)
    require(unlinked(stage/'schematic.spice').read_text(encoding='utf-8')==top,'Staged top-level deck differs.')
    pending=list(reachable)
    while pending:
        for dependency in edges[pending.pop()]:
            if dependency not in reachable:reachable.add(dependency);pending.append(dependency)
    require(reachable==set(mapping),'Staged mapping differs from reachable dependency graph.')
    actual={p.relative_to(stage).as_posix() for p in (stage/'pdk-models').iterdir()}
    require(actual==set(mapping) and all(unlinked(stage/name).is_file() for name in actual),'Staged file inventory differs.')
    require({p.name for p in stage.iterdir()}=={'pdk-models','pdk-model-files.json','schematic.spice'},'Unexpected staged output.')

def verify(output,expected):
    output=unlinked(output).resolve();report=json.loads(unlinked(output/'report.json').read_bytes())
    require(expected['schema']=='pw2dn-frozen-gui-input-v1' and expected['scope']=='frozen-gui-lifecycle-only','Unexpected external acceptance scope.')
    require(re.fullmatch('[0-9a-f]{32}',expected['execution_id']) is not None and re.fullmatch('[0-9a-f]{40}',expected['commit']) is not None,'Invalid execution or commit identity.')
    executable=unlinked(expected['executable']).resolve();engine=unlinked(expected['engine']).resolve()
    require(file_digest(executable)==expected['executable_sha256'] and file_digest(engine)==expected['engine_sha256'],'External binary identity differs.')
    resource=executable.parent/'_internal';require(engine.parent==resource/'icstudio/assets/runtime/ngspice','External engine is not shipped.')
    require(Path(expected['bundled_package']).resolve()==resource/'icstudio/assets/pdks/sky130A','External bundle path differs.')
    candidate=package(expected['bundled_package'],expected['candidate_manifest_sha256'])
    require(candidate['files']==expected['candidate_files'] and candidate['technology']==expected['candidate_technology'],'External candidate data differs.')
    require(file_digest(unlinked(resource/'icstudio/assets/pdks/collection.json'))==expected['collection_sha256'],'External collection differs.')
    runtime=unlinked(engine.parent/'runtime-manifest.json');require(file_digest(runtime)==expected['runtime_manifest_sha256'],'External runtime identity differs.')
    require(json.loads(runtime.read_bytes())['files']==expected['runtime_files'],'External runtime files differ.')
    for name,sha in expected['runtime_files'].items():require(file_digest(unlinked(engine.parent/name))==sha,'External runtime asset differs: '+name)
    from scripts.installed_mim_inputs import candidate_sources
    candidate_sources(expected['candidate_sources'],expected['commit'])
    require(inventory(output)==expected['producer_inventory'],'Producer output inventory changed.')
    require(report['status']=='PASS_GUI_LIFECYCLE' and report['frozen'] is True,'Frozen GUI lifecycle incomplete.')
    require(report['build']['frozen'] is True and report['build']['dirty'] is False and report['build']['commit']==expected['commit'],'Frozen build identity differs.')
    prelaunch=json.loads((output/'prelaunch.json').read_bytes())
    for key in ('execution_id','frozen','build','executable_sha256','candidate_manifest_sha256','collection_sha256'):
        require(prelaunch[key]==report[key],'Prelaunch identity differs: '+key)
    for k in ('execution_id','executable_sha256','candidate_manifest_sha256','collection_sha256'):
        require(report[k]==expected[k],'Execution identity differs: '+k)
    require(report['hub_selected']=='sky130A@'+REV,'Wrong bundled Hub selection.')
    require(Path(report['hub_source_path']).resolve()==Path(expected['bundled_package']).resolve(),'Wrong bundled Hub source.')
    require(report['registry']['old_key']=='sky130A@'+OLD and report['registry']['current_key']=='sky130A@'+REV,'Registry identities differ.')
    projects={}
    for which in ('old_before','old_after','new'):
        row=report[which];folder=output/which.replace('_','-') if which!='new' else output/'new'
        path=folder/'project.icproj';deck=folder/'schematic.spice'
        require(Path(row['project']).resolve()==path and Path(row['schematic']).resolve()==deck,'Unexpected evidence path.')
        require(file_digest(path)==row['project_sha256'],'Saved project changed.')
        project=load_project(path);require(project['pdk']['package_lock']==row['package_lock'],'Saved lock differs.')
        require(deck.read_text(encoding='utf-8')==spice(project,project['top'],project['analysis']),'Export differs from independently rebuilt project.')
        projects[which]=project
    before,after,new=projects['old_before'],projects['old_after'],projects['new']
    require(before==after and before['pdk']['revision']==OLD,'Prior project migrated or changed.')
    def single_cell(project):
        require(len(project['cells'])==1,'Unexpected project cells.');cell=project['cells'][0]
        require(cell['id']==project['top'] and len(cell['devices'])==1 and all(not cell.get(k) for k in ('ports','shapes','wires','junctions','labels','instances')),'Unexpected fixture circuit contents.')
        return cell['devices'][0]
    olddev=single_cell(before);oldkey=KEY.replace('pw2dn','ps2nw')
    require(olddev['model_ref']=={'pdk':'sky130A','revision':OLD,'device':oldkey} and olddev['nets']=={'d0':'OA','d1':'OK'} and parameter_values(before['pdk']['simulation']['catalog'][oldkey],olddev)=={'w':3,'l':2,'area':6,'perim':10},'Prior populated RF specimen differs.')
    require(new['pdk']['revision']==REV and new['pdk']['package_lock']['files']==expected['candidate_files'],'Candidate project lock differs.')
    require({k:v for k,v in before['pdk'].items() if k not in ('package_root','package_lock')}==expected['predecessor_technology'] and before['pdk']['package_lock']['files']==expected['predecessor_files'],'Prior project technology differs.')
    require({k:v for k,v in new['pdk'].items() if k not in ('package_root','package_lock')}==expected['candidate_technology'],'Candidate project technology differs.')
    old_root=unlinked(before['pdk']['package_root']).resolve()
    require(old_root.is_relative_to(output/'profile') and old_root.name=='sky130A@'+OLD,'Predecessor registry escaped GUI profile.')
    for name,sha in expected['predecessor_files'].items():
        asset=unlinked(old_root/name).resolve()
        require(asset.is_relative_to(old_root) and file_digest(asset)==sha,'Changed predecessor registry asset: '+name)
    registry_root=unlinked(new['pdk']['package_root']).resolve()
    require(registry_root.is_relative_to(output/'profile') and registry_root.name=='sky130A@'+REV,'Candidate registry escaped isolated GUI profile.')
    registry_manifest=json.loads(unlinked(registry_root/'package.json').read_bytes())
    require(registry_manifest['files']==expected['candidate_files'] and registry_manifest['technology']==expected['candidate_technology'],'Registry technology differs.')
    for name,sha in expected['candidate_files'].items():
        asset=unlinked(registry_root/name).resolve()
        require(asset.is_relative_to(registry_root) and file_digest(asset)==sha,'Changed registry asset: '+name)
    dev=single_cell(new);binding=new['pdk']['simulation']['catalog'][KEY]
    require(dev['model_ref']=={'pdk':'sky130A','revision':REV,'device':KEY} and binding['model']==MODEL and binding['prefix']=='X' and binding['pin_order']==['d0','d1'],'Selected model binding differs.')
    require(dev['nets']=={'d0':'A','d1':'K'} and parameter_values(binding,dev)=={'w':4,'l':2,'area':8,'perim':12},'Selected model or geometry differs.')
    require('X_D1 A K '+MODEL+' area=8 perim=12' in (output/'new/schematic.spice').read_text(encoding='utf-8'),'Export model line differs.')
    stage=output/'staged';mapping=json.loads((stage/'pdk-model-files.json').read_bytes())
    staging(stage,new['pdk']['package_root'],expected['candidate_files'],(output/'new/schematic.spice').read_text(encoding='utf-8'))
    matches=[stage/name for name,source in mapping.items() if source==REL]
    require(len(matches)==1 and file_digest(matches[0])==expected['candidate_files'][REL] and report['staged_derivative_sha256']==expected['candidate_files'][REL],'Staged model differs.')
    require(file_digest(output/'prelaunch.json')==expected['prelaunch_sha256'],'Prelaunch receipt changed.')
    return {'status':'PASS_FROZEN_GUI_LIFECYCLE_ONLY','report_sha256':file_digest(output/'report.json'),
            'project_sha256':file_digest(output/'new/project.icproj'),'spice_sha256':file_digest(output/'new/schematic.spice')}
