"""Independent raw/deck readback for the finite corrected ESD integration batch.

This reader does not import the producer, application emitter, raw reader, or its
comparison routine. It does not establish ESD ratings or physical qualification.
"""
import argparse
import hashlib
import json
import math
import posixpath
import re
from pathlib import Path, PurePosixPath, PureWindowsPath
from datetime import datetime, timezone

PACKAGE = '5315d2d6ad7618047eeeb48a15f81f221e6f42864647208acfb65124ee5c9c7a'
MODEL = 'sky130_fd_pr__esd_nfet_05v0_nvt'
ENGINES = {'86c9ea5f645ca919e305639fa7bdb522355364c424d14e197f1ade617feb3453': '46',
           '820658317b0b54035208da41936fd6871ce924036e5ea4113a4168b821b7fc45': '42',
           '67399d2db139e9a8e7bfd118cab8acfa290bb6db003c996333e55ed682a65d25': '47-linux-corrected'}
FAULTS = ('wrong-multiplicity', 'wrong-gate', 'wrong-body', 'wrong-length')


def require(condition, message):
    if not condition:
        raise ValueError(message)


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def load(path):
    return json.loads(Path(path).read_bytes())


def raw(path, drive, engine, expected_title):
    text = Path(path).read_text(encoding='ascii')
    require(text.count('Values:\n') == 1, 'Missing or duplicate raw plot')
    header, values = text.split('Values:\n', 1)
    def field(name):
        found = re.findall(r'^'+re.escape(name)+r':[ \t]*(.*)$',header,re.M)
        require(len(found) == 1, 'Missing or duplicate raw header: '+name)
        return found[0].strip()
    require(field('Title') == expected_title.lower(), 'Raw execution/case/role title')
    # These are three exact, externally pinned engine profiles. The verified
    # Ubuntu 42 build emits no Command field; 46 emits exactly one. The caller
    # has already bound the actual engine hash, command, timing, deck, raw and
    # console bytes through the execution receipt and trusted full manifest.
    commands = re.findall(r'^Command:[ \t]*(.*)$',header,re.M)
    require(engine in ('42','46','47-linux-corrected'), 'Unreviewed raw engine profile')
    if engine == '46':
        require(len(commands) == 1 and re.fullmatch(r'ngspice-46, Build [^\r\n]+',commands[0].strip()),
                'Raw Windows46 engine identity')
    elif engine == '47-linux-corrected':
        require([v.strip() for v in commands] == ['ngspice-47, Build Sat Oct 17 12:12:53 UTC 2026'],
                'Raw corrected Linux47 engine identity')
    else:
        require(not commands, 'Raw Linux42 must use its reviewed absent-Command profile')
    require(field('Plotname') == ('DC transfer characteristic' if drive == 'dc' else 'AC Analysis'), 'Raw plot identity')
    count = int(field('No. Variables'))
    points = int(field('No. Points'))
    require(25 <= count < 200 and points == (41 if drive == 'dc' else 31), 'Raw dimensions')
    require(field('Flags') == ('real' if drive == 'dc' else 'complex'), 'Raw type')
    require(header.count('Variables:\n') == 1, 'Missing or duplicate raw variable table')
    vars = [line.split() for line in header.split('Variables:\n', 1)[1].splitlines() if line.strip()]
    require(len(vars) == count and [int(v[0]) for v in vars] == list(range(count)), 'Raw variable indices')
    names = [v[1].lower() for v in vars]
    require(names[0] == ('v(v-sweep)' if drive == 'dc' else 'frequency') and
            all(len(v) == 3 or i == 0 and drive != 'dc' and v == ['0','frequency','frequency','grid=3']
                for i,v in enumerate(vars)), 'Raw variable table shape')
    require(len(set(names)) == count, 'Duplicate raw variables')
    lines = [line.split() for line in values.splitlines() if line.strip()]
    require(len(lines) == count * points, 'Truncated or trailing raw data')
    data = {name: [] for name in names}
    for point in range(points):
        for col, name in enumerate(names):
            tokens = lines[point * count + col]
            require(len(tokens) == (2 if col == 0 else 1), 'Raw row shape')
            if col == 0:
                require(tokens[0] == str(point), 'Raw point index')
            parts = tokens[-1].split(',')
            require(len(parts) == (1 if drive == 'dc' else 2), 'Raw scalar type')
            value = complex(*map(float, parts))
            require(math.isfinite(value.real) and (name == 'frequency' or math.isfinite(value.imag)), 'Nonfinite raw value')
            data[name].append(value)
    domain = [i * .03 for i in range(41)] if drive == 'dc' else [1000 * 10 ** (i / 5) for i in range(31)]
    require(all(abs(a.real - b) <= 1e-14 + 1e-9 * abs(b) for a, b in zip(data[names[0]], domain)), 'Wrong analysis domain')
    return data, domain


