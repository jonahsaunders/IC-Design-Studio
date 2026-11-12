"""Bind seven special-device records only when their subjects are provably absent."""
import argparse
from collections import Counter
import csv
import io
import json
from pathlib import Path
from tempfile import TemporaryDirectory

from icstudio import digital_sky130_special_subjects as checks
from scripts import sky130_device_root_review as previous_review
from scripts import sky130_catalog_queue as queue
from scripts import check_sky130_filled_replay as fixture
from scripts.sky130_rule_inventory import manual_rows

ROOT=queue.ROOT
PREVIOUS='docs/validation/sky130-device-roots-2026-10-15.json'
PREVIOUS_SHA='7c2d7e30f66bdfcf28d0b3b67c1a83fe34aaa9f17e35e265efda013f1a564346'
OUTPUT=ROOT/'docs/validation/sky130-special-subjects-2026-10-15.json'


def reconstruct(reader):
    catalog,baselines,_=previous_review.reconstruct(reader);previous=reader.read(PREVIOUS,PREVIOUS_SHA)
    for path,digest in previous['inputs'].items():reader.read(path,digest)
    for before,prior in zip(baselines,previous['cases']):
        if before['case']!=prior['case'] or before['gds_sha256']!=prior['original_gds_sha256']:
            raise ValueError('Changed special-subject predecessor identity.')
        rows=queue.apply_decisions(before['rows'],prior['original_new_error_decisions'],catalog)
        if dict(Counter(r['disposition'] for r in rows))!=prior['original_error_counts']:
            raise ValueError('Special-subject predecessor does not reconstruct.')
        before.update(rows=rows,counts=prior['original_error_counts'])
    return catalog,baselines,previous


