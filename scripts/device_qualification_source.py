"""Reconstruct exact pre-promotion device packages without rewriting projects.

The promoted packages add files and metadata; every earlier asset remains intact.
Only the four old manifests are duplicated. Existing qualification recipes keep
their original input identities and do not silently relabel historical evidence.
"""
from contextlib import contextmanager
from functools import wraps
import json, shutil, tempfile
from pathlib import Path
from icstudio.model import file_digest
from scripts.prepare_alternate_models import BASE as ALTERNATE_BASE
from scripts.alternate_model_source import PROMOTED as ALTERNATE_DEFAULTS
from scripts.sky130_li_source import PROMOTED as LI_DEFAULT,REVISION as LI_REVISION
from scripts.sky130_mim_source import PROMOTED as MIM_DEFAULT,REVISION as MIM_REVISION
from scripts.ihp_tap_source import PROMOTED as TAP_DEFAULT,REVISION as TAP_REVISION,BASE as TAP_BASE
from scripts.ihp_npn_source import PROMOTED as NPN_DEFAULT,REVISION as NPN_REVISION
from scripts.gf180_hv_source import PROMOTED as HV_DEFAULTS,REVISIONS as HV_REVISIONS
from scripts.sky130_rf_source import PROMOTED as RF_DEFAULT,REVISION as RF_REVISION
ROOT=Path(__file__).resolve().parents[1]
RETAINED=ROOT/'icstudio/assets/qualification/device-base-v2'
PREVIOUS={
    'sky130A':'177e57626c06cb5d103aab04c4bc82983bc4ba96f2e08e4bc04006ade6cd8e2d',
    'gf180mcuC':'92ed3a348c93cde49bf48f2edf37a4f41bee6a0d3741b04f7c5ebfbdbc23ac7f',
    'gf180mcuD':'b4200b48f3fe59e961a4f514cdcb7166d21c231bccef586f01a7fa6b5f2ed738',
    'ihp-sg13g2':'63616ff9b0af1ec391e325d8f5a44ec7a5a45b420ce9a1e0946fbb14b028057c',
}
HISTORICAL_PROMOTED={
    **ALTERNATE_DEFAULTS,
    **HV_DEFAULTS,
    'sky130A':RF_DEFAULT,
    'ihp-sg13g2':NPN_DEFAULT,
}
INTERMEDIATE={'sky130A':'7f07476f0bdd530ec3060e3f7e74103e8d3f7b70ff61298af7295cb21a096ae5','ihp-sg13g2':TAP_BASE}
HISTORICAL_REVISIONS={'sky130A':RF_REVISION,**HV_REVISIONS,'ihp-sg13g2':NPN_REVISION}
# Exact current bundle identity; qualification and historical gates stay separate.
SKY130_ESD_DEFAULT='125cde7c313ee18a05a7ec5c280d514b99aea521d6b39476e44f486ae494153b'
SKY130_ESD_REVISION='5dda725c94efe3c2'
PROMOTED={**HISTORICAL_PROMOTED,'sky130A':SKY130_ESD_DEFAULT}
REVISIONS={**HISTORICAL_REVISIONS,'sky130A':SKY130_ESD_REVISION}


@contextmanager
def previous_devices(source):
    source=Path(source).resolve();h=file_digest(source/'package.json')
    target=next((t for t,expected in [*PROMOTED.items(),*HISTORICAL_PROMOTED.items(),*ALTERNATE_DEFAULTS.items(),*INTERMEDIATE.items(),*ALTERNATE_BASE.items(),('sky130A',LI_DEFAULT),('sky130A',MIM_DEFAULT),('ihp-sg13g2',TAP_DEFAULT)] if h==expected),None)
    if target is None:
        # The original recipe still applies its own strict input/hash checks.
        yield source
        return
    current=json.loads((source/'package.json').read_bytes())
    for rel,expected in current['files'].items():
        p=(source/rel).resolve()
        if not p.is_relative_to(source) or not p.is_file() or file_digest(p)!=expected:
            raise ValueError('Changed current device asset: '+rel)
    manifest=RETAINED/target/'package.json'
    if file_digest(manifest)!=PREVIOUS[target]:raise ValueError('Changed retained device manifest: '+target)
    old=json.loads(manifest.read_bytes())
    with tempfile.TemporaryDirectory(prefix='icstudio-previous-devices-') as tmp:
        dest=Path(tmp)
        for rel,expected in {'package.json':PREVIOUS[target],**old['files']}.items():
            src=manifest if rel=='package.json' else (source/rel).resolve()
            if rel!='package.json' and not src.is_relative_to(source):raise ValueError('Unsafe retained asset path.')
            if file_digest(src)!=expected:raise ValueError('Previous device asset is unavailable: '+rel)
            out=dest/rel;out.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(src,out)
            if file_digest(out)!=expected:raise ValueError('Previous device asset changed during copy: '+rel)
        yield dest


def historical_input(prepare):
    @wraps(prepare)
    def wrapped(source,output):
        # Fail before reconstruction when the caller would overwrite an output.
        if Path(output).exists():raise ValueError('Choose a new package directory; the output already exists.')
        with previous_devices(source) as original:return prepare(original,output)
    return wrapped
