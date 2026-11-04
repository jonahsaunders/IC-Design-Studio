"""Recompute portable chunk-5 evidence from retained native application outputs.

Run on Windows and Linux with --workspace pointing at the capture workspace.
This audits completed results; it never turns unfinished simulations into passes.
"""
import argparse
import hashlib
import json
import math
import re
from pathlib import Path
import sys
import xml.etree.ElementTree as ET
import zipfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from icstudio.digital_ihp_geometry import compare_native
from icstudio.digital_reports import timing_report
from scripts.check_ihp_lvs import audit as lvs_audit


def sha(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def read(path):
    return json.loads(Path(path).read_text(encoding='utf-8'))


def audit(workspace, on_reference=lambda row: None):
    root = Path(workspace); rows = []
    for case, revision in [('counter', 2), ('uart', 1), ('apb', 5)]:
        base = root / ('work/hosted-toolchain-qualified/' + (
            'digital-platforms/ihp-sg13g2' if case == 'counter' else 'digital-workloads/ihp-sg13g2/' + case))
        app = root / f'outputs/ihp-application-fill-v1/{case}'
        result = read(app/'result.json'); data = result['digital_result']; artifacts = data['artifacts']
        used = {}

        def capture(path):
            used[path.relative_to(root).as_posix()] = sha(path)
            return read(path)

        def files(folder, entries):
            for name, digest in entries.items():
                path = (folder/name).resolve()
                assert path.is_relative_to(folder.resolve()) and sha(path) == digest, str(path)
                used[path.relative_to(root.resolve()).as_posix()] = digest

        capture(app/'result.json'); application = capture(app/'application-audit.json')
        files(app, {v['path']: v['sha256'] for v in artifacts.values()})
        original = capture(base/'finished/result.json')['digital_result']['artifacts']
        for key in ('spef', 'netlist', 'checkpoint', 'def'):
            assert artifacts[key]['sha256'] == original[key]['sha256']
        worker = capture(app/'ihp-fill/verified/record.json')
        files(app/'ihp-fill/verified', worker['files'])
        inventory = read(app/'ihp-fill/inventory.json'); top = inventory['top']
        comparison = compare_native(app/f'ihp-fill/verified/original-native/{top}.ext',
                                    app/f'ihp-fill/verified/filled-native/{top}.ext', inventory)
        assert comparison == worker['capacitance']
        markers = len(ET.parse(app/'ihp-fill/verified/full.lyrdb').findall('./items/item'))
        assert markers == worker['markers']
        supplement = capture(app/'ihp-fill/verified/supplemental.json')
        invariance = capture(root/f'outputs/ihp-signal-invariance-v{revision}/{case}/record.json')
        inv_dir = root/f'outputs/ihp-signal-invariance-v{revision}/{case}'
        files(inv_dir, invariance['files'])
        for entry in invariance['results']:
            source_ext = (root/f'outputs/ihp-conserved-rc-{case}-v3/original/native-original.ext' if entry['engine']=='stock'
                          else root/f'outputs/ihp-same-net-ground-capture-v1/{case}/original/{top}.ext')
            assert sha(source_ext)==entry['source_ext_sha256']
            used[source_ext.relative_to(root).as_posix()]=sha(source_ext)
            assert compare_native(source_ext, inv_dir/entry['engine']/(top+'.ext'), inventory)==entry['capacitance']
        native = root/f'outputs/ihp-signal-lvs-v2/{case}'
        lvs = capture(native/'record.json'); files(native, lvs['files'])
        aliases = read(native/'aliases.json')
        assert lvs_audit(native/'report.lvsdb', top, list(aliases['ports'].values())) == read(native/'audit.json')
        lvs_reference = capture(root/f'outputs/ihp-native-lvs-{case}-v7/record.json')
        assert lvs['reference_record_sha256'] == sha(root/f'outputs/ihp-native-lvs-{case}-v7/record.json')
        assert lvs_reference['source_artifacts']['checkpoint']['sha256'] == original['checkpoint']['sha256']
        lef = capture(root/f'outputs/ihp-export-lef-v1/{case}/record.json')
        files(root/f'outputs/ihp-export-lef-v1/{case}', lef['files'])
        with zipfile.ZipFile(app/'macro.zip') as archive:
            macro = json.loads(archive.read('macro.json'))
            for key, item in macro['artifacts'].items():
                assert hashlib.sha256(archive.read(item['path'])).hexdigest() == item['sha256']
            for key in ('gds', 'lef', 'spef', 'netlist'):
                assert macro['artifacts'][key]['sha256'] == artifacts[key]['sha256']
        assert sha(app/'macro.zip') == lef['macro_sha256']
        used[(app/'macro.zip').relative_to(root).as_posix()] = lef['macro_sha256']
        fields = []
        for path in [root/f'outputs/ihp-corrected-field-projection-v1/{case}/original',
                     root/f'outputs/ihp-signal-field-projection-v1/{case}/filled']:
            record = capture(path/'record.json'); assert not record['errors']
            values = capture(path/'projected.json')
            pairs = {(a, b): v for a, b, v in values}
            assert len(pairs) == len(values) and all(math.isfinite(v) for v in pairs.values())
            fields.append(pairs)
        assert fields[0].keys() == fields[1].keys()
        delta = [abs(fields[0][p]-fields[1][p]) for p in sorted(fields[0])]
        field = dict(status='same-frozen-mesh-roundoff-only', pairs=len(delta),
                     maximum_change_af=max(delta), total_absolute_change_af=math.fsum(delta),
                     minimum_capacitance_af=min(min(d.values()) for d in fields),
                     source_files={p:h for p,h in used.items() if 'field-projection' in p})
        timing_dir = root/f'outputs/ihp-signal-timing-v1/{case}'
        timing = capture(timing_dir/'record.json'); files(timing_dir, timing['files'])
        for run in timing['results']:
            assert timing_report(timing_dir/(run['corner']+'-'+run['state']), require_parasitics=True) == run['timing']
        app_timing = root/f'outputs/ihp-application-timing-v1/{case}'
        timing_result = capture(app_timing/'result.json')
        timing_audit = capture(app_timing/'audit.json')
        files(app_timing, {v['path']:v['sha256'] for v in timing_result['digital_result']['artifacts'].values()})
        assert timing_audit['upstream_result_sha256'] == sha(app/'result.json')
        app_corners = timing_result['digital_result']['timing']['corners']
        # CTS adds load-only inverters with an intentionally unconnected Y pin.
        # Prove the exact empty connections from the final structural netlist;
        # a connected but unannotated wire is never accepted.
        netlist=(app/artifacts['netlist']['path']).read_text()
        disconnected=[f'clkload{i}/Y' for i in range(dict(counter=0,uart=1,apb=6)[case])]
        hierarchy=read(app_timing/'netlist.json')['modules']
        for name in disconnected:
            instance,pin=name.split('/')
            match=re.search(r'\b'+re.escape(instance)+r'\s*\((.*?)\);',netlist,re.S)
            assert match and (not re.search(r'\.'+pin+r'\s*\(',match[1]) or re.search(r'\.'+pin+r'\s*\(\s*\)',match[1]))
            cell=hierarchy[top]['cells'][instance]
            assert cell['type']=='sg13g2_inv_1' and not cell['connections'].get(pin) and hierarchy[cell['type']]['ports'][pin]['direction']=='output'
        for corner in app_corners:
            report = timing_report(app_timing/'timing-corners'/corner['corner'], require_parasitics=True)
            assert all(corner[k] == v for k,v in report.items() if k != 'paths')
        equivalent = capture(base/'physical-equivalent/result.json')
        proof = equivalent['digital_result']
        assert proof['artifacts']['netlist']['sha256'] == artifacts['netlist']['sha256']
        files(base/'physical-equivalent', {v['path']:v['sha256'] for v in proof['artifacts'].values()})
        row = dict(case=case, artifacts={key:artifacts[key]['sha256'] for key in ('gds','lef','spef','netlist','checkpoint')},
                   original_artifacts={key:original[key]['sha256'] for key in ('gds','spef','netlist','checkpoint')},
                   application=application, worker=worker, supplement=supplement,
                   physical_checks=data['physical']['checks'], invariance=invariance,
                   lvs=lvs, lvs_label_audit=read(native/'label-audit.json'), lvs_reference=lvs_reference,
                   lef=lef, field=field, timing=timing,
                   application_timing=timing_result['digital_result']['timing'],
                   application_timing_binding=timing_audit,
                   verified_unconnected_outputs=disconnected,
                   formal=dict(status=proof['equivalence']['status'], result_sha256=sha(base/'physical-equivalent/result.json'),
                               netlist_sha256=proof['artifacts']['netlist']['sha256']),
                   evidence_files=used)
        rows.append(row)
        on_reference(row)
    return rows


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--workspace',type=Path,required=True);parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args();assert not args.output.exists()
    partial=args.output.with_suffix('.parts');partial.mkdir(exist_ok=False)
    def preserve(row):
        (partial/(row['case']+'.json')).write_text(json.dumps(row,indent=2)+'\n',encoding='utf-8')
        print(json.dumps(dict(case=row['case'],status='raw-evidence-audited')),flush=True)
    rows=audit(args.workspace,preserve)
    from scripts.check_ihp_fill_closure import validate_reference
    for row in rows:validate_reference(row)
    record=dict(schema=1,status='three-final-ihp-references-audited',system=sys.platform,references=rows,
                references_sha256=hashlib.sha256(json.dumps(rows,sort_keys=True,separators=(',',':')).encode()).hexdigest(),
                auditor_sha256=sha(__file__))
    args.output.write_text(json.dumps(record,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({k:v for k,v in record.items() if k!='references'}),flush=True)


if __name__=='__main__':main()
