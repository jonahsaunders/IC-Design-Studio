"""Read native GDS/netlists directly; no Studio runner/auditor imports."""
import argparse, hashlib, json, pathlib, re, tempfile, zipfile
import klayout.db as k
SIZES = {(0.5, 0.5), (0.5, 20), (20, 0.5), (2, 7), (7, 2)}
MODELS = {'rsil', 'rppd', 'rhigh'}
FAULTS = {'terminal-open', 'body-open', 'terminal-short', 'reference-width', 'reference-model', 'missing-via'}

def require(condition, message='Evidence requirement failed'):
    if not condition:
        raise ValueError(message)

def strict_json(data):

    def pairs(items):
        result = {}
        for key, value in items:
            require(key not in result, 'Duplicate JSON key: ' + key)
            result[key] = value
        return result

    def invalid(value):
        raise ValueError('Non-finite JSON constant: ' + value)
    return json.loads(data, object_pairs_hook=pairs, parse_constant=invalid)

def audit(read):
    layouts = []

    def js(name):
        return strict_json(read(name))

    def stream(name):
        with tempfile.TemporaryDirectory() as tmp:
            path = pathlib.Path(tmp) / 'audit.gds'
            path.write_bytes(read(name))
            ly = k.Layout()
            ly.read(str(path))
        require(ly.dbu == 0.001 and len(ly.top_cells()) == 1, 'Evidence requirement: ly.dbu == 0.001 and len(ly.top_cells()) == 1')
        layouts.append(ly)
        cell = ly.top_cell()
        cell.flatten(True)
        regions = {}
        labels = {}
        for index in ly.layer_indexes():
            info = ly.get_info(index)
            pair = (info.layer, info.datatype)
            reg = k.Region(cell.begin_shapes_rec(index)).merged()
            if not reg.is_empty():
                regions[pair] = reg
            for shape in cell.shapes(index).each():
                if shape.is_text() and shape.text.string in ('R1', 'R2', 'B'):
                    text = shape.text
                    require(text.string not in labels, 'Duplicate interface label')
                    labels[text.string] = (pair, [text.x, text.y], text.trans.angle)
        return (regions, labels)

    def component(region, point):
        selected = [v for v in region.each() if v.inside(k.Point(*point))]
        require(len(selected) == 1, 'Evidence requirement: len(selected) == 1')
        return k.Region(selected[0])

    def device(name, model, w, l, opened=None):
        rows = [v.split() for v in read(name).decode().splitlines() if re.match('(?i)^x\\S+\\s', v)]
        require(len(rows) == 1 and rows[0][4] == model, 'Evidence requirement: len(rows) == 1 and rows[0][4] == model')
        row = rows[0]
        params = dict((v.split('=', 1) for v in row[5:] if '=' in v))
        require(params['w'].endswith('u') and float(params['w'][:-1]) == w, "Evidence requirement: params['w'].endswith('u') and float(params['w'][:-1]) == w")
        require(params['l'].endswith('u') and float(params['l'][:-1]) == l, "Evidence requirement: params['l'].endswith('u') and float(params['l'][:-1]) == l")
        if opened == 'R1':
            require(row[1] not in ('R1', 'R2', 'B') and row[2:4] == ['R2', 'B'], "Evidence requirement: row[1] not in ('R1', 'R2', 'B') and row[2:4] == ['R2', 'B']")
        elif opened == 'B':
            require(set(row[1:3]) == {'R1', 'R2'} and row[3] not in ('R1', 'R2', 'B'), "Evidence requirement: set(row[1:3]) == {'R1', 'R2'} and row[3] not in ('R1', 'R2', 'B')")
        elif opened == 'short':
            require(row[1:4] == ['R2','R2','B'], 'Actual resistor terminals are not shorted')
        else:
            require(set(row[1:3]) == {'R1', 'R2'} and row[3] == 'B', "Evidence requirement: set(row[1:3]) == {'R1', 'R2'} and row[3] == 'B'")
        return row[1:4]
    final = js('landing-final-v2/qualification.json')
    legacy = js('legacy-final-v2/qualification.json')
    raw = js('raw-vias1/qualification.json')
    require(final['status'] == legacy['status'] == 'PASS' and raw['status'] == 'FAIL', "Evidence requirement: final['status'] == legacy['status'] == 'PASS' and raw['status'] == 'FAIL'")
    require(all((v['qualified'] is False and v['chunk_complete'] is False for v in (final, legacy, raw))), 'Producer scope flags differ')
    require(all((v['implementation_unchanged'] for v in (final, legacy, raw))), "Evidence requirement: all((v['implementation_unchanged'] for v in (final, legacy, raw)))")
    require({tuple((v['model'], v['width_um'], v['length_um'])) for v in final['cases']} == {(m, w, l) for m in MODELS for w, l in SIZES}, "Evidence requirement: {tuple((v['model'], v['width_um'], v['length_um'])) for v in final['cases']} == {(m, w, l) for m in MODELS for w, l in SIZES}")
    require(len(final['cases']) == len(legacy['cases']) == len(raw['cases']) == 15, "Evidence requirement: len(final['cases']) == len(legacy['cases']) == len(raw['cases']) == 15")
    require(sum((v['status'] == 'FAIL' for v in raw['cases'])) == 6, "Evidence requirement: sum((v['status'] == 'FAIL' for v in raw['cases'])) == 6")
    require(all((v['width_um'] == 0.5 for v in raw['cases'] if v['status'] == 'FAIL')), "Evidence requirement: all((v['width_um'] == 0.5 for v in raw['cases'] if v['status'] == 'FAIL'))")
    legal = controls = via_controls = body_controls = 0
    details = []
    for row in final['cases']:
        require(row['status'] == 'PASS' and len(row['layouts']) == 2 and (len(row['faults']) == 6), "Evidence requirement: row['status'] == 'PASS' and len(row['layouts']) == 2 and (len(row['faults']) == 6)")
        require({v['name'] for v in row['faults']} == FAULTS, 'Exact six fault names required')
        prefix = 'landing-final-v2/' + row['name'] + '/'
        model = row['model']
        w = row['width_um']
        l = row['length_um']
        native, _ = stream(prefix + 'generator/coupon.gds')
        baseline, labels = stream(prefix + 'baseline-0.gds')
        baseline_labels=labels
        require(set(native) == set(baseline), 'Evidence requirement: set(native) == set(baseline)')
        require(all(((native[key] ^ baseline[key]).is_empty() for key in native if key != (10, 0))), 'Evidence requirement: all(((native[key] ^ baseline[key]).is_empty() for key in native if key != (10, 0)))')
        expected = native[10, 0].dup()
        for poly in native[10, 0].each():
            area = poly.area()
            box = poly.bbox()
            require((k.Region(poly) ^ k.Region(box)).is_empty(), 'Evidence requirement: (k.Region(poly) ^ k.Region(box)).is_empty()')
            if area < 144000:
                denominator = 2 * box.height() * 5
                extension = (144000 - area + denominator - 1) // denominator * 5
                expected.insert(k.Box(box.left - extension, box.bottom, box.right + extension, box.top))
        require((expected.merged() ^ baseline[10, 0]).is_empty(), 'Landing differs from exact independent rule')
        for angle in (0, 90):
            path = prefix + f'physical-{angle}/'
            regions, labels = stream(prefix + f'reimported-{angle}.gds')
            trans=k.Trans(angle//90,False,0,0)
            require(set(regions)==set(baseline) and all((baseline[key].transformed(trans)^regions[key]).is_empty() for key in baseline),'Positive stream mask rotation differs')
            expected_labels={name:(item[0],item[1] if angle==0 else [-item[1][1],item[1][0]],(item[2]+angle//90)%4) for name,item in baseline_labels.items()}
            require(labels==expected_labels,'Positive stream labels do not match exact rotation')
            require(set(labels) == {'R1', 'R2', 'B'} and labels['B'][0] == (8, 2), "Evidence requirement: set(labels) == {'R1', 'R2', 'B'} and labels['B'][0] == (8, 2)")
            require(labels['R1'][0] == labels['R2'][0] == (10, 2), "Evidence requirement: labels['R1'][0] == labels['R2'][0] == (10, 2)")
            lower_components = []
            upper_components = []
            for name in ('R1', 'R2', 'B'):
                point = labels[name][1]
                m1 = component(regions[8, 0], point)
                lower_components.append(m1)
                contacts = regions[6, 0] & m1
                require(not contacts.is_empty(), 'Evidence requirement: not contacts.is_empty()')
                require((contacts - regions[(1, 0) if name == 'B' else (5, 0)]).is_empty(), "Evidence requirement: (contacts - regions[(1, 0) if name == 'B' else (5, 0)]).is_empty()")
                if name != 'B':
                    m2 = component(regions[10, 0], point)
                    upper_components.append(m2)
                    require(m2.area() >= 144000 and (not (regions[19, 0] & m1 & m2).is_empty()), 'Evidence requirement: m2.area() >= 144000 and (not (regions[19, 0] & m1 & m2).is_empty())')
            require(all(((a & b).is_empty() for i, a in enumerate(lower_components) for b in lower_components[i + 1:])), 'Evidence requirement: all(((a & b).is_empty() for i, a in enumerate(lower_components) for b in lower_components[i + 1:]))')
            require((upper_components[0] & upper_components[1]).is_empty(), 'Evidence requirement: (upper_components[0] & upper_components[1]).is_empty()')
            native_report = js(path + 'report.json')
            require(native_report['status'] == 'passed' and native_report['drc_count'] == 0, "Evidence requirement: native_report['status'] == 'passed' and native_report['drc_count'] == 0")
            console = read(path + 'drc/console.log').decode()
            lvs = read(path + 'lvs/lvs.log').decode()
            require('STUDIO_DRC_STYLE drc(full)' in console and 'STUDIO_DRC_COUNT 0' in console and ('Final result: Circuits match uniquely.' in lvs), "Evidence requirement: 'STUDIO_DRC_STYLE drc(full)' in console and 'STUDIO_DRC_COUNT 0' in console and ('Final result: Circuits match uniquely.' in lvs)")
            device(path + 'lvs-extraction/extracted.spice', model, w, l)
            legal += 1
        for fault in row['faults']:
            require(fault['detected'], "Evidence requirement: fault['detected']")
            controls += 1
            fault_path = prefix + fault['name'] + '/'
            fault_report = js(fault_path + 'report.json')
            fault_stages = {v['name']: v['status'] for v in fault_report['stages']}
            require(fault_report['status'] == 'failed' and fault_stages.get('preflight') == 'passed', 'Missing native fault preflight: ' + fault_path)
            extraction_console=read(fault_path+'lvs-extraction/console.log').decode()
            require('STUDIO_MAGIC_COMPLETE' in extraction_console,'Fault extraction did not complete')
            if fault['name']=='terminal-short':
                require(fault_stages.get('lvs_extraction')=='failed' and fault_stages.get('lvs')=='not_run','Missing short-interface rejection')
                require('electrically shorted' in extraction_console,'Native extraction did not identify a terminal short')
                device(fault_path+'lvs-extraction/extracted.spice',model,w,l,'short')
            else:
                require(fault_stages.get('integrity')=='passed' and fault_stages.get('lvs_extraction')=='passed' and fault_stages.get('lvs')=='failed','Missing native LVS fault witness')
                fault_lvs = read(fault_path + 'lvs/lvs.log').decode()
                if fault['name']=='reference-width':
                    require('Property errors were found.' in fault_lvs and ' w circuit1:' in fault_lvs,'Native wrong-width property witness absent')
                else:
                    require('Final result: Circuits match uniquely.' not in fault_lvs and ('do not match' in fault_lvs.lower() or 'failed' in fault_lvs.lower() or 'mismatch' in fault_lvs.lower()), 'Fault log does not prove mismatch: ' + fault_path)
                opened='R1' if fault['name'] in ('terminal-open','missing-via') else 'B' if fault['name']=='body-open' else None
                device(fault_path+'lvs-extraction/extracted.spice',model,w,l,opened)
            fault_console = read(fault_path + 'drc/console.log').decode()
            require('STUDIO_DRC_STYLE drc(full)' in fault_console and 'STUDIO_MAGIC_COMPLETE' in fault_console, 'Fault DRC execution incomplete')
            if fault['name'] not in ('missing-via', 'body-open'):
                continue
            name = fault['name']
            path = prefix + name + '/'
            report = js(path + 'report.json')
            stages = {v['name']: v['status'] for v in report['stages']}
            require(stages['lvs_extraction'] == 'passed' and stages['lvs'] == 'failed', "Evidence requirement: stages['lvs_extraction'] == 'passed' and stages['lvs'] == 'failed'")
            if name == 'missing-via':
                require(stages['drc'] == 'passed', "Evidence requirement: stages['drc'] == 'passed'")
                via_controls += 1
            else:
                body_controls += 1
            mutated, mutated_labels = stream(path + 'original.gds')
            base, base_labels = stream(prefix + 'baseline-0.gds')
            require(mutated_labels == base_labels, 'Evidence requirement: mutated_labels == base_labels')
            changed = (19, 0) if name == 'missing-via' else (6, 0)
            require(set(mutated)-{changed}==set(base)-{changed},'Mutation introduced or removed an unexpected layer')
            require(all(((base[key] ^ mutated.get(key, k.Region())).is_empty() for key in base if key != changed)), 'Evidence requirement: all(((base[key] ^ mutated.get(key, k.Region())).is_empty() for key in base if key != changed))')
            require((mutated.get(changed, k.Region()) - base[changed]).is_empty(), 'Evidence requirement: (mutated.get(changed, k.Region()) - base[changed]).is_empty()')
            removed = base[changed] - mutated.get(changed, k.Region())
            require(not removed.is_empty(), 'Evidence requirement: not removed.is_empty()')
            target = component(base[8, 0], base_labels['R1' if name == 'missing-via' else 'B'][1])
            require((removed - target).is_empty(), (row['name'], name, (removed - target).area(), removed.bbox().to_s(), target.bbox().to_s(), base[changed].area(), mutated.get(changed, k.Region()).area(), list(mutated)))
            require((mutated.get(changed, k.Region()) & target).is_empty(), 'Evidence requirement: (mutated.get(changed, k.Region()) & target).is_empty()')
            device(path + 'lvs-extraction/extracted.spice', model, w, l, 'R1' if name == 'missing-via' else 'B')
        saved = js(prefix + 'saved.icproj')
        ports = saved['cells'][0]['layout_ports']
        require({v['name']: v['layer'] for v in ports} == {'R1': 'Metal2.drawing', 'R2': 'Metal2.drawing', 'B': 'Metal1.drawing'}, "Evidence requirement: {v['name']: v['layer'] for v in ports} == {'R1': 'Metal2.drawing', 'R2': 'Metal2.drawing', 'B': 'Metal1.drawing'}")
        details.append(dict(case=row['name'], native_layouts=2, controls=6))
    require((legal, controls, via_controls, body_controls) == (30, 90, 15, 15), 'Evidence requirement: (legal, controls, via_controls, body_controls) == (30, 90, 15, 15)')
    require({(v['model'],v['width_um'],v['length_um']) for v in legacy['cases']}=={(m,w,l) for m in MODELS for w,l in SIZES},'Legacy finite selection differs')
    legacy_layouts=legacy_controls=0
    for row in legacy['cases']:
        require(row['status']=='PASS' and len(row['layouts'])==2 and len(row['faults'])==5,'Legacy case incomplete')
        require({v['name'] for v in row['faults']}==FAULTS-{'missing-via'},'Legacy fault set differs')
        prefix='legacy-final-v2/'+row['name']+'/';model=row['model'];w=row['width_um'];l=row['length_um']
        base,labels=stream(prefix+'baseline-0.gds')
        for angle in (0,90):
            path=prefix+f'physical-{angle}/';report=js(path+'report.json');require(report['status']=='passed' and report['drc_count']==0,'Legacy native positive failed')
            console=read(path+'drc/console.log').decode();lvs=read(path+'lvs/lvs.log').decode()
            require('STUDIO_DRC_STYLE drc(full)' in console and 'STUDIO_DRC_COUNT 0' in console and 'Final result: Circuits match uniquely.' in lvs and 'Property errors were found.' not in lvs,'Legacy native log failed')
            device(path+'lvs-extraction/extracted.spice',model,w,l);legacy_layouts+=1
            actual,actual_labels=stream(prefix+f'reimported-{angle}.gds');trans=k.Trans(angle//90,False,0,0)
            require(set(actual)==set(base) and all((base[key].transformed(trans)^actual[key]).is_empty() for key in base),'Legacy rotation masks differ')
            expected={name:(item[0],item[1] if angle==0 else [-item[1][1],item[1][0]],(item[2]+angle//90)%4) for name,item in labels.items()}
            require(actual_labels==expected and all(item[0]==(8,2) for item in actual_labels.values()),'Legacy rotation ports differ')
        for fault in row['faults']:
            path=prefix+fault['name']+'/';report=js(path+'report.json');stages={v['name']:v['status'] for v in report['stages']}
            require(report['status']=='failed' and stages.get('preflight')=='passed','Legacy fault preflight incomplete')
            console=read(path+'drc/console.log').decode();extraction=read(path+'lvs-extraction/console.log').decode()
            require('STUDIO_DRC_STYLE drc(full)' in console and 'STUDIO_MAGIC_COMPLETE' in console and 'STUDIO_MAGIC_COMPLETE' in extraction,'Legacy fault native execution incomplete')
            if fault['name']=='terminal-short':
                require(stages.get('lvs_extraction')=='failed' and stages.get('lvs')=='not_run' and 'electrically shorted' in extraction,'Legacy short witness absent')
                device(path+'lvs-extraction/extracted.spice',model,w,l,'short')
            else:
                require(stages.get('integrity')=='passed' and stages.get('lvs_extraction')=='passed' and stages.get('lvs')=='failed','Legacy native mismatch absent')
                lvs=read(path+'lvs/lvs.log').decode()
                if fault['name']=='reference-width':require('Property errors were found.' in lvs and ' w circuit1:' in lvs,'Legacy width property witness absent')
                else:require('Final result: Circuits match uniquely.' not in lvs and any(v in lvs.lower() for v in ('do not match','failed','mismatch')),'Legacy native mismatch log absent')
                device(path+'lvs-extraction/extracted.spice',model,w,l,'R1' if fault['name']=='terminal-open' else 'B' if fault['name']=='body-open' else None)
            legacy_controls+=1
    require((legacy_layouts,legacy_controls)==(30,75),'Legacy native selection incomplete')
    return dict(status='PASS', native_layouts=legal, controls=controls, missing_via_native_lvs_controls=via_controls, independent_body_native_lvs_controls=body_controls, raw_vias1_failed_cases=6, legacy_passed_cases=15,legacy_native_layouts=legacy_layouts,legacy_native_controls=legacy_controls, process=final['process'], qualified=False, chunk_complete=False, cases=details)

def main():
    ap = argparse.ArgumentParser()
    group = ap.add_mutually_exclusive_group(required=True)
    group.add_argument('--root', type=pathlib.Path)
    group.add_argument('--archive', type=pathlib.Path)
    ap.add_argument('--archive-sha256')
    ap.add_argument('--manifest-sha256')
    ap.add_argument('--output', required=True, type=pathlib.Path)
    args = ap.parse_args()
    if args.archive:
        require(args.archive_sha256 and args.manifest_sha256, 'External expected archive and manifest hashes required')
        require(hashlib.sha256(args.archive.read_bytes()).hexdigest() == args.archive_sha256, 'Archive hash differs')
        with zipfile.ZipFile(args.archive) as z:
            names = z.namelist()
            require(len(names) == len(set(names)), 'Duplicate ZIP member')
            manifest_bytes = z.read('manifest.json')
            require(hashlib.sha256(manifest_bytes).hexdigest() == args.manifest_sha256, 'Manifest hash differs')
            manifest = strict_json(manifest_bytes)
            require(manifest['format'] == 'sha256-content-addressed-files', 'Unknown archive format')
            files = manifest['files']
            expected_objects = {}
            for name, info in files.items():
                require(not name.startswith('/') and '\\' not in name and ('..' not in pathlib.PurePosixPath(name).parts), 'Unsafe manifest path')
                require(re.fullmatch('[0-9a-f]{64}', info['sha256']) is not None and type(info['bytes']) is int and (info['bytes'] >= 0), 'Invalid object metadata')
                h = info['sha256']
                require(h not in expected_objects or expected_objects[h] == info['bytes'], 'Conflicting object length')
                expected_objects[h] = info['bytes']
            require(set(names) == {'manifest.json', *('objects/' + h for h in expected_objects)}, 'ZIP object inventory differs')
            for h, size in expected_objects.items():
                blob = z.read('objects/' + h)
                require(len(blob) == size and hashlib.sha256(blob).hexdigest() == h, 'Corrupt declared object')

            def read(name):
                info = files[name]
                data = z.read('objects/' + info['sha256'])
                require(hashlib.sha256(data).hexdigest() == info['sha256'] and len(data) == info['bytes'], "Evidence requirement: hashlib.sha256(data).hexdigest() == info['sha256'] and len(data) == info['bytes']")
                return data
            result = audit(read)
        result['archive_sha256'] = hashlib.sha256(args.archive.read_bytes()).hexdigest()
    else:
        result = audit(lambda name: (args.root / name).read_bytes())
    result['auditor_sha256'] = hashlib.sha256(pathlib.Path(__file__).read_bytes()).hexdigest()
    args.output.write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps(result))
if __name__ == '__main__':
    main()