def source_proof(folder,catalog):
    raw={name:(Path(folder)/name).read_bytes() for name in checks.SOURCE['files']}
    for name,digest in checks.SOURCE['files'].items():
        if queue.sha(raw[name])!=digest:raise ValueError('Changed special-subject source: '+name)
    definitions={r['Name']:r['Defining algorithm'] for r in csv.DictReader(io.StringIO(
        raw['docs/rules/layers/table-c3-device-lvs-other.csv'].decode()))}
    if definitions.get('prec_resistor')!='rpm AND (poly overlapping poly.rs) AND psdm':
        raise ValueError('Changed precision-resistor definition.')
    layers=list(csv.DictReader(io.StringIO(raw['docs/rules/gds_layers.csv'].decode())))
    aliases=dict(poly_resistor=('poly','resistor'),areaid_en=('areaid.en','identifier'),areaid_en20=('areaid.en20','identifier'))
    for name,pair in (checks.LAYERS|{'nwell':(64,20)}).items():
        alias,purpose=aliases.get(name,(name,'mask' if name in ('cdnm','cnwm','crpm') else 'drawing'))
        if [r['GDS layer:datatype'] for r in layers if r['Layer name']==alias and purpose in r['Purpose'].split(', ')]!=['%s:%s'%pair]:
            raise ValueError('Changed special-subject purpose: '+name)
    literal={
        'r396':('ulvt.3','LOWVTID must not straddle uhvi','p055-ulvt-_dotdash','ulvt-.3'),
        'r929':('uhvi.2','poly must not straddle uhvi','p055-uhvi_dotdash_dotdash','uhvi.2.-'),
        'r928':('uhvi.6','UHVI must enclose dnwell','p055-uhvi_dotdash_dotdash','uhvi.6.-'),
        'r1047':('urpm.3','0.2 min. enclosure of precResistor by rpm','p029-rpm_dotdash','rpm.3'),
        'r1059':('rpm.10','2 min. spacing of rpmNotXmt & pwbm','p029-rpm_dotdash','rpm.10'),
        'r1060':('rpm.10','rpmNotXmt must not overlap pwbm','p029-rpm_dotdash','rpm.10'),
        'r922':('depmos.8','90 degree angles are not permitted for nwellhole over poly','p051-depmos_dotdash','depmos.8')}
    indexed={r['id']:r for r in catalog['rows']};errors={r['ID']:r for r in csv.DictReader(io.StringIO(raw['docs/rules/errors.csv'].decode()))}
    bindings={}
    for subject,group in checks.GROUPS.items():
        for key in group['ids']:
            rule,description,section,parent_rule=literal[key];row=indexed[key]
            if (row['rule'],row['description'])!=(rule,description) or (errors[key]['Name'],errors[key]['Description'])!=(rule,description):
                raise ValueError('Changed literal special-subject catalog record.')
            path='docs/rules/periphery/'+section+'.csv';parents=[r for r in manual_rows(raw[path],path) if r['rule']==parent_rule]
            if len(parents)!=1:raise ValueError('Missing exact special-subject parent.')
            bindings[key]=dict(record=row,subject=subject,raw_operands=list(group['raw']),candidate_tokens=list(checks.HINTS[group['hints']]),
                nwell_holes_required_absent=group['holes'],parent=parents[0])
    return dict(source=checks.SOURCE,bindings=bindings,prec_resistor_definition=definitions['prec_resistor'],interpretation=checks.SCOPE,
        discrepancies=[
            'The catalog calls the precision-resistor enclosure urpm.3 while the matching manual description is rpm.3. Both implant selectors and poly-resistor data are required empty; no nonempty threshold/name equivalence is claimed.',
            'The catalog depmos.8 selects nwell holes over poly; the manual selects holes overlapping a drain-extended PMOS drain. The complete merged nwell has no holes, and explicit masks/device markers are also absent. This does not resolve their nonempty selector difference.',
            'UHV manual values and rpm.10 are N/A while catalog messages exist. N/A is not used as a waiver; only independently established empty operands discharge these records.'])


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
                raise ValueError('Changed special-subject reference identity.')
            for report in (original,corrected):
                checks.evaluate(report,report['gds_sha256'],report['top'])
                if Counter(r['disposition'] for r in report['rows'])!={'absent-operand':7}:
                    raise ValueError('Reference does not establish each conservative special-subject absence.')
            if original['measurements']!=corrected['measurements']:raise ValueError('Special-subject geometry changed during outline correction.')
            rows=queue.apply_decisions(before['rows'],original['rows'],catalog)
            current=queue.partition([r for r in rows if r['disposition']=='unreviewed'])
            if batches is not None and batches!=current:raise ValueError('Reference queues differ.')
            batches=current
            cases.append(dict(case=name,original_gds_sha256=original['gds_sha256'],original_measurement=original,
                original_new_error_decisions=original['rows'],original_error_counts=dict(Counter(r['disposition'] for r in rows)),
                corrected_gds_sha256=corrected['gds_sha256'],corrected_special_subjects=corrected))
    paths=[Path(__file__),Path(checks.__file__),ROOT/'tests/test_sky130_special_subjects.py',
           ROOT/'icstudio/digital_sky130_rules.py',ROOT/'icstudio/digital_sky130_rule_worker.py',ROOT/'tests/test_sky130_application_rules.py']
    return dict(schema=1,chunk=6,status='special-subject-absence-reviewed',qualified=False,chunk_complete=False,
        inputs=dict(sorted(reader.digests.items())),source_files={p.relative_to(ROOT).as_posix():queue.sha(p.read_bytes()) for p in paths},
        proof=proof,cases=cases,remaining_original_batches=[dict(id=b['id'],count=b['count'],ids=[r['id'] for r in b['records']]) for b in batches],
        scope='Seven special-device records have empty required operands under conservative mask and intent guards. '
              'Nonempty subjects and unresolved source differences remain unreviewed. The original catalog retains '
              '449 unreviewed records; chunk 6 remains incomplete.')


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--workspace',type=Path);p.add_argument('--output',type=Path,default=OUTPUT)
    p.add_argument('--check',action='store_true');a=p.parse_args();raw=(json.dumps(build(a.workspace),indent=2,ensure_ascii=False)+'\n').encode()
    if a.check:
        if a.output.read_bytes()!=raw:raise ValueError('Saved special-subject review differs.')
    else:a.output.write_bytes(raw)
    print(json.dumps({c['case']:c['original_error_counts'] for c in json.loads(raw)['cases']}))
