"""Pinned, offline Xschem and GF180 simulation assets with explicit provenance."""
import hashlib,json,re,urllib.request,os
from pathlib import Path
from .model import atomic_write

ASSETS=Path(__file__).parent/'assets/exchange'


def manifest():return json.loads((ASSETS/'index.json').read_text())


def cache_root():
    base=Path(os.environ.get('LOCALAPPDATA') or os.environ.get('XDG_DATA_HOME') or Path.home()/'.local/share')
    return base/'ICDesignStudio/libraries'/manifest()['libraries']['gf180mcu']['revision']


def library_root(key):
    library=manifest()['libraries'][key]
    def healthy(root):return all((root/rel).is_file() and hashlib.sha256((root/rel).read_bytes()).hexdigest()==item['sha256'] for rel,item in library['files'].items())
    if healthy(ASSETS):return ASSETS
    if key=='gf180mcu':
        cache=cache_root()
        if not healthy(cache):repair_gf180()
        if healthy(cache):return cache
    raise ValueError('The included '+key+' library is missing or changed. Reinstall the application package.')


def prepare(path,libraries=(),locations=None):
    """Local/project libraries win. Standard installed assets are the fallback."""
    text=Path(path).read_text(encoding='utf-8');roots=list(libraries);mapped=dict(locations or {});standard=library_root('xschem')
    roots.extend([str(standard/'xschem'),str(standard/'xschem/devices')])
    selected=['xschem'];variant=None
    match=re.search(r'gf180mcu([ABCD])(?:[/\\]|\b)',text,re.I)
    gf_symbols={Path(rel).name for rel in manifest()['libraries']['gf180mcu']['files'] if rel.endswith('.sym')}
    from .xschem_project import records,properties
    components=[r for r in records(text) if r[0]=='C'];symbol_refs=[r[1] for r in components]
    if match or any(Path(ref).name in gf_symbols for ref in symbol_refs):
        variant='gf180mcu'+match[1].upper() if match else 'gf180mcu';gf=library_root('gf180mcu');selected.append('gf180mcu');roots.extend([str(gf/'gf180mcu'),str(gf/'gf180mcu/symbols'),str(gf/'gf180mcu/models')])
        values='\n'.join(properties(r[6]).get('value','') for r in components)
        refs=re.findall(r'(?im)^\s*\.(?:include|inc|lib)\s+("[^"\n]+"|\'[^\'\n]+\'|\S+)',values)
        for raw in refs:
            ref=raw.strip('"\'')
            if not re.search(r'gf180mcu',ref,re.I):continue
            if ref in mapped:continue
            name=ref.replace('\\','/').rsplit('/',1)[-1]
            # Prefer an explicitly supplied installation of the requested variant.
            candidates=[Path(ref)]
            for folder in libraries:
                root=Path(folder)
                candidates.extend([root/variant/'libs.tech/ngspice'/name,root/'libs.tech/ngspice'/name,root/name])
            found=next((p for p in candidates if p.is_file()),None)
            if found:mapped[ref]=str(found.resolve());continue
            target=gf/'gf180mcu/models'/name.replace('.ngspice','.spice')
            if target.is_file():mapped[ref]=str(target.resolve())
        for ref in symbol_refs:
            if ref in mapped or Path(ref).name not in gf_symbols:continue
            if any((root/ref).is_file() for root in [Path(path).parent]+[Path(r) for r in libraries]):continue
            if 'gf180mcu' in ref.lower() or ref.startswith('symbols/'):mapped[ref]=str((gf/'gf180mcu/symbols'/Path(ref).name).resolve())
    data=manifest();lock={key:{'revision':data['libraries'][key]['revision'],'source':data['libraries'][key].get('repository',data['libraries'][key].get('source'))} for key in selected}
    return list(dict.fromkeys(roots)),mapped,{'libraries':lock,'variant':variant,'scope':'Schematic and simulation assets'}


def repair_gf180(progress=lambda *_:None):
    """Restore pinned public model/symbol bytes, never select a moving latest ref."""
    library=manifest()['libraries']['gf180mcu'];items=list(library['files'].items())
    for i,(rel,item) in enumerate(items):
        path=cache_root()/rel
        if path.is_file() and hashlib.sha256(path.read_bytes()).hexdigest()==item['sha256']:continue
        with urllib.request.urlopen(library['raw_base']+item['source'],timeout=30) as response:data=response.read(10_000_001)
        if hashlib.sha256(data).hexdigest()!=item['sha256']:raise ValueError('Downloaded library does not match its pinned revision: '+rel)
        atomic_write(path,data);progress((i+1)/len(items),'Restored '+path.name)
