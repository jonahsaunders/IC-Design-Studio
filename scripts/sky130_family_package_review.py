"""Replay 38 family absences and five package crossings against the full catalog."""
import argparse, csv, io, json
from collections import Counter
from pathlib import Path
from tempfile import TemporaryDirectory
import xml.etree.ElementTree as ET

from icstudio import digital_sky130_family_targets as family
from icstudio import digital_sky130_package_boundaries as package
from scripts import sky130_seal_geometry_review as previous_review

delivery=previous_review.delivery
ROOT=delivery.ROOT
PREVIOUS='docs/validation/sky130-seal-geometry-2026-10-15.json'
PREVIOUS_SHA='5d304631ec59f1116c12e3c39c4d61c8564d9a922a4aa86e4cf62fa504b9c42d'
OUTPUT=ROOT/'docs/validation/sky130-family-package-2026-10-15.json'
BOND_LITERALS={
    'r1312':('pad.1','padPL pcells should be used for bondpad'),
    'r1313':('pad.1','padPL pcells should have text plastic to be used for bondpad'),
    'r1333':('pad.15','500.0 Max spacing between bondpad opening and edge of scribe line(outer end of seal ring)')}
RF_MODELS=(('W0p42_L0p15_2F','0.42','1.14'),('W0p84_L0p15_2F','0.84','1.14'),
    ('W0p84_L0p15_4F','0.84','2'),('W0p84_L0p15_8F','0.84','3.72'),
    ('W3p0_L0p15_2F','1.14','3'),('W3p0_L0p15_4F','2','3'),('W3p0_L0p15_8F','3','3.72'))


def source_proof(folder,catalog):
    raw={key:delivery.checked(Path(folder)/key,digest) for key,digest in (family.SOURCE['files']|package.SOURCE['files']).items()}
    def rows(key):return list(csv.DictReader(io.StringIO(raw[key].decode())))
    table=family.SOURCE['device_table'];table_raw=delivery.checked(ROOT/table['path'],table['sha256'])
    device=[{key.strip():value.strip() for key,value in row.items()}
            for row in csv.DictReader(io.StringIO(table_raw.decode()),delimiter='\t')]
    matches=[(i+1,r) for i,r in enumerate(device) if r['Layout Model']=='nlowvt']
    delivery.require(len(matches)==1 and matches[0][1]['Name']=='Low Vt nmos 1.8V 32A' and
                     matches[0][1]['lvtn:dg']=='D','Changed mandatory nlowvt drawing prerequisite.')
    delivery.require('``D`` = DRAWN indicates that a layer is drawn by Design.' in
        raw['docs/rules/layers/table-f2a-lvs-key.rst'].decode(),'Changed drawn-device table semantics.')
    definitions={r['Name']:r['Defining algorithm'] for r in rows('docs/rules/layers/table-c3-device-lvs-other.csv')}
    delivery.require(definitions.get('bondPad')=='pad:dg OUTSIDE areaid:ft','Changed bondPad definition.')
    layers=rows('docs/rules/gds_layers.csv');aliases={
        'pad_pin':('pad','pin'),'pad_label':('pad','label'),'pad_legacy_pin':('pad','pin'),
        'cpdm':('cpdm','mask'),'pad_center':('padCenter','drawing'),'pad_frame':('areaid.fe','identifier'),
        'clvtnm':('clvtnm','mask'),'clvtnm_drawing':('clvtnm','drawing'),
        'clvtnm_add':('clvtnm','mask add'),'clvtnm_drop':('clvtnm','mask drop'),'low_vt_id':('areaid.lvt','identifier')}
    bindings={}
    for name,pair in family.LAYERS.items():
        alias,purpose=aliases.get(name,(name,'drawing'))
        found=[r for r in layers if r['Layer name']==alias and purpose in r['Purpose'].split(', ') and r['GDS layer:datatype']=='%s:%s'%pair]
        delivery.require(len(found)==1,'Changed family guard purpose: '+name);bindings[name]=found[0]
    delivery.require(bindings['lvtn']['Description']=='Low-Vt NMOS device','Changed low-Vt drawing meaning.')
    literals=dict(BOND_LITERALS)
    for n,(suffix,width,length) in enumerate(RF_MODELS):
        model='sky130rf_nlowvt_'+suffix+'_cell'
        descriptions=(model+' should be rectangular',width+' min. width of '+model,width+' max. width of '+model,
                      length+' min. length of '+model,length+' max. length of '+model)
        literals.update({'r'+str(645+5*n+i):('diff.13',s) for i,s in enumerate(descriptions)})
    literals.update({key:('scribe.7',r['target']+' drawn layer cannot straddle areaid:ModuleCut') for key,r in package.CHECKS.items()})
    errors={r['ID']:r for r in rows('docs/rules/errors.csv')};indexed={r['id']:r for r in catalog['rows']}
    for key,value in literals.items():
        delivery.require((indexed[key]['rule'],indexed[key]['description'])==value and
            (errors[key]['Name'],errors[key]['Description'])==value,'Changed literal family/package rule: '+key)
    mapped=package.SOURCE['layer_map'];metadata=json.loads(delivery.checked(ROOT/mapped['path'],mapped['sha256']))
    installed=package.SOURCE['installed_map'];xml=ET.fromstring(delivery.checked(ROOT/installed['path'],installed['sha256']))
    delivery.require(metadata['sources']['installed']['sha256']==installed['sha256'],'Changed installed map provenance.')
    package_bindings={}
    for name,pair in package.LAYERS.items():
        found=[r for r in metadata['layers'] if tuple(r['pair'])==pair and
               any(a['name']==name and a['purpose']=='drawing' and a['source']=='installed' for a in r['aliases'])]
        entries=[r for r in xml.iter('properties') if r.findtext('name')==name+'.drawing - %s/%s'%pair]
        delivery.require(len(found)==len(entries)==1 and entries[0].findtext('source')=='%s/%s@1'%pair,
                         'Changed installed package drawing purpose: '+name)
        package_bindings[name]=dict(metadata=found[0],name=entries[0].findtext('name'),source=entries[0].findtext('source'))
    delivery.require('areaid.mt{81:10},areaid module cut' in raw['docs/rules/layers/table-c4b-layer-description.csv'].decode(),
                     'Changed module-cut definition.')
    return dict(family_source=family.SOURCE,package_source=package.SOURCE,
        mandatory_device=dict(record=matches[0][0],row=matches[0][1]),family_layer_guards=bindings,
        bond_pad_definition=definitions['bondPad'],package_drawings=package_bindings,
        bindings={key:indexed[key] for key in literals},interpretation=[family.SCOPE,package.SCOPE],
        unresolved='Present RF devices require fixed-layout model mapping and Table H5. Other pad variants, generated operands, frame construction, density and pin spacing remain open.')


