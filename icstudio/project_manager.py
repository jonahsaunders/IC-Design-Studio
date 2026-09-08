"""Project index and recoverable file deletion, independent of the desktop UI."""
from pathlib import Path
import json,os
from .model import atomic_write,load_project,now,uid,file_digest

class ProjectIndex:
    def __init__(self,root):
        self.root=Path(root);self.root.mkdir(parents=True,exist_ok=True);self.path=self.root/'projects.json'
    def entries(self):
        if not self.path.exists():return []
        value=json.loads(self.path.read_text())
        if not isinstance(value,list):raise ValueError('Invalid project index.')
        return value
    def remember(self,project,path):
        if not path:return
        path=str(Path(path).resolve());entries=[e for e in self.entries() if e['path']!=path]
        lock=project.get('pdk',{}).get('package_lock',{})
        entries.insert(0,{'path':path,'name':project['name'],'id':project['id'],'pdk':lock.get('id','No PDK'),'revision':lock.get('revision',''),'opened':now()})
        atomic_write(self.path,json.dumps(entries[:100],indent=2))
    def forget(self,path):
        path=str(Path(path).resolve());atomic_write(self.path,json.dumps([e for e in self.entries() if e['path']!=path],indent=2))
    def trash(self,path,expected_hash=None):
        path=Path(path).resolve()
        if path.suffix not in ('.icproj','.icstudio') or not path.is_file():raise ValueError('Select an existing Studio project file.')
        load_project(path)
        if expected_hash and file_digest(path)!=expected_hash:raise ValueError('Project changed on disk. Reopen it before deleting.')
        # Rename only the manifest/file beside the original; folder projects retain
        # all cell snapshots and every unrelated user file. Works across drives.
        target=path.with_name('.'+path.name+'.deleted-'+uid());record={'original':str(path),'trashed':str(target),'deleted':now()}
        atomic_write(self.root/('trash-'+target.name[-16:]+'.json'),json.dumps(record,indent=2))
        os.replace(path,target);self.forget(path);return record
    def deleted(self):
        return [json.loads(p.read_text()) for p in sorted(self.root.glob('trash-*.json')) if Path(json.loads(p.read_text())['trashed']).exists()]
    def restore(self,record):
        original=Path(record['original']);trashed=Path(record['trashed'])
        if original.exists():raise ValueError('A project now occupies the original path. Move it before restoring.')
        os.replace(trashed,original);project=load_project(original);self.remember(project,original);return original


def delete_cell(project,cid):
    if len(project['cells'])==1:raise ValueError('A project must retain at least one cell.')
    if project['top']==cid:raise ValueError('Set another cell as the project root before deleting this cell.')
    refs=[c['name'] for c in project['cells'] if any(d.get('cell')==cid for d in c['devices']+c.get('layout_instances',[]))]
    if refs:raise ValueError('Cell is used by: '+', '.join(refs)+'. Remove those instances first.')
    project['cells']=[c for c in project['cells'] if c['id']!=cid]
