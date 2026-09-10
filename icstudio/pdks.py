"""Local, content-verified PDK revisions; never imply foundry qualification."""
from __future__ import annotations
import json,shutil,re,os
from pathlib import Path
from .model import clone,digest,file_digest,atomic_write,example,validate,uid

class PDKRegistry:
    def __init__(self,root): self.root=Path(root);self.root.mkdir(parents=True,exist_ok=True)
    def install(self,manifest_path):
        src=Path(manifest_path).resolve();base=src.parent;manifest=json.loads(src.read_text(encoding='utf-8'))
        # Managed packages must use their installed copies, even when exported
        # from a registration that referred to a developer's original folder.
        manifest.pop('source_root',None)
        for key in ('id','revision'):
            if not re.fullmatch(r'[A-Za-z0-9_-][A-Za-z0-9_.-]{0,100}',manifest.get(key,'')):raise ValueError('Invalid PDK '+key)
        if manifest.get('schema')!=1:raise ValueError('Unsupported technology package schema.')
        p=example('empty');p['pdk']=manifest['technology'];validate(p)
        files=manifest.get('files',{})
        if not files:raise ValueError('A technology package needs checksummed assets.')
        for rel,sha in files.items():
            path=(base/rel).resolve()
            if Path(rel).is_absolute() or not path.is_relative_to(base) or path.is_symlink() or not path.is_file():raise ValueError('Unsafe or missing PDK asset: '+rel)
            if file_digest(path)!=sha:raise ValueError('PDK asset checksum mismatch: '+rel)
        key=manifest['id']+'@'+manifest['revision'];dest=self.root/key
        if dest.exists():
            if json.loads((dest/'package.json').read_text())!=manifest:raise ValueError('This revision is already installed with different contents. Use a new revision.')
            self.verify(key);return key
        stage=self.root/('_install_'+uid());stage.mkdir()
        try:
            for rel in files:
                target=stage/rel;target.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(base/rel,target)
                if file_digest(target)!=files[rel]:raise ValueError('PDK asset changed during installation: '+rel)
            atomic_write(stage/'package.json',json.dumps(manifest,indent=2));os.replace(stage,dest)
        finally:
            if stage.exists():shutil.rmtree(stage)
        return key
    def register_local(self,path,progress=lambda message:None):
        from .pdk_import import scan_local
        manifest=scan_local(path,progress);key=manifest['id']+'@'+manifest['revision'];dest=self.root/key
        if dest.exists():
            previous=self.manifest(key)
            if previous.get('files')!=manifest['files'] or previous.get('technology')!=manifest['technology']:raise ValueError('Catalog revision conflicts with installed metadata.')
            if previous.get('source_root')!=manifest['source_root']:atomic_write(dest/'package.json',json.dumps(manifest,indent=2))
            self.verify(key);return key
        stage=self.root/('_install_'+uid());stage.mkdir()
        try:
            atomic_write(stage/'package.json',json.dumps(manifest,indent=2));os.replace(stage,dest)
        finally:
            if stage.exists():shutil.rmtree(stage)
        return key
    def entries(self):
        entries=[]
        for p in sorted(self.root.glob('*/package.json')):
            if p.parent.name.startswith(('_install_','_removed_')):continue
            try:entries.append(json.loads(p.read_text()))
            except (ValueError,OSError):entries.append({'id':p.parent.name,'revision':'unreadable','error':'Cannot read registration metadata.'})
        return entries
    def manifest(self,key):
        if not re.fullmatch(r'[A-Za-z0-9_-][A-Za-z0-9_.-]*@[A-Za-z0-9_-][A-Za-z0-9_.-]*',key):raise ValueError('Invalid package key.')
        base=(self.root/key).resolve()
        if not base.is_relative_to(self.root.resolve()):raise ValueError('Invalid package location.')
        return json.loads((base/'package.json').read_text())
    def verify(self,key):
        manifest=self.manifest(key);base=Path(manifest.get('source_root',self.root/key)).resolve()
        for rel,sha in manifest['files'].items():
            path=(base/rel).resolve()
            if not path.is_relative_to(base) or not path.is_file() or file_digest(path)!=sha:raise ValueError('Installed PDK asset missing or changed: '+rel+'. Restore the original folder or register a new revision.')
        return manifest
    def technology(self,key):
        manifest=self.verify(key);tech=clone(manifest['technology']);tech['package_root']=str(Path(manifest.get('source_root',self.root/key)).resolve());tech['package_lock']={'id':manifest['id'],'revision':manifest['revision'],'manifest_hash':digest(manifest),'files':manifest['files']};return tech
    def relocate(self,key,folder):
        manifest=self.manifest(key);root=Path(folder).resolve()
        for rel,sha in manifest['files'].items():
            path=(root/rel).resolve()
            if not path.is_relative_to(root) or not path.is_file() or file_digest(path)!=sha:raise ValueError('Folder does not match registered revision: '+rel)
        manifest['source_root']=str(root)
        atomic_write(self.root/key/'package.json',json.dumps(manifest,indent=2))
        return self.technology(key)
    def remove(self,key):
        self.manifest(key)
        # Retain every byte in a recoverable local archive. External PDK folders
        # and projects already linked to them are never deleted here.
        dest=self.root/('_removed_'+uid());os.replace(self.root/key,dest);return dest

