"""Shared, explicit acceptance fixture for custom and included digital tools."""
import json
from pathlib import Path
import re
import shutil

from . import digital, digital_constraints, digital_platform
from .model import atomic_write


def counter(platform):
    project=digital.counter_project()
    config=digital_platform.bind(project['digital'],platform)
    intent=digital_constraints.default_intent();intent['clocks'][0]['period_ns']=50
    config=digital_constraints.apply(config,intent);config['timeout']=600
    config['physical']={'die_area':[0,0,200,200],'core_area':[20,20,180,180],'place_density':0.6,'threads':2}
    project['digital']=config
    return project


def require_clean_route(folder):
    metrics=json.loads((Path(folder)/'physical_metrics.json').read_text())
    counts=[value['detailedroute__route__drc_errors'] for value in metrics.values()
            if 'detailedroute__route__drc_errors' in value]
    if not counts or any(type(n) is not int or n!=0 for n in counts):
        raise ValueError('Final detailed-route rule checks are missing or not clean: '+repr(counts))
    return {'detailed_route_drc_errors':counts,'scope':'Router rule checks; not foundry DRC/LVS'}


def faulty_mapping(mapped, destination, output=None):
    from .digital_flow import artifact
    mapped=Path(mapped)
    # A combinational OR4 also has a pin named D. Require mapped register pins
    # and, for workloads such as UART, select an observable named state output.
    hierarchy=json.loads((mapped/'netlist.json').read_text())
    types={c['type'] for module in hierarchy['modules'].values() for c in module.get('cells',{}).values()
        if c.get('port_directions',{}).get('D')=='input' and c.get('port_directions',{}).get('Q')=='output'
        and any(c.get('port_directions',{}).get(pin)=='input' for pin in ('CLK','CK','C'))}
    original=(mapped/'netlist.v').read_text();selected=None
    for cell in re.finditer(r'(?m)^\s*(\S+)\s+(\S+)\s+\([^;]*?\);',original):
        if cell[1] not in types:continue
        pins=cell[0]
        if output is not None and not re.search(r'\.Q\(\s*'+re.escape(output)+r'\s*\)',pins):continue
        changed,count=re.subn(r'\.D\([^)]*\)',".D(1'b0)",pins,count=1)
        if count==1 and changed!=pins:selected=(cell,changed);break
    if selected is None:raise ValueError('No mapped D-input register matches the requested fault output: '+repr(output))
    cell,changed=selected;text=original[:cell.start()]+changed+original[cell.end():]
    destination=Path(destination);shutil.copytree(mapped,destination);path=destination/'netlist.v'
    atomic_write(path,text)
    atomic_write(destination/'qualification_fault.json',json.dumps({'cell_type':cell[1],'instance':cell[2],
        'output':output,'before':cell[0].strip(),'after':changed.strip()},indent=2))
    result=json.loads((destination/'result.json').read_text())
    result['digital_result']['artifacts']['netlist']=artifact(destination,path)
    atomic_write(destination/'result.json',json.dumps(result))
    return destination
