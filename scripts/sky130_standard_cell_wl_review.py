"""Bind only explicit W/L catalog records to the published standard-cell exception.

This exact-reference review authenticates the captured HD library, compares all
shapes in every gate/poly/SC-bearing master, and checks instance-level gate
geometry against the retained native census. It does not qualify RF recognition,
RF fixed layouts, arbitrary user-created standard-cell markers or missing MRGA
limits. Dummy-poly absence is a separate, conservative all-purpose label census.
"""
import argparse
from collections import Counter
from copy import deepcopy
import csv
import io
import json
from pathlib import Path
from tempfile import TemporaryDirectory

import klayout.db as k
from scripts import sky130_catalog_queue as queue
from scripts import sky130_grid_geometry as grid
from scripts import check_sky130_filled_replay as fixture
from scripts.sky130_global_geometry import LAYER_MAP_PATH
from scripts.sky130_rule_inventory import validate_unreviewed, manual_rows

ROOT = queue.ROOT
OUTPUT = ROOT/'docs/validation/sky130-standard-cell-wl-2026-10-15.json'
PREVIOUS = 'docs/validation/sky130-local-hv-2026-10-15.json'
PREVIOUS_SHA = '8056cb07c88e58be1fff098881c444e204ae85b53dc21bc570a35558e0c5de9a'
NATIVE = 'docs/validation/sky130-device-intent-2026-10-14.json'
NATIVE_SHA = 'c8dc8265a41da92a9a8b66f6fad116b70f52e204f8460606fbb2da19459618b5'
INVENTORY = 'docs/qualification/sky130-rule-inventory.json'
PARENT = 'docs/rules/periphery/p028-poly_dotdash.csv'
C3 = 'docs/rules/layers/table-c3-device-lvs-other.csv'
SC_DESCRIPTION = 'docs/rules/layers/table-c4b-layer-description.csv'
LIBRARY = 'sky130hd/gds/sky130_fd_sc_hd.gds'
LIBRARY_SHA = '15240e34c50e42419336c0f3f498aaeac1e1e403c62134c0eee088225b69dc13'
LIBRARY_BYTES = 4182250
INPUTS = dict(
    counter='1bb2a7ef2a1db3d000a68c429cee82807eaff828d646c5d127666adb5a0b3991',
    uart='ecdf75aa48f65ad8ca837703cdadc93b51d1503ea522f6e4bc0d3893bf3be660',
    apb='50c4418df21f2ed9539a340b16e36b0417b885651d3c1ca519542abcfb809a77')
WL_IDS = tuple('r'+s for s in '''546 547 548 549 551 552 553 555 556 558 559
560 561 562 563 564 565 566 567 569 570 571 572 573 574 576 577 578 579 580
582 583 584 585 586 587 588 589 590 591 592 593 594 595 596 597 598 599 600
601 602 603 604 606 607 608 609 610 611 612 614 615 616 617 618 619 620 621
622 624 625 626 627 628 629 630 631 632 633 634 635 636 637 638 639 640 641
642 643 644'''.split())
DUMMY_IDS = tuple('r'+str(i) for i in range(538,543))
EXEMPT = 'standard-cell-wl-exempt'
LAYERS = dict(diff=(65,20), poly=(66,20), sc=(81,4), nwell=(64,20))
DEFINITIONS = {'gate':'poly AND diff', 'nfet':'Gate NOT  nwell',
               'pfet':'Gate AND nwell',
               'dummy_poly':'poly overlapping text "dummy_poly" (written using text.dg)'}
PARENT_TEXT = ("All FETs would be checked for W/Ls as documented in spec 001-02735  "
               "(Exempt FETs that are pruned; exempt for W/L's inside :drc_tag:`areaid.sc` "
               "and inside cell name scs8*decap* and listed in the MRGA as a decap only W/L)")