def staged_models(folder, package, files):
    mapping = load(folder / 'pdk-model-files.json')
    require(len(mapping) == len(set(mapping.values())), 'Ambiguous staged models')
    inverse = {rel: name for name, rel in mapping.items()}
    pattern = re.compile(r'(?im)^[^\S\n]*(\.include|\.inc|\.lib)[^\S\n]+("[^"\n]+"|\x27[^\x27\n]+\x27|[^\s]+)([^\n]*)')
    for name, rel in mapping.items():
        require(rel in files, 'Unpinned staged model')
        expected_name = 'pdk-models/' + hashlib.sha256((rel + '\0' + files[rel]).encode()).hexdigest()[:24] + '.spice'
        require(name == expected_name, 'Staged model name')
        def replace(m):
            if m[1].lower() == '.lib' and not m[3].strip():
                return m[0]
            target = posixpath.normpath(posixpath.join(posixpath.dirname(rel), m[2].strip('"\x27')))
            require(target in inverse, 'Staged dependency closure')
            return m[1] + ' ' + inverse[target] + m[3]
        original = (package / rel).read_text(encoding='utf-8')
        require((folder / name).read_text(encoding='utf-8') == pattern.sub(replace, original), 'Changed staged model: ' + rel)
    return inverse


def analysis_directive(tokens, drive, role):
    if drive == 'dc':
        require(tokens[:2] == ['.dc', 'vg'] and list(map(float, tokens[2:])) == [0., 1.2, .03], 'DC analysis')
    else:
        # Actual application emission spells SI values numerically; the literal
        # independent deck uses SPICE suffixes. Both are exact 31-point domains.
        limits = ['1k','1g'] if role == 'independent' else ['1000','1000000000']
        require(tokens == ['.ac','dec','5',*limits], 'AC analysis')


def model_header_paths(package_sha256):
    """Exact selected package determines headers, never the submitted deck."""
    base = ('libs.tech/ngspice/sky130.lib.spice',
            'libs.tech/ngspice/icstudio-parallel-varactors.spice',
            'libs.tech/ngspice/icstudio-rf-ps2nw/library.spice',
            'libs.tech/ngspice/icstudio-esd-nvt/' + MODEL + '.pm3.spice')
    profiles = {
        PACKAGE: base,
        '125cde7c313ee18a05a7ec5c280d514b99aea521d6b39476e44f486ae494153b': base,
        '0c19e0ea5718a841045b597022d13f2dcb57e35cf8be9757b254fb465f2a35c4':
            base + ('libs.tech/ngspice/icstudio-rf-pw2dn/library.spice',),
    }
    require(package_sha256 in profiles, 'Unreviewed ESD package/header profile')
    return profiles[package_sha256]