def build(workspace=None,case=None,progress=None):
    workspace=Path(workspace or ROOT.parents[1]).resolve()
    previous=json.loads(delivery.checked(ROOT/PREVIOUS,PREVIOUS_SHA))
    fresh=previous_review.build(workspace,case,progress)
    catalog=json.loads((ROOT/delivery.queue.CATALOG).read_bytes())
    with TemporaryDirectory() as td:
        folder=Path(td)/'inputs';delivery.fixture.unpack(delivery.fixture.BUNDLE,folder)
        proof=source_proof(folder/'sources',catalog)
    for row in fresh['cases']:
        original=delivery.pick(previous,row['case'])
        delivery.require(row['gds_sha256']==original['gds_sha256'] and row['counts']==original['counts'],
                         'Fresh replay differs from the seal baseline.')
        path=workspace/'outputs/sky130-application-boundary-v1/linux'/row['case']/'sky130-pin-export/final.gds'
        for name,checks in (('family_targets',family),('package_boundaries',package)):
            report=checks.audit(path);checks.evaluate(report,row['gds_sha256'],row['top'])
            delivery.require(all(r['disposition']=='absent-operand' for r in report['rows']),'Reference family/package subject changed.')
            row['rows']=delivery.apply_rows(row['rows'],report['rows'],catalog,name,row['provenance'])
            row['measurements'][name]=report
        row['counts']=dict(Counter(r['disposition'] for r in row['rows']))
        row['remaining_batches']=delivery.queue.partition([r for r in row['rows'] if r['disposition']=='unreviewed'])
        if progress:progress(dict(case=row['case'],stage='family-package-replayed',counts=row['counts']))
    fresh.update(status='corrected-catalog-family-package-reviewed',predecessor=dict(path=PREVIOUS,sha256=PREVIOUS_SHA))
    fresh['proofs']['family_package']=proof
    for path in (Path(__file__),Path(family.__file__),Path(package.__file__),Path(package.geometry.__file__),
                 ROOT/'tests/test_sky130_family_package.py',ROOT/package.SOURCE['installed_map']['path']):
        fresh['source_files'][path.relative_to(ROOT).as_posix()]=delivery.sha(path)
    fresh['source_files']=dict(sorted(fresh['source_files'].items()))
    fresh['scope']+=' Thirty-five low-Vt RF and three explicit bondpad targets are absent with required-drawing and intent guards. Five package crossing checks are implemented; their reference targets are absent.'
    return fresh


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--workspace',type=Path)
    p.add_argument('--case',choices=delivery.queue.CASES);p.add_argument('--output',type=Path,default=OUTPUT)
    p.add_argument('--check',action='store_true');a=p.parse_args()
    raw=(json.dumps(build(a.workspace,a.case,lambda r:print(json.dumps(r),flush=True)),indent=2,ensure_ascii=False)+'\n').encode()
    if a.check:delivery.require(a.output.read_bytes()==raw,'Saved family/package review differs.')
    else:a.output.write_bytes(raw)
