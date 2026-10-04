"""Stage qualified previews, with an explicit gated public release mode."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile
from urllib.parse import quote, unquote, urlsplit, urlunsplit

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def preview_tag(version, branch, commit, run_id, attempt):
    if not re.fullmatch(r'\d+\.\d+\.\d+(?:[.-][A-Za-z0-9]+)*', version):
        raise ValueError('Invalid preview version.')
    if branch not in ('main', 'experimental'):
        raise ValueError('Only main and experimental produce automatic previews.')
    if not re.fullmatch(r'[0-9a-f]{40}', commit):
        raise ValueError('Use the complete source commit SHA.')
    if any(not re.fullmatch(r'[1-9][0-9]*', str(value)) for value in (run_id, attempt)):
        raise ValueError('Use the GitHub run ID and positive run attempt.')
    # A failed asset upload can leave a partial draft. A rerun must get its own
    # identity rather than overwrite that draft or mix separately rebuilt assets.
    return f'{branch}-v{version}-{commit}-{run_id}-{attempt}'


def public_tag(version, branch):
    if branch != 'main' or not re.fullmatch(r'(?:0|[1-9][0-9]*)\.(?:0|[1-9][0-9]*)\.(?:0|[1-9][0-9]*)', version):
        raise ValueError('Public releases require main and a plain X.Y.Z version.')
    return 'v' + version


def render_release_notes(notes, repository, commit, *, root=ROOT):
    """Make repository links work when the Markdown is copied onto a release."""
    root, notes = Path(root).resolve(), Path(notes).resolve()
    if not notes.is_relative_to(root):
        raise ValueError('Release notes must be inside the source repository.')

    def replace(match):
        destination = match.group('destination')
        if destination is None:  # Leave fenced and inline code examples intact.
            return match.group(0)
        wrapped = destination.startswith('<')
        uri = urlsplit(destination[1:-1] if wrapped else destination)
        if uri.scheme or uri.netloc or not uri.path:
            return match.group(0)
        target = (root / unquote(uri.path).lstrip('/') if uri.path.startswith('/')
                  else notes.parent / unquote(uri.path)).resolve()
        if not target.is_relative_to(root) or not target.exists():
            raise ValueError('Missing or unsafe release-note link: ' + destination)
        relative = quote(target.relative_to(root).as_posix(), safe='/')
        base = ('https://raw.githubusercontent.com/' + repository + '/' + commit + '/'
                if match.group('prefix').startswith('![')
                else 'https://github.com/' + repository + '/blob/' + commit + '/')
        rebased = urlunsplit((*urlsplit(base + relative)[:3], uri.query, uri.fragment))
        if wrapped:
            rebased = '<' + rebased + '>'
        start, end = match.span('destination')
        return match.group(0)[:start - match.start()] + rebased + match.group(0)[end - match.start():]

    # Release notes use inline Markdown links; reference definitions and images
    # use the same destination handling. Code examples are copied verbatim.
    pattern = re.compile(
        r'(?P<code>^[ \t]{0,3}(?P<fence>`{3,}|~{3,})[^\n]*\n.*?^[ \t]{0,3}(?P=fence)[ \t]*$|`+[^`\n]+`+)'
        r'|(?P<prefix>!?\[[^\]\n]*\]\(|^[ \t]{0,3}\[[^\]\n]+\]:[ \t]*)'
        r'(?P<destination><[^>\n]+>|[^\s)]+)', re.MULTILINE | re.DOTALL)
    return pattern.sub(replace, notes.read_text(encoding='utf-8'))


def validate_public_assets(directory, assets, version, commit):
    """Require complete, unchanged desktop payloads from the selected source."""
    from scripts.release_evidence import checksum, EVIDENCE_KINDS, _validate_record, BUFFER_BYTES
    directory = Path(directory)
    files = {path.name: path for path in assets}
    prefix = f'IC-Design-Studio-{version}-'
    sums_name = f'SHA256SUMS-{version}.txt'
    required = {sums_name, prefix + 'Statistical-Validation.json'}
    for platform in ('Windows', 'Linux'):
        required.update(prefix + kind + '-' + platform + '.zip' for kind in ('Source', 'Evidence'))
        required.add(prefix + 'Validation-' + platform + '.json')
    required.update(prefix + suffix for suffix in ('Windows-x64-Setup.exe', 'Windows-x64-Portable.zip', 'Linux-x86_64.tar.gz'))
    if not required <= files.keys():
        raise ValueError('Public release requires both qualified Windows packages, Linux, corresponding source/evidence, validation and checksums. Missing: ' + ', '.join(sorted(required - files.keys())))
    for kind in EVIDENCE_KINDS:
        name = prefix + kind + '-Evidence.zip'
        if name not in files and name + '.parts.json' not in files:
            raise ValueError('Missing public release qualification evidence: ' + kind)
    hashes = {}
    for line in files[sums_name].read_text(encoding='utf-8').splitlines():
        match = re.fullmatch(r'([0-9a-f]{64})  (.+)', line)
        if not match or match[2] in hashes or match[2] not in files or match[2] == sums_name:
            raise ValueError('Invalid or duplicate public release checksum entry.')
        hashes[match[2]] = match[1]
    if hashes.keys() != files.keys() - {sums_name}:
        raise ValueError('Public release checksums must cover every upload asset.')
    for name, expected in hashes.items():
        if checksum(files[name]) != expected:
            raise ValueError('Changed public release asset: ' + name)
    for name, path in files.items():
        if not name.endswith('.zip.parts.json'): continue
        manifest = json.loads(path.read_text(encoding='utf-8')); archive_name = name[:-len('.parts.json')]
        if not isinstance(manifest, dict) or manifest.get('schema') != 1 or manifest.get('format') != 'split-zip':
            raise ValueError('Invalid public evidence parts manifest: ' + name)
        archive, parts = manifest.get('archive'), manifest.get('parts')
        _validate_record(archive, archive_name)
        if not isinstance(parts, list) or len(parts) < 2:
            raise ValueError('Public evidence requires every ordered archive part: ' + name)
        whole = hashlib.sha256(); total = 0
        for index, part in enumerate(parts, 1):
            _validate_record(part, f'{archive_name}.part{index:03d}')
            if (part['name'] not in files or hashes[part['name']] != part['sha256']
                    or files[part['name']].stat().st_size != part['bytes']):
                raise ValueError('Missing or changed public evidence part: ' + part['name'])
            with files[part['name']].open('rb') as stream:
                while chunk := stream.read(BUFFER_BYTES): whole.update(chunk); total += len(chunk)
        if total != archive['bytes'] or whole.hexdigest() != archive['sha256']:
            raise ValueError('Public evidence parts do not reconstruct the qualified archive: ' + name)
    def matches(record):
        return isinstance(record, dict) and record.get('status') == 'passed' and record.get('version') == version and record.get('commit') == commit
    def desktop(report):
        return (isinstance(report, dict) and report.get('status') == 'passed' and report.get('version') == version and report.get('frozen') is True
                and isinstance(report.get('build'), dict) and report['build'].get('commit') == commit and report['build'].get('dirty') is False)
    for platform in ('Windows', 'Linux'):
        record = json.loads(files[prefix + 'Validation-' + platform + '.json'].read_text(encoding='utf-8'))
        if not matches(record) or record.get('platform') != platform:
            raise ValueError('Public release validation must match the selected version, commit and platform.')
        archive = prefix + ('Windows-x64-Portable.zip' if platform == 'Windows' else 'Linux-x86_64.tar.gz')
        platform_required = {archive, prefix + 'Source-' + platform + '.zip', prefix + 'Evidence-' + platform + '.zip'}
        if platform == 'Windows': platform_required.add(prefix + 'Windows-x64-Setup.exe')
        recorded = record.get('assets', {})
        if not isinstance(recorded, dict) or not platform_required <= recorded.keys() or any(hashes.get(name) != digest for name, digest in recorded.items()):
            raise ValueError('Public release assets differ from their qualified platform validation.')
        distribution = record.get('distribution', {})
        if (not isinstance(distribution, dict) or distribution.get('status') != 'passed' or distribution.get('archive') != archive
                or distribution.get('archive_sha256') != hashes[archive] or not desktop(distribution.get('report', {}))):
            raise ValueError('Public release archive execution must match the exact clean packaged source.')
        if platform == 'Windows':
            installer = record.get('installer', {}); setup = prefix + 'Windows-x64-Setup.exe'
            probes = installer.get('probes', []) if isinstance(installer, dict) else []
            if (not matches(installer) or installer.get('installer') != setup or installer.get('installer_sha256') != hashes[setup]
                    or not isinstance(probes, list) or len(probes) != 3 or not all(isinstance(probe, dict) for probe in probes)
                    or {str(probe.get('scale')) for probe in probes} != {'1', '1.5', '2'}
                    or not all(desktop(probe) for probe in probes)):
                raise ValueError('Public Windows installer must match the executed source and all three DPI probes.')
    statistics = json.loads(files[prefix + 'Statistical-Validation.json'].read_text(encoding='utf-8'))
    if not matches(statistics):
        raise ValueError('Public statistical validation must match the selected version and commit.')


def require_unused_public_tag(tag, repository, run):
    # Listing with push access includes drafts; lookup by tag alone can miss them.
    releases = run(['gh', 'api', '--paginate', f'repos/{repository}/releases?per_page=100',
                    '--jq', '.[] | select(.tag_name == ' + json.dumps(tag) + ') | .id'],
                   capture_output=True, text=True)
    if releases.returncode:
        raise ValueError('Could not check existing public releases. Resolve GitHub access or connectivity and retry.')
    if releases.stdout.strip():
        raise ValueError('Refusing to replace an existing canonical release: ' + tag)
    reference = run(['gh', 'api', '--include', '--silent', f'repos/{repository}/git/ref/tags/{tag}'],
                    capture_output=True, text=True)
    statuses = re.findall(r'^HTTP/[0-9.]+\s+([0-9]{3})(?:\s|$)', reference.stdout, flags=re.MULTILINE)
    if statuses and statuses[-1] == '200':
        raise ValueError('Refusing to replace an existing canonical tag: ' + tag)
    if not statuses or statuses[-1] != '404':
        raise ValueError('Could not confirm the public release tag is unused. Resolve GitHub access or connectivity and retry.')


def publish(directory, version, branch, commit, run_id, attempt, repository,
            *, root=ROOT, run=subprocess.run, public=False):
    from scripts.release_evidence import preflight_assets
    tag = preview_tag(version, branch, commit, run_id, attempt)
    if not re.fullmatch(r'[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+', repository):
        raise ValueError('Use an explicit owner/repository for the preview.')
    canonical = public_tag(version, branch) if public else None
    note_version = re.sub(r'^(\d+\.\d+)\.0\.dev(\d+)$', r'\1_DEV\2', version)
    notes = Path(root) / 'docs' / f'UPDATE_{note_version}.md'
    if not notes.is_file():
        raise ValueError('Matching release notes are missing: ' + notes.name)
    rendered_notes = render_release_notes(notes, repository, commit, root=root)
    assets = preflight_assets(directory)
    if public:
        validate_public_assets(directory, assets, version, commit)
        require_unused_public_tag(canonical, repository, run)
    with tempfile.TemporaryDirectory(prefix='icstudio-release-notes-') as temporary:
        published_notes = Path(temporary) / notes.name
        published_notes.write_text(rendered_notes, encoding='utf-8')
        command = ['gh', 'release', 'create', tag, *[str(p.resolve()) for p in assets],
                   '--repo', repository, '--draft', '--prerelease', '--target', commit,
                   '--title', f'IC Design Studio {version} — {branch} preview ({run_id}/{attempt})',
                   '--notes-file', str(published_notes)]
        run(command, check=True)
    if public:
        require_unused_public_tag(canonical, repository, run)
        # Creating the ref atomically closes the check/upload race. A conflict
        # fails without publishing or changing the prior release/tag.
        run(['gh', 'api', '--method', 'POST', f'repos/{repository}/git/refs',
             '-f', 'ref=refs/tags/' + canonical, '-f', 'sha=' + commit], check=True)
        try:
            run(['gh', 'release', 'edit', tag, '--repo', repository, '--tag', canonical,
                 '--target', commit, '--verify-tag', '--draft=false', '--prerelease=false', '--latest',
                 '--title', f'IC Design Studio {version}'], check=True)
        except subprocess.CalledProcessError as exc:
            raise ValueError('Public promotion failed after reserving ' + canonical + '. Inspect that tag and draft ' + tag + ' before retrying; neither is overwritten automatically.') from exc
    return canonical or tag


def main():
    from icstudio import __version__
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--directory', type=Path, required=True)
    parser.add_argument('--version', default=__version__)
    parser.add_argument('--branch', default=os.environ.get('RELEASE_BRANCH', ''))
    parser.add_argument('--commit', default=os.environ.get('RELEASE_COMMIT', ''))
    parser.add_argument('--run-id', default=os.environ.get('GITHUB_RUN_ID', ''))
    parser.add_argument('--attempt', default=os.environ.get('GITHUB_RUN_ATTEMPT', ''))
    parser.add_argument('--repository', default=os.environ.get('GITHUB_REPOSITORY', ''))
    parser.add_argument('--public', action='store_true', help='Publish a complete qualified main release as vVERSION; previews remain drafts by default.')
    args = parser.parse_args()
    print(publish(args.directory, args.version, args.branch, args.commit,
                  args.run_id, args.attempt, args.repository, public=args.public))


if __name__ == '__main__':
    main()
