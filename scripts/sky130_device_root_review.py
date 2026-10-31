"""Bind seven floating-net records to paths ending at actual device geometry."""
import argparse
from collections import Counter
import csv
import io
import json
from pathlib import Path
from tempfile import TemporaryDirectory

from icstudio import digital_sky130_device_roots as checks
from scripts import sky130_conservative_bound_review as previous_review
from scripts import sky130_catalog_queue as queue
from scripts import check_sky130_filled_replay as fixture
from scripts.sky130_rule_inventory import manual_rows

ROOT=queue.ROOT
PREVIOUS='docs/validation/sky130-conservative-bounds-2026-10-15.json'
PREVIOUS_SHA='62d872f2703c9a17f2eb7e7831e279bd1cd0087073b74f733fa9d750f8454719'
OUTPUT=ROOT/'docs/validation/sky130-device-roots-2026-10-15.json'
PARENT='docs/rules/periphery/p018-x_dotdash.csv'


def reconstruct(reader):
    catalog,baselines,_=previous_review.reconstruct(reader);previous=reader.read(PREVIOUS,PREVIOUS_SHA)
    for path,digest in previous['inputs'].items():reader.read(path,digest)
    for before,prior in zip(baselines,previous['cases']):
        if before['case']!=prior['case'] or before['gds_sha256']!=prior['original_gds_sha256']:
            raise ValueError('Changed device-root predecessor identity.')
        rows=queue.apply_decisions(before['rows'],prior['original_new_error_decisions'],catalog)
        if dict(Counter(r['disposition'] for r in rows))!=prior['original_error_counts']:
            raise ValueError('Device-root predecessor does not reconstruct.')
        before.update(rows=rows,counts=prior['original_error_counts'])
    return catalog,baselines,previous


def source_proof(folder,catalog):
    raw={name:(Path(folder)/name).read_bytes() for name in checks.SOURCE['files']}
    for name,digest in checks.SOURCE['files'].items():
        if queue.sha(raw[name])!=digest:raise ValueError('Changed physical-device-root source: '+name)
    parent=next(row for row in manual_rows(raw[PARENT],PARENT) if row['record']==37)
    if parent['rule']!='x.22' or parent['flags']!=['RC'] or \
            'Rule flags interconnects with no path to poly, difftap or metal pins.' not in parent['description']:
        raise ValueError('Changed floating-net endpoint definition.')
    definitions={r['Name']:r['Defining algorithm'] for r in csv.DictReader(io.StringIO(
        raw['docs/rules/layers/table-c3-device-lvs-other.csv'].decode()))}
    if definitions.get('gate')!='poly AND diff':raise ValueError('Changed physical gate definition.')
    layers=list(csv.DictReader(io.StringIO(raw['docs/rules/gds_layers.csv'].decode())))
    aliases=dict(licon='licon1',m1='met1',m2='met2',m3='met3',m4='met4',m5='met5',poly_short='poly')
    for name,pair in checks.LAYERS.items():
        purpose='short' if name=='poly_short' else 'drawing'
        if [r['GDS layer:datatype'] for r in layers if r['Layer name']==aliases.get(name,name) and purpose in r['Purpose'].split(', ')]!=['%s:%s'%pair]:
            raise ValueError('Changed physical-device-root layer purpose: '+name)
    indexed={r['id']:r for r in catalog['rows']}
    errors={r['ID']:r for r in csv.DictReader(io.StringIO(raw['docs/rules/errors.csv'].decode()))}
    bindings={}
    for key,name in checks.CHECKS.items():
        row=indexed[key];operand=aliases.get(name,name)
        if row['rule']!='x.22' or row['description']!='Nets on '+operand+' is floating' or \
                row['description']!=errors[key]['Description'] or errors[key]['Name']!='x.22' or \
                row['periphery_candidates']!=[PARENT+'#37']:
            raise ValueError('Changed exact floating-net catalog record.')
        bindings[key]=dict(record=row,parent={k:parent[k] for k in ('id','rule','description','flags','source_sha256')},
            proof='Every drawn conductor on this layer reaches physical gate or diffusion/tap geometry through the full contact graph. '
                  'All extracted areas are accounted for. No block-pin endpoint, label, standard-cell exemption or tie declaration is used.')
    return dict(source=checks.SOURCE,bindings=bindings,gate_definition=definitions['gate'],interpretation=checks.SCOPE)


