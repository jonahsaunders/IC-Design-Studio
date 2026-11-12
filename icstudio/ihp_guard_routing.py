"""Finite opt-in corrected IHP guard routing; not unchanged native PDK masks."""
import hashlib,json
from pathlib import Path
from .model import file_digest

OPTION='corner-safe-m2-v1'
RECIPE='ihp-resistor-guard-corner-safe-v1'
TEMPLATE_HASH='f1ade4a445f011532622f78a23b30a90f5b3607d4944b3634abf8ef5b68e3d31'
CIFOUT_HASH='b972c6d07557e0147462ad533aaf2f3aea14404437f800a1f8fc96ba13086dc8'
NATIVE_LABEL='Native Metal1 body'
CORNER_LABEL='Corner-safe Metal2 body (2/7 um only)'


def templates(tech):
    try:
        source=Path(tech['package_root'])/'libs.tech/magic/ihp-sg13g2-cifout.tech'
        if file_digest(source)!=CIFOUT_HASH:raise ValueError('Changed reviewed guard cut-array source.')
        raw=(Path(__file__).parent/'assets/qualification/ihp-guard-corner-safe/templates.json').read_bytes()
        if hashlib.sha256(raw).hexdigest()!=TEMPLATE_HASH:raise ValueError('Changed corner-safe guard templates.')
        return json.loads(raw)
    except (OSError,KeyError,json.JSONDecodeError) as exc:
        raise ValueError('Reviewed corner-safe guard assets are unavailable.') from exc


def specification_fields(tech,d,size,via):
    if 'physical_guard_routing' not in d:return {}
    choice=d['physical_guard_routing']
    if choice!=OPTION:raise ValueError('Choose the reviewed corner-safe guard routing option.')
    if tuple(size)!=(2000,7000) or via:raise ValueError('Corner-safe guard requires W/L 2/7 µm and Metal1 resistor terminals; Metal2 terminal access is unsupported.')
    data=templates(tech)
    return dict(recipe=RECIPE,guard_routing=OPTION,template_sha256=TEMPLATE_HASH,guard_template_sha256=TEMPLATE_HASH,guard_source_report_sha256=data['source_report_sha256'],guard_contract_sha256=data['contract_sha256'],guard_native_equivalence=False,guard_cifout_sha256=CIFOUT_HASH)
