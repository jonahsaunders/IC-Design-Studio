"""Check complete, source-matched IHP transients at the fixed 1 ps limit.

This is numerical evidence for the captured outputs and stimulus only. It does
not qualify field extraction, static timing, cold startup or a PDK release.
"""
import argparse
import hashlib
import json
import math
from pathlib import Path
import re

from scripts.check_ihp_waveform import audit

LIMIT_PS = 1.
EDGE_START_NS = 10.


def _number(value):
    match = re.fullmatch(r'([+\-]?(?:\d+(?:\.\d*)?|\.\d+)(?:e[+\-]?\d+)?)([fpnum]?)', value, re.I)
    if not match:
        raise ValueError('Unsupported numerical setting in the captured transient.')
    result = float(match[1])*{'': 1., 'f': 1e-15, 'p': 1e-12, 'n': 1e-9, 'u': 1e-6, 'm': 1e-3}[match[2].lower()]
    if not math.isfinite(result) or result <= 0:
        raise ValueError('Transient settings must be positive and finite.')
    return result


def _settings(path, duration_ns):
    text = path.read_text(); settings = {}
    for key in ('reltol', 'abstol', 'vntol', 'chgtol'):
        pattern = r'(?i)\b'+key+r'=([^\s]+)'
        matches = re.findall(pattern, text)
        if key == 'chgtol' and not matches:
            continue
        if len(matches) != 1:
            raise ValueError('One explicit '+key+' setting is required.')
        settings[key] = _number(matches[0])
        text = re.sub(pattern, key+'=<compared>', text)
    pattern = r'(?m)^tran (\S+) (\S+) 0 (\S+)(?: (uic))?$'
    matches = re.findall(pattern, text)
    if len(matches) != 1:
        raise ValueError('One explicit complete transient is required.')
    step, end, maximum = map(_number, matches[0][:3])
    if not math.isclose(end, duration_ns*1e-9, rel_tol=0., abs_tol=1e-18):
        raise ValueError('The captured duration differs from the requested workload.')
    settings.update(output_step=step, maximum_step=maximum)
    return settings, re.sub(pattern, lambda match: 'tran <step> <end> 0 <maximum>'+(' uic' if match[4] else ''), text)


def _events(path, voltage):
    previous = None; events = None
    with path.open() as stream:
        next(stream)
        for line in stream:
            row = list(map(float, line.split()))
            if events is None:
                events = [[] for _ in row[1:]]
            if previous is not None:
                for channel, (before, after) in enumerate(zip(previous[1:], row[1:])):
                    threshold = voltage/2
                    if (before >= threshold) != (after >= threshold):
                        time = previous[0]+(threshold-before)/(after-before)*(row[0]-previous[0])
                        if time >= EDGE_START_NS*1e-9:
                            events[channel].append((1 if after > before else -1, time))
            previous = row
    return events


def compare(baseline, tighter, duration_ns):
    """Require identical captured physics/stimulus and genuinely tighter settings.

    The caller must bind the external PDK libraries and executables separately.
    Never use a passing result as an acceptance of those uninspected resources.
    """
    baseline, tighter = map(Path, (baseline, tighter))
    if not math.isfinite(duration_ns) or duration_ns <= EDGE_START_NS:
        raise ValueError('A full workload longer than the startup exclusion is required.')
    sha = lambda path: hashlib.sha256(path.read_bytes()).hexdigest()
    files = ('circuit.spice', 'capacitance.spice', '.spiceinit', 'expectations.json',
             'bench.spice', 'waveform.txt', 'engine.log')
    captured = [{name: sha(folder/name) for name in files} for folder in (baseline, tighter)]
    matched = {}
    for name in ('circuit.spice', 'capacitance.spice', '.spiceinit', 'expectations.json'):
        value = sha(baseline/name)
        if sha(tighter/name) != value:
            raise ValueError('Convergence inputs differ: '+name)
        matched[name] = value
    settings, templates = zip(*(_settings(folder/'bench.spice', duration_ns) for folder in (baseline, tighter)))
    if settings[0].keys() != settings[1].keys():
        raise ValueError('Optional charge tolerance must be explicit in both captures or neither.')
    if templates[0] != templates[1]:
        raise ValueError('The circuit, stimulus or non-compared simulator settings changed.')
    if (any(settings[1][key] > settings[0][key] for key in settings[0]) or
            settings[1]['reltol'] >= settings[0]['reltol'] or
            settings[1]['maximum_step'] >= settings[0]['maximum_step']):
        raise ValueError('The second run must tighten relative tolerance and maximum step without loosening other settings.')
    expected = json.loads((baseline/'expectations.json').read_text())
    audits = [audit(folder/'waveform.txt', folder/'expectations.json', duration_ns, folder/'engine.log')
              for folder in (baseline, tighter)]
    if any(row['status'] != 'pass' for row in audits):
        raise ValueError('Both complete functional waveforms must pass before convergence comparison.')
    events = [_events(folder/'waveform.txt', expected['voltage']) for folder in (baseline, tighter)]
    channels = []; maximum = 0.; matched_edges = 0
    for name, left, right in zip(expected['channels'], *events):
        same = [v[0] for v in left] == [v[0] for v in right]
        differences = [abs(a[1]-b[1])*1e12 for a, b in zip(left, right)] if same else []
        largest = max(differences, default=0.) if same else None
        channels.append(dict(channel=name, baseline_edges=len(left), tighter_edges=len(right),
                             same_direction_sequence=same, maximum_edge_change_ps=largest))
        if same:
            matched_edges += len(left); maximum = max(maximum, largest)
    passed = matched_edges > 0 and all(row['same_direction_sequence'] for row in channels) and maximum <= LIMIT_PS
    # Bind the exact checked inputs again after reading the waves.
    for folder, snapshot in zip((baseline, tighter), captured):
        if any(sha(folder/name) != value for name, value in snapshot.items()):
            raise ValueError('A convergence input changed during the comparison.')
    return dict(schema=1, status='convergence-pass' if passed else 'convergence-failed', qualified=False,
                convergence_limit_ps=LIMIT_PS, transition_start_ns=EDGE_START_NS,
                duration_ns=duration_ns, matched_input_sha256=matched, settings=list(settings),
                captured_file_sha256=captured,
                bench_sha256=[sha(folder/'bench.spice') for folder in (baseline, tighter)],
                waveform_audits=audits, channels=channels, matched_edges=matched_edges,
                maximum_edge_change_ps=maximum,
                scope='Complete source-matched output-function and 50%-supply edge convergence after 10 ns. External models, engines, startup, field accuracy and static timing require separate evidence.')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--baseline', required=True, type=Path)
    parser.add_argument('--tighter', required=True, type=Path)
    parser.add_argument('--duration-ns', required=True, type=float)
    parser.add_argument('--output', required=True, type=Path)
    args = parser.parse_args()
    if args.output.exists():
        raise ValueError('Use a new convergence report to preserve prior evidence.')
    result = compare(args.baseline, args.tighter, args.duration_ns)
    args.output.write_text(json.dumps(result, indent=2)+'\n', encoding='utf-8', newline='\n')
    print(json.dumps(result))
    return 0 if result['status'] == 'convergence-pass' else 1


if __name__ == '__main__':
    raise SystemExit(main())