def build(workspace=None):
    workspace=Path(workspace or ROOT.parents[1]);reader=queue.RetainedReader()
    catalog,baselines,previous=reconstruct(reader);cases=[];batches=None
    with TemporaryDirectory() as td:
        folder=Path(td)/'inputs';manifest=fixture.unpack(fixture.BUNDLE,folder);proof=source_proof(folder/'sources',catalog)
        for entry in manifest['cases']:
            name=entry['case'];before=next(c for c in baselines if c['case']==name);prior=next(c for c in previous['cases'] if c['case']==name)
            original=checks.audit(folder/entry['gds'])
            corrected=checks.audit(workspace/'outputs/sky130-application-boundary-v1/linux'/name/'sky130-pin-export/final.gds')
            if original['gds_sha256']!=before['gds_sha256'] or corrected['gds_sha256']!=prior['corrected_gds_sha256']:
                raise ValueError('Changed physical-device-root reference identity.')
            for report in (original,corrected):
                checks.evaluate(report,report['gds_sha256'],report['top'])
                if Counter(r['disposition'] for r in report['rows'])!={'executed-reviewed':7} or report['pin_roots_used']:
                    raise ValueError('Reference does not establish every physical-device-root path.')
            if original['measurements']!=corrected['measurements']:raise ValueError('Device-root graph changed during outline correction.')
            rows=queue.apply_decisions(before['rows'],original['rows'],catalog)
            current=queue.partition([r for r in rows if r['disposition']=='unreviewed'])
            if batches is not None and batches!=current:raise ValueError('Reference queues differ.')
            batches=current
            cases.append(dict(case=name,original_gds_sha256=original['gds_sha256'],original_measurement=original,
                original_new_error_decisions=original['rows'],original_error_counts=dict(Counter(r['disposition'] for r in rows)),
                corrected_gds_sha256=corrected['gds_sha256'],corrected_device_roots=corrected))
    paths=[Path(__file__),Path(checks.__file__),ROOT/'tests/test_sky130_device_roots.py',
           ROOT/'icstudio/digital_sky130_rules.py',ROOT/'icstudio/digital_sky130_rule_worker.py',ROOT/'tests/test_sky130_application_rules.py']
    return dict(schema=1,chunk=6,status='physical-device-root-connectivity-reviewed',qualified=False,chunk_complete=False,
        inputs=dict(sorted(reader.digests.items())),source_files={p.relative_to(ROOT).as_posix():queue.sha(p.read_bytes()) for p in paths},
        proof=proof,cases=cases,remaining_original_batches=[dict(id=b['id'],count=b['count'],ids=[r['id'] for r in b['records']]) for b in batches],
        scope='Seven floating-net records pass a complete physical-device-root graph with no block-pin endpoints. '
              'Unrooted components or unimplemented profile selectors remain unreviewed. This does not establish '
              'device/body LVS, chip I/O correctness, ESD or electrical performance. The original catalog retains '
              '456 unreviewed records; chunk 6 remains incomplete.')


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--workspace',type=Path);p.add_argument('--output',type=Path,default=OUTPUT)
    p.add_argument('--check',action='store_true');a=p.parse_args();raw=(json.dumps(build(a.workspace),indent=2,ensure_ascii=False)+'\n').encode()
    if a.check:
        if a.output.read_bytes()!=raw:raise ValueError('Saved physical-device-root review differs.')
    else:a.output.write_bytes(raw)
    print(json.dumps({c['case']:c['original_error_counts'] for c in json.loads(raw)['cases']}))
