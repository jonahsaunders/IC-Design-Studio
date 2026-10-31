"""Capture complete top-level pin metal from OpenDB without changing the design."""
import hashlib
import json
from pathlib import Path


def capture(checkpoint):
    from openroad import Tech, Design
    checkpoint = Path(checkpoint)
    digest = hashlib.sha256(checkpoint.read_bytes()).hexdigest()
    tech = Tech(); design = Design(tech); design.readDb(str(checkpoint)); block = design.getBlock()
    if block is None or block.getDbUnitsPerMicron() != 1000:
        raise ValueError('SKY130 pin export requires a checkpoint on the 1 nm grid.')
    ports = []
    for term in sorted(block.getBTerms(), key=lambda t: t.getName()):
        boxes = []
        for pin in term.getBPins():
            for rect in pin.getBoxes():
                layer = rect.getTechLayer()
                if layer is None or rect.isVia():
                    raise ValueError('Unsupported SKY130 boundary-pin geometry.')
                bounds = [rect.xMin(), rect.yMin(), rect.xMax(), rect.yMax()]
                if bounds[0] >= bounds[2] or bounds[1] >= bounds[3]:
                    raise ValueError('Empty SKY130 boundary-pin geometry.')
                boxes.append(dict(layer=layer.getName(), box_nm=bounds))
        if not boxes or term.getNet() is None:
            raise ValueError('A SKY130 boundary port has no physical shape or net.')
        ports.append(dict(name=term.getName(), net=term.getNet().getName(),
                          kind=term.getSigType(), boxes=boxes))
    if not ports or hashlib.sha256(checkpoint.read_bytes()).hexdigest() != digest:
        raise ValueError('Empty or changed SKY130 pin inventory.')
    rect = block.getDieArea()
    return dict(schema=1, top=block.getName(), checkpoint_sha256=digest,
                die_nm=[rect.xMin(), rect.yMin(), rect.xMax(), rect.yMax()], ports=ports)


if __name__ == '__main__':
    import sys
    source, target = map(Path, sys.argv[-2:])
    if target.exists():
        raise ValueError('Use a new pin inventory output.')
    target.write_text(json.dumps(capture(source), indent=2)+'\n', encoding='utf-8', newline='\n')
    print('SKY130_PIN_INVENTORY_COMPLETE')
