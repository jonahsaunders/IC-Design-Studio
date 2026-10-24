"""Explicit x.29 mode and C3-defined NFET containment measurements.

No default is accepted. Ordinary bulk mode is NOT_REQUESTED, never a passing
isolation test. Containment is measured in either mode and retained verbatim.
"""
import argparse
import csv
import io
import json
from pathlib import Path

import klayout.db as k
from scripts import sky130_grid_geometry as grid
from scripts.sky130_voltage_contract import require
from scripts.sky130_voltage_intent_review import authenticated, sha
from scripts.sky130_rule_inventory import manual_rows, validate_unreviewed

ROOT=Path(__file__).resolve().parents[1]
SOURCE='docs/rules/periphery/p018-x_dotdash.csv'
DEFINITION='docs/rules/layers/table-c3-device-lvs-other.csv'
RULE_ID=SOURCE+'#49'
SCOPE=('The explicit nfet_in_dnwell switch controls only x.29. C3 defines nfet as '
       '(poly AND diff) NOT nwell. Complete containment in the union of drawn '
       'deep-nwell polygons is measured without inventing a numeric margin. '
       'Other well spacing, body connectivity, RF requirements and physical qualification remain separate.')


def source_proof(source, inventory):
    validate_unreviewed(inventory);files={}
    for name in (SOURCE,DEFINITION):
        raw=authenticated(Path(source)/name,inventory['source_files'][name]['sha256'])
        files[name]=inventory['source_files'][name]['sha256']
        if name==SOURCE:
            rows=[r for r in manual_rows(raw,name) if r['id']==RULE_ID]
            require(len(rows)==1,'Missing exact x.29 source row.')
            row=rows[0];expected=next(r for r in inventory['rule_rows'] if r['id']==RULE_ID)
            require(all(row[key]==expected[key] for key in ('rule','description','record','value','unit','flags')),
                    'Changed optional isolation requirement.')
            require(row['rule']=='x.29' and row['description']==
                'nfet must be enclosed by dnwell. Rule is checked when switch nfet_in_dnwell is turned on.'
                and row['value']==row['unit']=='','Unexpected x.29 switch or numeric semantics.')
    definitions={r['Name']:r['Defining algorithm'] for r in csv.DictReader(io.StringIO(
        (Path(source)/DEFINITION).read_text(encoding='utf-8')))}
    require(definitions['gate']=='poly AND diff' and definitions['nfet']=='Gate NOT  nwell',
            'Changed C3 NFET selector.')
    return dict(files=files,rule=expected,definitions={name:definitions[name] for name in ('gate','nfet')},scope=SCOPE)


def mode(options):
    require(isinstance(options,dict) and set(options)=={'nfet_in_dnwell'}
            and type(options['nfet_in_dnwell']) is bool,'Declare an explicit Boolean nfet_in_dnwell option.')
    return options['nfet_in_dnwell']


def measure(layout):
    diagnostic=grid.check(layout)
    require(not any(row['violations'] for row in diagnostic['checks'] if row['rule'].startswith('profile.')),
            'Unsupported geometry for NFET containment.')
    top=layout.top_cell()
    region=lambda pair:k.Region(top.begin_shapes_rec(layout.layer(*pair))).merged()
    gates=(region((65,20))&region((66,20))).merged();well=region((64,20));dnwell=region((64,18))
    nfet=(gates-well).merged();pfet=(gates&well).merged()
    straddling=sum(not (k.Region(g)&well).is_empty() and not (k.Region(g)-well).is_empty() for g in gates.each())
    require(not straddling,'A gate straddles nwell; its device classification needs review.')
    outside=[]
    for gate in nfet.each():
        if not (k.Region(gate)-dnwell).is_empty():
            box=gate.bbox();outside.append([box.left,box.bottom,box.right,box.top])
    raw=top.begin_shapes_rec(layout.layer(64,18));raw_shapes=raw_texts=0
    while not raw.at_end():
        raw_shapes+=1;raw_texts+=int(raw.shape().is_text());raw.next()
    return dict(top=top.name,nfet_gates=nfet.count(),pfet_gates=pfet.count(),dnwell_polygons=dnwell.count(),
                raw_dnwell_shapes=raw_shapes,raw_dnwell_texts=raw_texts,
                nfet_not_contained=len(outside),outside_examples_nm=sorted(outside)[:20])


def evaluate(measurement, options):
    enabled=mode(options)
    keys=('nfet_gates','pfet_gates','dnwell_polygons','raw_dnwell_shapes','raw_dnwell_texts','nfet_not_contained')
    require(all(type(measurement.get(key)) is int and measurement[key]>=0 for key in keys)
            and measurement['nfet_not_contained']<=measurement['nfet_gates']
            and measurement['raw_dnwell_texts']<=measurement['raw_dnwell_shapes'],
            'Invalid containment measurement.')
    violations=measurement['nfet_not_contained']
    return dict(schema=1,rule='x.29',options=dict(options),qualified=False,
        status=('FAIL' if violations else 'PASS') if enabled else 'NOT_REQUESTED',
        disposition=('execution-failed' if violations else 'executed-reviewed') if enabled else 'declared-option-not-required',
        enforced=enabled,measured_noncontained_gates=violations,measurement=measurement,scope=SCOPE)


def check(layout,options):
    mode(options)  # Never guess a mode, even if the target happens to be empty.
    return evaluate(measure(layout),options)


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--gds',type=Path,required=True)
    parser.add_argument('--mode',choices=('bulk','isolated'),required=True)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args();before=sha(args.gds);layout=k.Layout();layout.read(str(args.gds))
    result=check(layout,{'nfet_in_dnwell':args.mode=='isolated'})
    require(sha(args.gds)==before,'Layout changed while reading.')
    result.update(gds_sha256=before,checker_sha256=sha(__file__))
    require(not args.output.exists(),'Preserve the existing check result.')
    args.output.write_bytes((json.dumps(result,indent=2)+'\n').encode())
    print(json.dumps(dict(status=result['status'],measured_noncontained_gates=result['measured_noncontained_gates'])))
    raise SystemExit(2 if result['status']=='FAIL' else 0)
