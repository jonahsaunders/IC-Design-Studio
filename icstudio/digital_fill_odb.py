"""Native OpenROAD worker for exact floating square representation and extraction.

Run with OpenROAD's embedded Python. This module is also captured as a job
artifact; the normal application process does not import OpenDB.
"""
import json
from pathlib import Path


def run(request):
    import odb
    from openroad import Tech, Design
    def require(ok, message):
        if not ok: raise ValueError(message)
    tech = Tech(); design = Design(tech); design.readDb(request['source'])
    block = design.getBlock(); dbtech = tech.getDB().getTech()
    dbu = block.getDbUnitsPerMicron(); require(dbu > 0, 'Missing database units.')
    def coord(nm):
        require(type(nm) is int and nm*dbu % 1000 == 0, 'Fill coordinate is not representable in OpenDB.')
        return nm*dbu//1000
    directory = Path(request['directory'])
    def word(path):
        text = str(path)
        require(not any(c in text for c in '{}\r\n'), 'Unsupported native extraction path.')
        return '{'+text+'}'
    original = set(n.getName() for n in block.getNets())
    die = block.getDieArea()
    require([die.xMin(), die.yMin(), die.xMax(), die.yMax()] == [coord(v) for v in request['die_nm']],
            'Fill boundary differs from the actual implementation die.')
    require(not any(n.startswith('ICSTUDIO_FLOAT_') for n in original), 'Reserved fill net prefix already exists.')
    design.evalTclString('write_def '+word(directory/'before.def'))
    added = []; layer = dbtech.findLayer('Metal1'); require(layer is not None, 'Metal1 is missing.')
    ndr = odb.dbTechNonDefaultRule.create(dbtech, 'ICSTUDIO_FLOATING_SQUARE_2UM')
    require(ndr is not None, 'Floating-fill width rule already exists.')
    rule = odb.dbTechLayerRule.create(ndr, layer); rule.setWidth(coord(2000))
    for i, box in enumerate(request['boxes']):
        require(len(box) == 4 and box[2]-box[0] == box[3]-box[1] == 2000, 'Fill must be 2 µm squares.')
        name = 'ICSTUDIO_FLOAT_'+str(i).zfill(4)
        net = odb.dbNet.create(block, name); net.setSigType('SIGNAL')
        wire = odb.dbWire.create(net); enc = odb.dbWireEncoder(); enc.begin(wire)
        enc.newPath(layer, 'ROUTED', rule)
        x1, y1, x2, y2 = [coord(v) for v in box]; y = (y1+y2)//2
        enc.addPoint(x1, y, 0); enc.addPoint(x2, y, 0); enc.end()
        require(not net.getITerms() and not net.getBTerms(), 'Fill was connected to a circuit terminal.')
        shape = odb.dbShape(); wire.getShape(5, shape); actual = shape.getBox()
        require(shape.getTechLayer().getName() == 'Metal1' and
                [actual.xMin(), actual.yMin(), actual.xMax(), actual.yMax()] == [x1, y1, x2, y2],
                'OpenDB fill shape differs from the written GDS.')
        added.append(dict(net=name, box_nm=box))
    design.evalTclString('write_def '+word(directory/'represented.def'))
    design.writeDb(str(directory/'represented.odb'))
    design.evalTclString('write_abstract_lef '+word(directory/'filled.lef'))
    # Reopen the serialized database and check the exact masks used by RCX.
    check_tech = Tech(); check = Design(check_tech); check.readDb(str(directory/'represented.odb'))
    for item in added:
        net = check.getBlock().findNet(item['net']); shape = odb.dbShape(); net.getWire().getShape(5, shape)
        b = shape.getBox()
        require([b.xMin(), b.yMin(), b.xMax(), b.yMax()] == [coord(v) for v in item['box_nm']],
                'Serialized fill geometry changed.')
    design.evalTclString('define_process_corner -ext_model_index 0 icstudio_rc')
    design.evalTclString('extract_parasitics -ext_model_file '+word(request['rules'])+' -coupling_threshold 0')
    design.evalTclString('write_spef -coordinates '+word(directory/'parasitics.spef'))
    (directory/'represented.json').write_text(json.dumps(dict(dbu_per_micron=dbu,
        original_nets=len(original), total_nets=len(block.getNets()), added=added), indent=2)+'\n')


if __name__ == '__main__':
    run(json.loads(Path('request.json').read_text()))