def deck(folder, package, files, corner, temp, drive, role):
    inverse = staged_models(folder, package, files)
    path = folder / ('reference.cir' if role == 'independent' else 'input.cir')
    lines = [line.lower().split() for line in path.read_text().splitlines() if line.strip() and not line.lstrip().startswith('*')]
    section = 'tt' if corner == 'nominal' else corner
    paths = model_header_paths(sha(package/'package.json'))
    expected_headers = [ ['.lib', inverse[paths[0]], section] ]
    for rel in paths[1:]:
        expected_headers.append(['.include', inverse[rel]])
    require(lines[:len(expected_headers)] == expected_headers, 'Model selection or ordering')
    actual = lines[len(expected_headers):]
    sources = {}
    transistors = {}
    directives = []
    for tokens in actual:
        name = tokens[0]
        if name.startswith('.'):
            directives.append(tokens)
        elif name.startswith('x'):
            require(name not in transistors, 'Duplicate transistor')
            transistors[name] = tokens
        elif name.startswith('v'):
            require(name not in sources, 'Duplicate source')
            sources[name] = tokens
        else:
            raise ValueError('Unexpected circuit statement')
    require(len(transistors) == 6 and len(sources) == 25, 'Missing or extra device')
    require(sources['vg'] in (['vg', 'sweep', '0', '.8', 'ac', '0'], ['vg', 'sweep', '0', 'dc', '0.8', 'ac', '0']), 'Gate stimulus')
    for i in range(6):
        tag = 'q' + str(i)
        length, copies = (.9, 2., 4.)[i // 2], (1, 3)[i % 2]
        name = ('x' if role == 'independent' else 'x_d') + tag
        tokens = transistors[name]
        nodes = [tag + p for p in 'dgsb']
        if role == 'wrong-gate': nodes[1] = nodes[2]
        if role == 'wrong-body': nodes[3] = nodes[2]
        if role == 'wrong-multiplicity': copies *= 2
        if role == 'wrong-length': length = 4. if length != 4 else 2.
        require(tokens[1:6] == [*nodes, MODEL], 'Model or terminal order')
        pairs = [token.split('=') for token in tokens[6:]]
        require(all(len(p) == 2 for p in pairs) and len({p[0] for p in pairs}) == len(pairs), 'Parameter shape')
        params = {k: float(v) for k, v in pairs}
        require(params == dict(w=10., l=length, nf=1., ad=2.9, **{'as': 2.9}, pd=20.58, ps=20.58, nrd=.029, nrs=.029, sa=0., sb=0., sd=0., m=copies, mult=copies), 'Source parameter equations')
        for p, value in zip('dgsb', (.6, 0., 0., -.15)):
            tokens = sources['v' + tag + p]
            require(tokens[:4] == ['v' + tag + p, tag + p, 'sweep' if p == 'g' else '0', 'dc'] and len(tokens) == 7, 'Voltage source terminals')
            require(float(tokens[4]) == value and tokens[5] == 'ac' and float(tokens[6]) == int(p == drive), 'Voltage source value')
    require(directives[0] == ['.temp', str(temp)], 'Temperature directive')
    require(directives[-1] == ['.end'] and len(directives) == 3, 'Analysis directive count')
    analysis_directive(directives[1], drive, role)


def compare(actual, reference, domain, drive, positive):
    errors = []
    for i in range(6):
        tag = 'q' + str(i)
        per_device = []
        for pin in 'dgsb':
            key = 'i(v' + tag + pin + ')'
            require(key in actual and key in reference, 'Missing terminal current')
            per_device.extend(abs(a-b)/(1e-12+1e-6*abs(b)) for a,b in zip(actual[key], reference[key]))
            for data in (reference, actual) if positive else (reference,):
                vkey = 'v(' + tag + pin + ')'
                require(vkey in data, 'Missing terminal voltage')
                target = domain if pin == 'g' and drive == 'dc' else [dict(d=.6,g=0.,s=0.,b=-.15)[pin] if drive == 'dc' else int(pin == drive)] * len(domain)
                require(all(abs(a-b) <= 1e-10+1e-9*abs(b) for a,b in zip(data[vkey], target)), 'Terminal stimulus not exercised')
        currents = [reference['i(v' + tag + pin + ')'] for pin in 'dgsb']
        for sample in zip(*currents):
            require(abs(sum(sample)) <= 1e-11+1e-6*max(map(abs,sample)), 'Current conservation')
        if drive == 'dc':
            drain = currents[0]
            require(max(v.real for v in drain)-min(v.real for v in drain) > 1e-10, 'Unexercised transfer curve')
        error = max(per_device)
        require(error <= 1 if positive else error > 1, 'Numerical comparison or undetected fault')
        errors.append(error)
    return errors


def native_path(value):
    return PureWindowsPath(value) if re.match(r'^[A-Za-z]:',value) else PurePosixPath(value)


def inventory(root):
    result = {}
    for path in sorted(root.rglob('*')):
        require(not path.is_symlink() and not (hasattr(path,'is_junction') and path.is_junction()), 'Linked evidence artifact')
        if path.is_file() and path != root/'evidence-manifest.json':
            result[path.relative_to(root).as_posix()] = sha(path)
    return result


def execution(child, report, case, role):
    record = load(child/'execution-receipt.json')
    require(record.get('schema') == 1 and record.get('status') == 'PASS' and not record.get('error') and
            record.get('execution_id') == report['execution_id'] and record.get('case') == case and record.get('role') == role,
            'Native execution receipt identity/status')
    raw_name = 'deck.raw' if role == 'independent' else 'result.raw'
    deck_name = 'reference.cir' if role == 'independent' else 'input.cir'
    require(record['deck_filename'] == deck_name and record['raw_filename'] == raw_name and
            record['engine_sha256'] == report['engine_sha256'], 'Native execution receipt inputs')
    command = record['command']
    require(isinstance(command,list) and len(command) == 10 and all(isinstance(v,str) for v in command) and
            command[1:8] == ['-n','-D','filetype=ascii','-D','ngbehavior=hsa','-b','-r'], 'Native command flags')
    engine = native_path(command[0]);origin = native_path(report['execution_root']);directory=origin/case/role
    require(engine.is_absolute() and origin.is_absolute() and command[0] == report['engine'] and
            command[-2:] == [str(directory/raw_name),str(directory/deck_name)] and
            record['cwd'] == str(directory), 'Native command/cwd/original-root binding')
    require(record['timeout_seconds'] == 180 and type(record['elapsed_seconds']) in (int,float) and
            math.isfinite(record['elapsed_seconds']) and record['elapsed_seconds'] >= 0, 'Native elapsed/timeout values')
    start,end = (datetime.fromisoformat(record[k]) for k in ('started_utc','ended_utc'))
    require(start.utcoffset() == end.utcoffset() == timezone.utc.utcoffset(None) and start <= end and
            abs((end-start).total_seconds()-record['elapsed_seconds']) < 1, 'Native execution time interval')
    for name,field in ((deck_name,'deck_sha256'),(raw_name,'raw_sha256'),('engine.log','log_sha256')):
        require(sha(child/name) == record[field], 'Native artifact differs from captured execution: '+name)
    title = 'icstudio-esd-nvt-v2 '+report['execution_id']+' '+case+' '+role
    title = '* '+title if role == 'independent' else '* IC Design Studio / '+title+' / revision 0'
    require((child/deck_name).read_text().splitlines()[0] == title, 'Actual executed deck title')
    return title


def audit(evidence, package, repo, runner, pilot=False, *, expected_report_sha256, expected_manifest_sha256):
    evidence,package,repo,runner=map(Path,(evidence,package,repo,runner))
    require(re.fullmatch('[0-9a-f]{64}',expected_report_sha256) and re.fullmatch('[0-9a-f]{64}',expected_manifest_sha256),
            'Trusted external report/manifest identities required')
    require(sha(evidence/'report.json') == expected_report_sha256 and sha(evidence/'evidence-manifest.json') == expected_manifest_sha256,
            'External acceptance identity differs')
    report = load(evidence / 'report.json')
    require(report.get('schema') == 2 and re.fullmatch('[0-9a-f]{32}',report['execution_id']), 'Versioned execution identity')
    manifest=load(evidence/'evidence-manifest.json')
    require(set(manifest) == {'schema','execution_id','files'} and manifest['schema'] == 1 and manifest['execution_id'] == report['execution_id'] and
            manifest['files'] == inventory(evidence), 'Complete captured evidence inventory differs')
    require(sha(package / 'package.json') == PACKAGE == report['package_sha256'], 'Package identity')
    require(report['status'] == 'PASS' and report['qualified'] is False and report['default_promoted'] is False and report['chunk_complete'] is False, 'Evidence status or scope')
    require(report['runner_sha256'] == sha(runner), 'Runner identity')
    require(report['engine_sha256'] in ENGINES, 'Engine identity')
    expected_sources={p.relative_to(repo).as_posix():sha(p) for base in ('icstudio','scripts') for p in (repo/base).glob('*.py')}
    require(report['source_files'] == expected_sources and {'icstudio/catalog.py','icstudio/engines.py','scripts/qualify_mos_variants.py'} <= expected_sources.keys(),
            'Complete reviewed source names/bytes differ')
    files = load(package / 'package.json')['files']
    for name, expected in files.items():
        require((package/name).resolve().is_relative_to(package.resolve()) and sha(package/name) == expected, 'Changed package asset')
    conditions = [('nominal',27,'dc')] if pilot else [(c,t,'dc') for c in ('nominal','ss','ff','sf','fs') for t in (0,27,85)] + [('nominal',27,p) for p in 'dgsb']
    require(report['conditions'] == [list(c) for c in conditions], 'Declared execution conditions differ')
    require([(c['corner'],c['temperature_c'],c['drive']) for c in report['cases']] == conditions, 'Incomplete or duplicate conditions')
    worst = 0.; faults = 0; points = 0
    for c,t,d in conditions:
        folder = evidence / f'{c}-{t}-{d}'
        record = load(folder/'record.json')
        require(record == report['cases'][conditions.index((c,t,d))] and record['status'] == 'PASS' and not record.get('error'), 'Case status/identity')
        roles = ('application','independent',*FAULTS) if d == 'dc' else ('application','independent')
        data = {}
        for role in roles:
            child = folder/role
            deck(child,package,files,c,t,d,role)
            raw_title = execution(child,report,f'{c}-{t}-{d}',role)
            log = (child/'engine.log').read_text()
            require(f'TEMP = {t:.6f}' in log and 'TNOM = 27.000000' in log and 'Total analysis time' in log, 'Native execution log')
            if role == 'independent':
                require((child/'reference.cir').read_bytes() == (child/'deck-snapshot.cir').read_bytes(), 'Reference execution snapshot')
            data[role],domain = raw(child/('deck.raw' if role == 'independent' else 'result.raw'),d,ENGINES[report['engine_sha256']],raw_title)
        worst = max(worst,*compare(data['application'],data['independent'],domain,d,True))
        for role in roles[2:]:
            compare(data[role],data['independent'],domain,d,False);faults += 6
        points += len(domain)*24
        print(c,t,d,'AUDIT PASS',flush=True)
    return dict(status='PASS',schema=2,execution_id=report['execution_id'],original_execution_root=report['execution_root'],
        cases=len(conditions),devices=6,current_samples=points,fault_device_instances=faults,maximum_normalized_error=worst,
        qualified=False,default_promoted=False,chunk_complete=False,package_sha256=PACKAGE,
        producer_report_sha256=sha(evidence/'report.json'),evidence_manifest_sha256=sha(evidence/'evidence-manifest.json'),
        source_count=len(expected_sources),artifact_count=len(manifest['files']),reader_sha256=sha(__file__))


if __name__ == '__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for name in ('evidence','package','repo','runner','output'):p.add_argument('--'+name,type=Path,required=True)
    p.add_argument('--expected-report-sha256',required=True);p.add_argument('--expected-manifest-sha256',required=True)
    p.add_argument('--pilot',action='store_true');a=p.parse_args()
    result=audit(a.evidence,a.package,a.repo,a.runner,a.pilot,expected_report_sha256=a.expected_report_sha256,expected_manifest_sha256=a.expected_manifest_sha256)
    require(not a.output.exists() and not a.output.resolve().is_relative_to(a.evidence.resolve()), 'Write new audit receipt outside immutable evidence')
    a.output.write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(result,indent=2))
