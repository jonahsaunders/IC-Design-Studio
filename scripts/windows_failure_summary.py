"""Small diagnostic projection, never an installed-acceptance authority.

Reads only named CI reports and a bounded transcript tail. No recursive evidence
copy, executable, project, environment dump or whole-file hashing of large logs.
"""
from pathlib import Path
import argparse
import hashlib
import json
import math
import os
import re
import stat

MAX_INPUT = 64 * 1024
MAX_OUTPUT = 8 * 1024 * 1024
REPORTS = (
    'wrapper-error.json', 'windows-release.json',
    'dpi-1/release-test.json', 'dpi-1.5/release-test.json', 'dpi-2/release-test.json',
    'physical/report.json', 'mim/verification.json', 'mim-acceptance.json',
    'optional-esd/acceptance.json', 'default-esd/acceptance.json',
    'pw2dn/verification.json', 'pw2dn/reference-invocation.json',
    'pw2dn/native-references/failure.json', 'pw2dn/reference-launcher.log',
    'ihp-cmim/verification.json',
    'device-classes/verification.json', 'ihp-resistors/verification.json',
    'ihp-guard-corner/verification.json', 'metal-resistors-acceptance.json',
    'metal-parallel-acceptance.json',
)
KEYS = ('status', 'error', 'errors', 'message', 'exception', 'script_stack_trace',
        'commit', 'version', 'frozen', 'build', 'execution_id',
        'returncode', 'seconds', 'started_utc', 'ended_utc')

def redact(text):
    # Defense in depth for standard credential formats. The collector never
    # reads credential files/environment or includes arbitrary project fields.
    text = re.sub(r'(?i)(authorization\s*[:=]\s*(?:bearer|basic)\s+)\S+', r'\1[REDACTED]', text)
    text = re.sub(
        r'''(?ix)(["']?(?:token|password|secret|api[_-]?key)["']?\s*[:=]\s*)
        (?:"(?:\\.|[^"\\])*"|'(?:\\.|[^'\\])*'|[^\s,;]+)''',
        r'\1[REDACTED]', text)
    text = re.sub(r'\b(?:gh[pousr]_[A-Za-z0-9_]+|github_pat_[A-Za-z0-9_]+)\b', '[REDACTED]', text)
    text = re.sub(r'(https?://[^\s?]+)\?[^\s]+', r'\1?[QUERY REDACTED]', text)
    return text

def scalar(value):
    """Only declared scalar fields, never arbitrary nested report content."""
    return value is None or type(value) in (str, bool, int) or (
        type(value) is float and math.isfinite(value))

def projection(obj):
    result, omitted = {}, []
    for key in KEYS:
        if key not in obj or key == 'build':
            continue
        value = obj[key]
        if scalar(value):
            result[key] = redact(value) if isinstance(value, str) else value
        else:
            omitted.append(key)
    if isinstance(obj.get('build'), dict):
        result['build'] = {}
        for key in ('commit', 'dirty', 'frozen', 'version'):
            if key not in obj['build']:
                continue
            value = obj['build'][key]
            if scalar(value):
                result['build'][key] = redact(value) if isinstance(value, str) else value
            else:
                omitted.append('build.' + key)
    elif 'build' in obj:
        omitted.append('build')
    return result, omitted

def checked(root, relative):
    root = Path(root).absolute()
    path = root / relative
    # Reject links/reparse points in every existing ancestor, including root.
    for part in [*reversed(path.parents), path]:
        info = part.lstat()
        if stat.S_ISLNK(info.st_mode) or getattr(info, 'st_file_attributes', 0) & 0x400:
            raise ValueError('linked/reparse path')
    if not stat.S_ISREG(path.lstat().st_mode):
        raise ValueError('not a regular file')
    return path

def collect(root, candidate):
    if not re.fullmatch(r'[0-9a-f]{40}', candidate):
        raise ValueError('expected full candidate SHA')
    result = dict(schema=1, diagnostic_only=True, installed_acceptance=False,
                  candidate=candidate, reports=[], omissions=[],
                  scope='Allowlisted report projections and transcript tail only; not full evidence.',
                  limitations=['Missing files do not identify the failed gate.',
                               'PowerShell transcript may omit buffered/native output; authoritative job log remains required.',
                               'Redaction is defense in depth, not a general secret detector.'])
    for name in (*REPORTS, 'verify-windows-transcript.txt'):
        row = dict(path=name)
        try:
            path = checked(root, name)
            with path.open('rb') as stream:
                info = os.fstat(stream.fileno())
                if not stat.S_ISREG(info.st_mode):
                    raise ValueError('not regular after open')
                size = info.st_size
                row['source_bytes'] = size
                if name.endswith('.json') and size > MAX_INPUT:
                    raise ValueError('oversize JSON omitted, not partially parsed')
                start = max(0, size - MAX_INPUT)
                stream.seek(start)
                raw = stream.read(MAX_INPUT)
            row.update(retained_offset=start, retained_bytes=len(raw),
                       retained_slice_sha256=hashlib.sha256(raw).hexdigest(),
                       truncated=bool(start), full_source_hash=not bool(start))
            text = raw.decode('utf-8', errors='replace')
            if name.endswith('.json'):
                obj = json.loads(text.lstrip('\ufeff'))
                if not isinstance(obj, dict):
                    raise ValueError('report must be object')
                row['projection'], row['omitted_nonscalar_fields'] = projection(obj)
            else:
                row['tail'] = redact(text)
            result['reports'].append(row)
        except (OSError, ValueError, UnicodeError) as exc:
            result['omissions'].append(dict(path=name, reason=str(exc)[:300]))
    result['omissions'].append(dict(path='all nonallowlisted evidence', reason='Not traversed: binaries, projects, raw data, screenshots and full logs remain in full diagnostics.'))
    data = (json.dumps(result, ensure_ascii=True, indent=2) + '\n').encode()
    if len(data) > MAX_OUTPUT:
        raise ValueError('summary exceeds hard8MiB budget')
    return data

def main():
    p = argparse.ArgumentParser()
    p.add_argument('--root', default='build/windows-evidence')
    p.add_argument('--output', default='build/windows-failure-summary/summary.json')
    p.add_argument('--candidate', required=True)
    args = p.parse_args()
    data = collect(args.root, args.candidate)
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    if output.exists() or output.is_symlink():
        raise ValueError('refuse stale summary output')
    # Output must not follow an existing directory link/reparse point either.
    for parent in [output.parent, *output.parent.parents]:
        info = parent.lstat()
        if stat.S_ISLNK(info.st_mode) or getattr(info, 'st_file_attributes', 0) & 0x400:
            raise ValueError('linked output directory')
    with output.open('xb') as stream:
        stream.write(data)

if __name__ == '__main__':
    main()
