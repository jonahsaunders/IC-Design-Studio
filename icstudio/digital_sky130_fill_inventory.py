"""Capture metal fill from OpenDB independently of the GDS stream reader."""
import hashlib
import json
from pathlib import Path


def capture(checkpoint):
    from openroad import Tech, Design
    checkpoint = Path(checkpoint); digest = hashlib.sha256(checkpoint.read_bytes()).hexdigest()
    tech = Tech(); design = Design(tech); design.readDb(str(checkpoint)); block = design.getBlock()
    if block is None or block.getDbUnitsPerMicron() != 1000:
        raise ValueError('SKY130 fill requires a 1 nm implementation database.')
    fills = {f'met{i}': [] for i in range(1, 6)}
    for fill in block.getFills():
        layer = fill.getTechLayer().getName(); box = fill.getRect()
        if layer not in fills or fill.needsOPC() or fill.maskNumber() != 0:
            raise ValueError('Unsupported implementation fill.')
        fills[layer].append([box.xMin(), box.yMin(), box.xMax(), box.yMax()])
    for rectangles in fills.values(): rectangles.sort()
    die = block.getDieArea()
    if hashlib.sha256(checkpoint.read_bytes()).hexdigest() != digest:
        raise ValueError('Implementation changed while capturing fill.')
    return dict(schema=1, top=block.getName(), checkpoint_sha256=digest,
                die_nm=[die.xMin(), die.yMin(), die.xMax(), die.yMax()], fills=fills)


if __name__ == '__main__':
    import sys
    source, target = map(Path, sys.argv[-2:])
    if target.exists(): raise ValueError('Preserve the previous fill inventory.')
    target.write_text(json.dumps(capture(source), separators=(',', ':'))+'\n', encoding='utf-8', newline='\n')
    print('SKY130_FILL_INVENTORY_COMPLETE')
