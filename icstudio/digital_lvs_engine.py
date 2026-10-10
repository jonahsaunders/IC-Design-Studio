"""Read-only OpenROAD worker for final-checkpoint reference generation.

Runs inside the captured OpenROAD Python engine, without importing Studio.
"""
import hashlib
import json
from pathlib import Path


def sha(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def tcl_word(value):
    return '"' + str(value).replace('\\', '\\\\').replace('"', '\\"').replace(
        '$', '\\$').replace('[', '\\[').replace(']', '\\]').replace('\n', '\\n').replace('\r', '\\r') + '"'


def run(request):
    from openroad import Tech, Design
    inputs = [request['checkpoint'], *request['masters']]
    for item in inputs:
        if sha(item['path']) != item['sha256']:
            raise ValueError('Reference input changed before OpenDB readback.')
    output = Path(request['raw_cdl'])
    if output.exists():
        raise ValueError('Raw reference output already exists.')
    tech = Tech(); design = Design(tech)
    design.readDb(request['checkpoint']['path'])
    block = design.getBlock()
    if block.getName() != request['top']:
        raise ValueError('The checkpoint belongs to a different top cell.')
    instances = []
    for inst in block.getInsts():
        box = inst.getBBox()
        instances.append(dict(name=inst.getName(), database_id=inst.getId(),
            master=inst.getMaster().getName(), orientation=str(inst.getOrient()),
            bbox=[box.xMin(), box.yMin(), box.xMax(), box.yMax()],
            pins=[dict(name=p.getMTerm().getName(), net=p.getNet().getName() if p.getNet() else '',
                       direction=str(p.getMTerm().getIoType())) for p in inst.getITerms()]))
    rules = [dict(inst_pattern=r.getInstPattern(), pin_pattern=r.getPinPattern(),
                  net=r.getNet().getName(), region=r.getRegion().getName() if r.getRegion() else None)
             for r in block.getGlobalConnects()]
    ports = [dict(name=p.getName(), net=p.getNet().getName() if p.getNet() else '',
                  direction=str(p.getIoType())) for p in block.getBTerms()]
    masters = '[list ' + ' '.join(tcl_word(p['path']) for p in request['masters']) + ']'
    command = 'write_cdl -masters ' + masters + ' -include_fillers ' + tcl_word(output)
    status = design.evalTclString('if {[catch {' + command +
        '} studio_reference_error]} {set studio_reference_status 1} else {set studio_reference_status 0}; set studio_reference_status')
    if status != '0':
        raise ValueError('OpenROAD reference export failed: ' + design.evalTclString('set studio_reference_error'))
    for item in inputs:
        if sha(item['path']) != item['sha256']:
            raise ValueError('Reference input changed during OpenDB readback.')
    return dict(schema=1, top=block.getName(), checkpoint_sha256=request['checkpoint']['sha256'],
        database=dict(version=1, dbu_per_micron=block.getDbUnitsPerMicron(), instances=instances),
        ports=ports, global_connections=rules, raw_cdl_sha256=sha(output))


if 'REQUEST_PATH' in globals():
    request = json.loads(Path(REQUEST_PATH).read_text(encoding='utf-8'))
    result = run(request)
    Path(request['output']).write_text(json.dumps(result, indent=2) + '\n', encoding='utf-8')
