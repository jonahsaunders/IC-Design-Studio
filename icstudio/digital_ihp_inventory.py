"""Read exact IHP signal geometry and cell terminals from an OpenDB checkpoint.

Executed with OpenROAD's embedded Python. The database is never modified.
The boxes include complete via bounds; callers still verify them against GDS.
"""
import hashlib
import json
from pathlib import Path


def capture(checkpoint):
    import odb
    from openroad import Tech, Design
    checkpoint = Path(checkpoint)
    digest = hashlib.sha256(checkpoint.read_bytes()).hexdigest()
    tech = Tech(); design = Design(tech); design.readDb(str(checkpoint))
    block = design.getBlock()
    if block is None or block.getDbUnitsPerMicron() != 1000:
        raise ValueError('IHP fill requires a checkpoint on the 1 nm grid.')
    def box(rect):
        values = [rect.xMin(), rect.yMin(), rect.xMax(), rect.yMax()]
        if values[0] >= values[2] or values[1] >= values[3]:
            raise ValueError('An empty native geometry box cannot define fill clearance.')
        return values
    nets = []
    for index, net in enumerate(sorted(block.getNets(), key=lambda n: n.getName())):
        pins, wires = [], []
        for term in net.getITerms():
            for layer, rect in term.getGeometries():
                pins.append(dict(layer=layer.getName(), box_nm=box(rect),
                                 terminal=term.getInst().getName()+'/'+term.getMTerm().getName(),
                                 direction=term.getMTerm().getIoType()))
        for term in net.getBTerms():
            for pin in term.getBPins():
                for rect in pin.getBoxes():
                    if rect.getTechLayer():
                        pins.append(dict(layer=rect.getTechLayer().getName(), box_nm=box(rect),
                                         terminal=term.getName(), direction=term.getIoType()))
        if net.getSigType() not in ('POWER', 'GROUND'):
            wire = net.getWire()
            if wire:
                iterator = odb.dbWirePathItr(); iterator.begin(wire)
                path, item = odb.dbWirePath(), odb.dbWirePathShape()
                while iterator.getNextPath(path):
                    while iterator.getNextShape(item):
                        shape = item.shape
                        if not (shape.isSegment() or shape.isVia() or shape.isViaBox()):
                            raise ValueError('Unsupported native signal shape.')
                        layer = shape.getTechLayer()
                        wires.append(dict(box_nm=box(shape.getBox()),
                                          layer=layer.getName() if layer else None,
                                          kind='via' if shape.isVia() or shape.isViaBox() else 'segment'))
            if net.getSWires():
                raise ValueError('Signal special wires require a separate clearance inventory.')
            if not pins:
                raise ValueError('A signal net has no physical terminal.')
        nets.append(dict(net=net.getName(), alias=f'NET{index:06d}',
                         sig_type=net.getSigType(), pins=pins, wires=wires))
    instances = [dict(name=i.getName(), master=i.getMaster().getName(),
                      box_nm=box(i.getBBox())) for i in block.getInsts()]
    if hashlib.sha256(checkpoint.read_bytes()).hexdigest() != digest:
        raise ValueError('Checkpoint changed during the inventory.')
    return dict(schema=1, checkpoint_sha256=digest, top=block.getName(),
                die_nm=box(block.getDieArea()), nets=nets, instances=instances)


if __name__ == '__main__':
    import sys
    source, target = map(Path, sys.argv[-2:])
    if target.exists():
        raise ValueError('Use a new native inventory output.')
    result = capture(source)
    target.write_text(json.dumps(result, indent=2)+'\n', encoding='utf-8', newline='\n')
    print('IHP_FILL_INVENTORY_COMPLETE', len(result['nets']))
