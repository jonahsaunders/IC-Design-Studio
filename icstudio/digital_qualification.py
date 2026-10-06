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


def faulty_mapping(mapped, destination):
    from .digital_flow import artifact
    destination=Path(destination);shutil.copytree(mapped,destination)
    path=destination/'netlist.v';text,count=re.subn(r'\.D\([^)]*\)',".D(1'b0)",path.read_text(),count=1)
    if count!=1:raise ValueError('Counter mapping must contain a D-input register for fault injection.')
    atomic_write(path,text)
    result=json.loads((destination/'result.json').read_text())
    result['digital_result']['artifacts']['netlist']=artifact(destination,path)
    atomic_write(destination/'result.json',json.dumps(result))
    return destination