def source_proof(source, catalog, inventory):
    queue.validate_catalog(catalog); validate_unreviewed(inventory)
    names = (PARENT,C3,SC_DESCRIPTION,'docs/rules/errors.csv','docs/rules/gds_layers.csv')
    files = {}
    for name in names:
        raw = (Path(source)/name).read_bytes()
        if queue.sha(raw) != inventory['source_files'][name]['sha256']:
            raise ValueError('Changed standard-cell source: '+name)
        files[name] = queue.sha(raw)
    parents = list(manual_rows((Path(source)/PARENT).read_bytes(),PARENT))
    known = {r['id']:r for r in inventory['rule_rows']}
    for row in parents:
        if any(row[key]!=known[row['id']][key] for key in ('rule','description','record','flags','value','unit')):
            raise ValueError('Changed standard-cell parent binding.')
    if parents[0]['rule']!='poly.X.1' or parents[0]['description']!=PARENT_TEXT or parents[1]['rule']!='poly.X.1a':
        raise ValueError('Changed published W/L or dummy-poly requirement.')
    definitions = {r['Name']:r['Defining algorithm'] for r in csv.DictReader(io.StringIO(
        (Path(source)/C3).read_text(encoding='utf-8')))}
    if any(definitions.get(name)!=text for name,text in DEFINITIONS.items()):
        raise ValueError('Changed gate or dummy-poly definition.')
    sc = [r for r in csv.reader(io.StringIO((Path(source)/SC_DESCRIPTION).read_text(encoding='utf-8')))
          if r and r[0]=='areaid.sc{81:4}']
    if len(sc)!=1 or sc[0][3]!='Cells in the standard cell library (over standard cell IP blocks only) .':
        raise ValueError('Changed standard-cell identifier purpose.')
    grid.layer_metadata()
    layers={tuple(row['pair']):row['aliases'] for row in json.loads(LAYER_MAP_PATH.read_bytes())['layers']}
    aliases={}
    for name,pair in LAYERS.items():
        expected=('areaid.sc','identifier') if name=='sc' else (name,'drawing, text' if name in ('diff','poly') else 'drawing')
        matches=[a for a in layers[pair] if (a['name'],a['purpose'])==expected and a['source']=='published']
        if len(matches)!=1:raise ValueError('Changed published standard-cell layer purpose.')
        aliases[name]=dict(pair=list(pair),**matches[0])
    indexed = {r['id']:r for r in catalog['rows']}
    explicit = {r['id'] for r in catalog['rows'] if 'device has an invalid W/L. Please see MRGA' in r['description']}
    if explicit!=set(WL_IDS) or len(WL_IDS)!=90 or len(set(WL_IDS))!=90:
        raise ValueError('Changed exact W/L catalog set.')
    bindings = {}
    for ids, parent, spelling in ((WL_IDS,parents[0],'poly.x.1'),(DUMMY_IDS,parents[1],'poly.x.1a')):
        for key in ids:
            row = indexed[key]
            if row['rule']!=spelling: raise ValueError('Changed exact W/L catalog spelling.')
            bindings[key] = dict(rule=row['rule'],description=row['description'],
                parent={key:parent[key] for key in ('id','rule','source','source_sha256','record')})
    return dict(files=files,definitions=DEFINITIONS,standard_cell_layer=sc[0],aliases=aliases,
        layer_map_sha256=queue.sha(LAYER_MAP_PATH.read_bytes()),bindings=bindings,
        interpretation='Use the areaid.sc standard-cell W/L exception only for unchanged masters from the captured HD library. '
                       'No pruned-FET, scs8 decap/MRGA or Table H3 exception is used. This is not an RF-recognition or fixed-layout exception.')


def load_library(folder, case):
    folder = Path(folder); raw = (folder/'input.json').read_bytes()
    if queue.sha(raw)!=INPUTS[case]: raise ValueError('Changed captured job input.')
    platform = json.loads(raw)['project']['digital']['platform']
    expected = dict(path=LIBRARY,sha256=LIBRARY_SHA,bytes=LIBRARY_BYTES)
    matches = [r for r in platform['files'] if r['path']==LIBRARY]
    if platform['name']!='sky130hd' or matches!=[expected]:
        raise ValueError('Captured job does not bind the expected HD library.')
    path = folder/'platform'/LIBRARY; library_raw = path.read_bytes()
    if queue.sha(library_raw)!=LIBRARY_SHA or len(library_raw)!=LIBRARY_BYTES:
        raise ValueError('Changed captured standard-cell library.')
    layout = k.Layout(); layout.read(str(path))
    return layout, dict(input_sha256=INPUTS[case],platform=platform['name'],
                       revision=platform['revision'],library=expected)


def signature(cell, layout):
    # Compare every nonempty purpose, including text and device/well markers.
    return sorted((layout.get_info(i).layer,layout.get_info(i).datatype,
                   sorted(s.to_s() for s in cell.shapes(i).each()))
                  for i in layout.layer_indexes() if not cell.shapes(i).is_empty())


