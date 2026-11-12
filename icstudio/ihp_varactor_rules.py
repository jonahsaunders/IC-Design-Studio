"""Keep complete poly/varactor contacts in the public Cnt.a width operand.

The importer splits a contact spanning poly and varactor into pc and varc.
Measuring pc alone reports its fragment width, not the written contact width.
Check their union on the same metal plane with the original 160 nm limit.
Only the private verification copy changes; no findings are filtered.
"""
import hashlib
from pathlib import Path, PurePosixPath

from .model import file_digest

RULE = 'libs.tech/magic/ihp-sg13g2-drc.tech'
SOURCE_SHA256 = 'bec75c6c8aeb9720edcdfdcf1e2c132d9be4af42801dd61b45715d6c6ec68402'
ORIGINAL = b' width pc/m1   160 "poly contact width        < %d (Cnt.a)"'
REPLACEMENT = b''' # IC Design Studio: pc and varc can be fragments of one written cut.
 # Measure their union; preserve the original Cnt.a minimum and full DRC.
 width (pc,varc)/m1 160 "poly/varactor contact width < %d (Cnt.a)"'''


def corrected(content):
    if hashlib.sha256(content).hexdigest() != SOURCE_SHA256 or content.count(ORIGINAL) != 1:
        raise ValueError('Varactor contact correction requires the exact locked IHP DRC source.')
    return content.replace(ORIGINAL, REPLACEMENT)


def prepare(assets, destination, expected_hashes):
    """Copy the already validated Magic closure and return its explicit proof."""
    destination = Path(destination)
    rule = assets[RULE]
    data = corrected(rule.read_bytes())
    prefix = 'libs.tech/magic/'
    sources = {name[len(prefix):]:path for name,path in assets.items() if name.startswith(prefix)}
    for name in sources:
        part=PurePosixPath(name)
        if part.is_absolute() or '..' in part.parts or '\\' in name or ':' in name:
            raise ValueError('Unsafe IHP Magic dependency path.')
    entry = Path(assets['technology']).name
    if entry not in sources or sources[entry].resolve() != Path(assets['technology']).resolve():
        raise ValueError('IHP Magic entry is outside the locked dependency closure.')
    destination.mkdir(parents=True, exist_ok=False)
    private = {}
    for name, source in sources.items():
        target = destination / name
        target.parent.mkdir(parents=True, exist_ok=True)
        original = source.read_bytes()
        expected = expected_hashes.get(prefix + name)
        content = data if prefix + name == RULE else original
        if hashlib.sha256(original).hexdigest() != expected:
            raise ValueError('IHP Magic dependency changed during copying.')
        target.write_bytes(content)
        if file_digest(target) != hashlib.sha256(content).hexdigest():
            raise ValueError('IHP Magic private copy failed verification.')
        private['ihp-magic/' + name] = target
    proof = dict(schema=1, rule='Cnt.a', minimum_nm=160,
                 source_sha256=SOURCE_SHA256, corrected_sha256=hashlib.sha256(data).hexdigest(),
                 original_operand='pc/m1', corrected_operand='(pc,varc)/m1',
                 scope='Full native DRC with one explicit contact-operand correction; no geometry changes or filtered findings.')
    return destination / entry, private, proof