def model_lines(technology,corner='nominal'):
    lock=technology.get('package_lock');root=Path(technology.get('package_root','')).resolve();lines=[]
    binding=technology.get('simulation',{})
    if not binding:return []
    if not lock:raise ValueError('Install this PDK package before using its models.')
    for rel,sha in lock['files'].items():
        path=(root/rel).resolve()
        if not path.is_relative_to(root) or not path.is_file() or file_digest(path)!=sha:raise ValueError('Locked PDK asset is missing or changed: '+rel)
    for item in binding.get('includes',[]):
        rel=item['path']
        if rel not in lock['files']:raise ValueError('Model include is absent from the dependency lock.')
        path=(root/rel).as_posix()
        if any(c in path for c in ('"','\n','\r')):raise ValueError('Unsupported model path.')
        section=item.get('sections',{}).get(corner,item.get('section'))
        if item.get('sections') and corner not in item['sections']:raise ValueError('Missing model section for corner '+corner)
        if section:
            if not re.fullmatch('[A-Za-z0-9_]+',section):raise ValueError('Invalid model section.')
            lines.append(f'.lib "{path}" {section}')
        else:lines.append(f'.include "{path}"')
    return lines


def stage_model_deck(technology, text, directory):
    """Make catalog-backed runs independent of profile paths and PDK locations.

    ngspice 42 splits even quoted .lib filenames at spaces. Keep a checksummed
    include closure under simple run-relative names, including self references.
    """
    import hashlib
    lock = technology.get('package_lock')
    if not lock or not technology.get('simulation'):
        return text
    source = Path(technology['package_root']).resolve()
    output = Path(directory).resolve()
    files = {(source / rel).resolve(): (rel, sha) for rel, sha in lock['files'].items()}
    staged = {}
    pattern = re.compile(r'(?im)^[^\S\n]*(\.include|\.inc|\.lib)[^\S\n]+("[^"\n]+"|\'[^\'\n]+\'|[^\s]+)([^\n]*)')

    def rewrite(contents, parent=None):
        def one(match):
            if match[1].lower() == '.lib' and not match[3].strip():
                return match[0]  # A section definition, not a file reference.
            reference = match[2].strip('"\'')
            path = ((parent.parent if parent else output) / reference).resolve()
            if path not in files:
                if parent is not None:
                    raise ValueError('PDK model dependency is absent from its lock: ' + reference)
                return match[0]
            return match[1] + ' ' + stage(path) + match[3]
        return pattern.sub(one, contents)

    def stage(path):
        if path in staged:
            return staged[path]
        relative, expected = files[path]
        if not path.is_relative_to(source) or not path.is_file():
            raise ValueError('Unsafe or missing locked PDK model: ' + relative)
        data = path.read_bytes()
        if hashlib.sha256(data).hexdigest() != expected:
            raise ValueError('Locked PDK model changed while preparing the run: ' + relative)
        name = 'pdk-models/' + hashlib.sha256((relative + '\0' + expected).encode()).hexdigest()[:24] + '.spice'
        staged[path] = name
        atomic_write(output / name, rewrite(data.decode('utf-8'), path))
        return name

    result = rewrite(text)
    atomic_write(output / 'pdk-model-files.json', json.dumps({name: files[path][0] for path, name in staged.items()}, indent=2))
    return result