def measure(layout, library):
    diagnostic = grid.check(layout)
    if any(r['violations'] for r in diagnostic['checks'] if r['rule'].startswith('profile.')):
        raise ValueError('Unsupported geometry for standard-cell W/L review.')
    if abs(library.dbu-layout.dbu)>1e-12:
        raise ValueError('Different standard-cell library database unit.')
    top=layout.top_cell(); verified={}; cache={}; visiting=set()
    indices={name:layout.layer(*pair) for name,pair in LAYERS.items()}

    def visit(index):
        if index in visiting: raise ValueError('Cyclic layout hierarchy.')
        if index in cache: return cache[index]
        visiting.add(index); cell=layout.cell(index)
        local=k.Region(cell.shapes(indices['diff'])) & k.Region(cell.shapes(indices['poly']))
        local.merge(); counts=Counter(); instances=list(cell.each_inst())
        relevant=any(not cell.shapes(indices[name]).is_empty() for name in ('diff','poly','sc'))
        if relevant:
            master=library.cell(cell.name)
            if master is None or instances or list(master.each_inst()) or signature(cell,layout)!=signature(master,library):
                raise ValueError('Untrusted or changed standard-cell master: '+cell.name)
            if not (local-k.Region(cell.shapes(indices['sc']))).is_empty():
                raise ValueError('Gate outside its own trusted standard-cell marker.')
            counts[cell.name]=1
            verified[cell.name]=dict(gates=local.count(),all_shapes_sha256=queue.sha(
                json.dumps(signature(cell,layout),separators=(',',':')).encode()))
        combined=local.dup()
        for instance in instances:
            child, child_counts=visit(instance.cell_index)
            for transform in instance.cell_inst.each_trans():
                combined.insert(child.transformed(transform))
            counts.update({name:n*instance.size() for name,n in child_counts.items()})
        combined.merge();visiting.remove(index);cache[index]=(combined,counts)
        return cache[index]

    reconstructed,instances=visit(top.cell_index())
    region=lambda name:k.Region(top.begin_shapes_rec(indices[name])).merged()
    gates=(region('diff') & region('poly')).merged(); nwell=region('nwell')
    weighted=sum(verified[name]['gates']*count for name,count in instances.items())
    if gates.is_empty() or not (gates^reconstructed).is_empty() or gates.count()!=weighted:
        raise ValueError('Gate union or count differs from trusted leaf-instance geometry.')
    if not (gates-region('sc')).is_empty():
        raise ValueError('Uncovered gate in final layout.')
    nfet=(gates-nwell).merged();pfet=(gates & nwell).merged()
    if nfet.count()+pfet.count()!=gates.count():
        raise ValueError('A gate straddles a well boundary.')
    dummy=0
    for index in layout.layer_indexes():
        iterator=top.begin_shapes_rec(index)
        while not iterator.at_end():
            shape=iterator.shape()
            if shape.is_text() and shape.text.string.strip().casefold()=='dummy_poly': dummy+=1
            iterator.next()
    return dict(top=top.name,gates=gates.count(),nfet_gates=nfet.count(),pfet_gates=pfet.count(),
        weighted_library_gates=weighted,gates_outside_sc=0,gate_union_matches_library_instances=True,
        dummy_poly_labels=dummy,
        masters=[dict(name=name,instances=instances[name],**verified[name]) for name in sorted(verified)],
        scope='All diff/poly/SC-bearing reachable cells must be unchanged HD-library leaves. '
              'Fresh global gate geometry equals the transformed library-instance union. '
              'Dummy-poly labels are counted conservatively on every layer purpose.')


def decisions(measured, native, bindings):
    expected={'sky130_fd_pr__nfet_01v8':measured['nfet_gates'],
              'sky130_fd_pr__pfet_01v8_hvt':measured['pfet_gates']}
    allowed=set(expected)|{'sky130_fd_pr__diode_pw2nd_05v5','sky130_fd_pr__res_generic_po'}
    models=native['native_models']; prior=native['measurement']
    if (any(type(v)is not int or v<0 for v in models.values()) or set(models)-allowed or
            any(models.get(name,0)!=count for name,count in expected.items()) or
            any(prior[name]!=measured[name] for name in ('gates','nfet_gates','pfet_gates')) or
            prior['straddling_gates']!=0 or measured['gates']<=0 or measured['gates_outside_sc']!=0 or
            measured['weighted_library_gates']!=measured['gates'] or
            measured['gate_union_matches_library_instances'] is not True):
        raise ValueError('Fresh trusted standard-cell geometry disagrees with the retained native census.')
    if type(measured['dummy_poly_labels'])is not int or measured['dummy_poly_labels']<0:
        raise ValueError('Invalid dummy-poly label census.')
    if set(bindings)!=set(WL_IDS)|set(DUMMY_IDS): raise ValueError('Incomplete exact source binding set.')
    return [dict(id=key,disposition=EXEMPT if key in WL_IDS else (
                     'absent-operand' if measured['dummy_poly_labels']==0 else 'unreviewed'),
                 binding=bindings[key],
                 reason=('Every physical FET gate is within its unchanged, authenticated HD standard-cell marker; '
                         'the explicit W/L exception applies. Other device requirements remain separate.'
                         if key in WL_IDS else
                         'No normalized dummy_poly label exists on any layer purpose; the C3 selected subject is absent.'
                         if measured['dummy_poly_labels']==0 else 'A dummy_poly label exists; measure its selected geometry.'))
            for key in (*WL_IDS,*DUMMY_IDS)]


