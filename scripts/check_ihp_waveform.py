"""Reject aborted transients even when ngspice exits zero and writes a waveform."""
import argparse
from bisect import bisect_left
import hashlib
import json
import math
from pathlib import Path
import re


def audit(waveform, expectations, duration_ns, log):
    waveform, expectations, log = map(Path, (waveform, expectations, log))
    if not math.isfinite(duration_ns) or duration_ns <= 0:
        raise ValueError('A positive finite test duration is required.')
    if re.search(r'simulation\(s\) aborted|timestep too small|no such vector|transient op failed',
                 log.read_text(errors='replace'), re.I):
        raise ValueError('The native simulator reported an incomplete analysis.')
    expected = json.loads(expectations.read_text())
    voltage = expected['voltage']; channels = expected['channels']; samples = expected['samples']
    if (not isinstance(voltage, (int, float)) or not math.isfinite(voltage) or voltage <= 0
            or not channels or not samples):
        raise ValueError('Expected voltage, channels and samples are required.')
    names = [row['node'].casefold() for row in channels]
    if len(names) != len(set(names)):
        raise ValueError('Expected channel identities must be unique.')
    times, values = [], []
    with waveform.open() as stream:
        header = stream.readline().casefold().split()
        if header != ['time'] + ['v('+n+')' for n in names]:
            raise ValueError('Saved waveform channels differ from the expected outputs.')
        for line in stream:
            row = list(map(float, line.split()))
            if (len(row) != len(names)+1 or not all(map(math.isfinite, row))
                    or row[0] < 0 or (times and row[0] <= times[-1])):
                raise ValueError('Waveform data are malformed, nonfinite or out of order.')
            times.append(row[0]); values.append(row[1:])
    end = duration_ns * 1e-9
    if len(times) < 2 or times[0] > 1e-12 or times[-1] < end - 1e-15:
        raise ValueError('The transient did not cover the entire requested test interval.')
    failures, tested = [], 0
    for sample in samples:
        t = sample['time_ns'] * 1e-9; bits = sample['bits']
        if (not math.isfinite(t) or not times[0] <= t <= end or len(bits) != len(names)
                or any(bit not in ('0', '1') for bit in bits)):
            raise ValueError('Every expected sample must lie inside the captured test interval.')
        i = bisect_left(times, t)
        if i == len(times) and t-times[-1] <= 1e-15:
            interpolated = values[-1]
        elif i == 0:
            interpolated = values[0]
        else:
            fraction = (t-times[i-1])/(times[i]-times[i-1])
            interpolated = [x+(y-x)*fraction for x,y in zip(values[i-1],values[i])]
        for j, (bit, value) in enumerate(zip(bits, interpolated)):
            tested += 1
            if not (value >= .8*voltage if bit == '1' else value <= .2*voltage):
                failures.append(dict(time_ns=sample['time_ns'], channel=channels[j],
                                     expected=bit, voltage=value))
    sha = lambda p: hashlib.sha256(p.read_bytes()).hexdigest()
    return dict(schema=1, status='fail' if failures else 'pass', qualified=False,
                complete_waveform=True, tested_bits=tested, failed_bits=len(failures),
                failures=failures[:25], duration_ns=duration_ns,
                waveform_sha256=sha(waveform), expectations_sha256=sha(expectations),
                engine_log_sha256=sha(log),
                scope='Complete digital output samples at the declared voltage; timing and model coverage require separate checks.')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--waveform', type=Path, required=True)
    parser.add_argument('--expectations', type=Path, required=True)
    parser.add_argument('--duration-ns', type=float, required=True)
    parser.add_argument('--log', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    result = audit(args.waveform, args.expectations, args.duration_ns, args.log)
    args.output.write_text(json.dumps(result, indent=2)+'\n', encoding='utf-8', newline='\n')
    return 0 if result['status'] == 'pass' else 1


if __name__ == '__main__':
    raise SystemExit(main())