def apply_decisions(rows, changes, catalog):
    if len(changes)!=95 or {c['id'] for c in changes}!=set(WL_IDS)|set(DUMMY_IDS):
        raise ValueError('Missing, duplicate or unrelated W/L review decision.')
    result=deepcopy(rows);indexed={r['id']:r for r in result}
    for change in changes:
        row=indexed[change['id']]
        expected=EXEMPT if row['id'] in WL_IDS else 'absent-operand'
        if row['disposition']!='unreviewed' or change['disposition']!=expected:
            raise ValueError('Overlapping or unsupported standard-cell decision.')
        row.update(change)
    queue.validate_rows(result,catalog)
    return result


def build(capture_root=None):
    capture_root=Path(capture_root) if capture_root else ROOT.parents[1]/'outputs/sky130-filled-electrical-v1'
    reader=queue.RetainedReader();catalog,baselines=queue.reconstruct(reader)
    previous=reader.read(PREVIOUS,PREVIOUS_SHA);native=reader.read(NATIVE,NATIVE_SHA)
    for data in (previous,native):
        for name,digest in data.get('inputs',{}).items():reader.read(name,digest)
        if 'predecessor' in data:reader.read(data['predecessor']['path'],data['predecessor']['sha256'])
    inventory=reader.read(INVENTORY);cases=[];batches=None
    with TemporaryDirectory() as td:
        folder=Path(td)/'inputs';manifest=fixture.unpack(fixture.BUNDLE,folder)
        proof=source_proof(folder/'sources',catalog,inventory)
        for entry in manifest['cases']:
            name=entry['case'];before=next(c for c in baselines if c['case']==name)
            last=next(c for c in previous['cases'] if c['case']==name)
            device=next(c for c in native['cases'] if c['case']==name)['execution']
            if not before['gds_sha256']==last['gds_sha256']==device['gds_sha256']==entry['gds_sha256']:
                raise ValueError('Changed retained/reference/native layout identity.')
            rows=queue.apply_decisions(before['rows'],last['new_error_decisions'],catalog)
            if dict(Counter(r['disposition'] for r in rows))!=last['error_counts']:
                raise ValueError('Latest retained catalog counts do not reconstruct.')
            library,provenance=load_library(capture_root/name/'finish',name)
            layout=k.Layout();layout.read(str(folder/entry['gds']));measured=measure(layout,library)
            if measured['top']!=entry['top']:raise ValueError('Changed reference top cell.')
            changes=decisions(measured,device,proof['bindings']);rows=apply_decisions(rows,changes,catalog)
            current=queue.partition([r for r in rows if r['disposition']=='unreviewed'])
            if batches is not None and batches!=current:raise ValueError('Reference work queues differ.')
            batches=current
            cases.append(dict(case=name,gds_sha256=entry['gds_sha256'],library_provenance=provenance,
                measurement=measured,native_census=dict(path=NATIVE,sha256=NATIVE_SHA,
                    native_ext_sha256=device['native_ext_sha256'],models=device['native_models']),
                new_error_decisions=changes,error_counts=dict(Counter(r['disposition'] for r in rows)),
                periphery_counts=last['periphery_counts'],open_periphery=last['open_periphery']))
    sources=[Path(__file__),Path(grid.__file__),Path(queue.__file__),Path(fixture.__file__),
             ROOT/'tests/test_sky130_standard_cell_wl.py']
    return dict(schema=1,chunk=6,status='exact-hd-standard-cell-wl-exception-reviewed',qualified=False,chunk_complete=False,
        inputs=dict(sorted(reader.digests.items())),source_files={p.relative_to(ROOT).as_posix():queue.sha(p.read_bytes()) for p in sources},
        bundle=dict(path=fixture.BUNDLE.relative_to(ROOT).as_posix(),sha256=fixture.BUNDLE_SHA256),
        proof=proof,cases=cases,
        remaining_batches=[dict(id=b['id'],count=b['count'],next_action=b['next_action'],ids=[r['id'] for r in b['records']]) for b in batches],
        scope='Ninety explicit invalid-W/L catalog records use the published areaid.sc exception on the exact three captured HD references. '
              'They are recorded as explicit exemptions, not executed numerical W/L checks. Five dummy-poly subjects are absent. '
              'All 60 RF fixed-layout dimensions and other device-recognition requirements remain open. '
              'No new extraction, application check, nonstandard-device qualification or foundry acceptance is claimed.')


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--check',action='store_true')
    parser.add_argument('--output',type=Path,default=OUTPUT);args=parser.parse_args()
    raw=(json.dumps(build(),indent=2,ensure_ascii=False)+'\n').encode()
    if args.check:
        if args.output.read_bytes()!=raw:raise ValueError('Saved standard-cell review differs.')
    else:args.output.write_bytes(raw)
    print(json.dumps({c['case']:c['error_counts'] for c in json.loads(raw)['cases']}))
