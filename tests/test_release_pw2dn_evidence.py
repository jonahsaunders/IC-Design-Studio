import importlib.util
import io
import json
from pathlib import Path
import tempfile
import unittest
import zipfile
import tarfile

HERE = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('pw2dn_release_receipt_test', HERE / 'scripts/release_pw2dn_evidence.py')
gate = importlib.util.module_from_spec(spec)
spec.loader.exec_module(gate)
COMMIT = 'a' * 40
EXECUTION = 'b' * 32
EXE = b'fixture executable'
ENGINE = b'fixture engine'

def runtime_payload(platform):
    base = 'icstudio/assets/runtime/ngspice/'
    values = {base + ('ngspice.exe' if platform == 'Windows' else 'ngspice'): ENGINE,
              base + 'spinit': b'accepted initializer'}
    if platform == 'Windows': values[base + 'libomp140.x86_64.dll'] = b'accepted OpenMP dependency'
    else:
        for name in ('libgcc_s.so.1','libgomp.so.1','libstdc++.so.6','libreadline.so.8','libtinfo.so.6'):
            values[name] = ('accepted ' + name).encode()
    return values


def distribution(path, platform, changes=None):
    executable = 'ICDesignStudio/ICDesignStudio' + ('.exe' if platform == 'Windows' else '')
    values = {executable: EXE, **{'ICDesignStudio/_internal/' + name: data for name, data in runtime_payload(platform).items()}}
    for name, value in (changes or {}).items():
        if value is None: values.pop(name)
        else: values[name] = value
    if platform == 'Windows':
        with zipfile.ZipFile(path, 'w') as archive:
            for name, data in values.items(): archive.writestr(name, data)
    else:
        with tarfile.open(path, 'w:gz') as archive:
            for name, data in values.items():
                member = tarfile.TarInfo(name); member.size = len(data); archive.addfile(member, io.BytesIO(data))


def fixture(platform="Windows", mutate_runtime=None):
    files = {}
    def put(name, obj): files[name] = json.dumps(obj, sort_keys=True).encode()
    def sha(name): return gate.digest(files[name])
    build = {'frozen': True, 'dirty': False, 'commit': COMMIT}
    put('gui/new/project.icproj', {'specimen': 1})
    put('gui/new/schematic.spice', {'export': 1})
    binary = {'executable_sha256': gate.digest(EXE), 'engine_sha256': gate.digest(ENGINE)}
    resource = 'C:/accepted/ICDesignStudio/_internal' if platform == 'Windows' else '/accepted/ICDesignStudio/_internal'
    engine = resource + '/icstudio/assets/runtime/ngspice/' + ('ngspice.exe' if platform == 'Windows' else 'ngspice')
    values = runtime_payload(platform)
    runtime = {'platform': 'win32' if platform == 'Windows' else 'linux', 'engine': engine,
               'sha256': binary['engine_sha256'], 'files': {}, 'elf_dependencies': {}}
    for name, data in values.items():
        path = resource + '/' + name
        if '/' in name: runtime['files'][path] = gate.digest(data)
        else: runtime['elf_dependencies'][path] = {'resolved': path, 'sha256': gate.digest(data)}
    if platform == 'Linux':
        for name in ('libc.so.6','libm.so.6','ld-linux-x86-64.so.2'):
            path = '/lib/x86_64-linux-gnu/' + name
            runtime['elf_dependencies'][path] = {'resolved': '/usr/lib/x86_64-linux-gnu/' + name, 'sha256': 'd' * 64}
        runtime['files']['/usr/bin/ldd'] = 'e' * 64
        runtime['files']['/etc/ld.so.cache'] = 'f' * 64
    if mutate_runtime is not None: mutate_runtime(runtime, resource)
    context = {'runtime': runtime, 'resource_root': resource, 'engine': engine}
    put('gui/prelaunch.json', {'execution_id': EXECUTION, 'executable_sha256': binary['executable_sha256']})
    put('gui/report.json', {'execution_id': EXECUTION, 'status': 'PASS_GUI_LIFECYCLE', 'frozen': True, 'build': build, 'executable_sha256': binary['executable_sha256']})
    put('expected.json', {'execution_id': EXECUTION, 'commit': COMMIT, **binary, **context})
    put('readback-input.json', {'execution_id': EXECUTION, 'commit': COMMIT, 'prelaunch_sha256': sha('gui/prelaunch.json'), **binary, **context})
    put('gui-verification.json', {'status': 'PASS_FROZEN_GUI_LIFECYCLE_ONLY', 'report_sha256': sha('gui/report.json'),
         'project_sha256': sha('gui/new/project.icproj'), 'spice_sha256': sha('gui/new/schematic.spice'), 'readback_input_sha256': sha('readback-input.json')})
    put('native/report.json', {'execution_id': EXECUTION, 'status': 'PASS_NATIVE_PRODUCTION_ONLY', 'frozen': True, 'build': build, 'selected_project_sha256': sha('gui/new/project.icproj'), 'engine_sha256': binary['engine_sha256'], 'runtime_before': runtime, 'runtime_after': runtime, 'resource_root': resource})
    native_input = {'execution_id': EXECUTION, 'commit': COMMIT, 'mode': 'installed', 'pilot': False,
         'native_report_sha256': sha('native/report.json'), 'gui_verification_sha256': sha('gui-verification.json'),
         'gui_report_sha256': sha('gui/report.json'), 'selected_project_sha256': sha('gui/new/project.icproj'),
         'selected_export_sha256': sha('gui/new/schematic.spice'), 'source_files': {'scripts/audit_installed_sky130_pw2dn_native.py': 'f' * 64}, **binary, **context}
    put('native-inputs.json', native_input)
    put('native-references/reference-report.json', {'status': 'PASS_REFERENCE_PRODUCTION_ONLY'})
    audit_input = {**native_input, 'reference_report_sha256': sha('native-references/reference-report.json')}
    put('native-references/expected-inputs.json', audit_input)
    verdict = {'status': 'PASS_FROZEN_NATIVE_ELECTRICAL', 'conditions': 9, 'geometries': 3, 'application_runs': 45, 'literal_runs': 18, 'detected_faulted_instances': 81,
               'expected': audit_input, 'reference_report_sha256': audit_input['reference_report_sha256'], 'reader_sha256': 'f' * 64}
    put('native-verification.json', verdict)
    put('native-references/verification.json', verdict)
    for name in ('invocation.json', 'reference-invocation.json'):
        put(name, {'execution_id': EXECUTION, 'status': 'PASS', 'returncode': 0})
    put('verification.json', {'status': 'PASS_FROZEN_GUI_AND_NATIVE', 'commit': COMMIT, 'execution_id': EXECUTION,
         'gui_verification_sha256': sha('gui-verification.json'), 'native_verification_sha256': sha('native-verification.json')})
    return files

class PayloadReceiptTests(unittest.TestCase):
    def test_both_platform_archive_paths_and_live_receipts(self):
        files = fixture()
        expected = gate.validate(files, COMMIT)
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            for name, data in files.items():
                path = root / name; path.parent.mkdir(parents=True, exist_ok=True); path.write_bytes(data)
            self.assertEqual(gate.from_directory(root, COMMIT), expected)
            for prefix in ('windows-evidence/pw2dn', 'frozen-pw2dn-evidence'):
                path = root / 'evidence.zip'
                with zipfile.ZipFile(path, 'w') as archive:
                    for name, data in files.items(): archive.writestr(prefix + '/' + name, data)
                with zipfile.ZipFile(path) as archive:
                    self.assertEqual(gate.from_zip(archive, prefix, COMMIT), expected)

    def test_missing_failed_wrong_commit_and_substituted_receipts(self):
        for mutation in ('missing', 'failed', 'commit', 'substitute', 'identity', 'boolean_rc', 'selection'):
            with self.subTest(mutation=mutation):
                files = fixture()
                if mutation == 'missing': del files['gui/report.json']
                elif mutation == 'substitute': files['gui/new/schematic.spice'] = b'changed'
                else:
                    name, key, value = {
                        'failed': ('verification.json', 'status', 'FAIL'),
                        'commit': ('native/report.json', 'build', {'commit': 'c' * 40, 'frozen': True, 'dirty': False}),
                        'identity': ('reference-invocation.json', 'execution_id', 'c' * 32),
                        'boolean_rc': ('invocation.json', 'returncode', False),
                        'selection': ('native-verification.json', 'literal_runs', 1),
                    }[mutation]
                    obj = json.loads(files[name]); obj[key] = value; files[name] = json.dumps(obj).encode()
                with self.assertRaises(ValueError): gate.validate(files, COMMIT)

    def test_duplicate_archived_receipt_rejected(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'e.zip'; files = fixture(); prefix = 'frozen-pw2dn-evidence'
            with zipfile.ZipFile(path, 'w') as archive:
                for name, data in files.items(): archive.writestr(prefix + '/' + name, data)
                with self.assertWarns(UserWarning): archive.writestr(prefix + '/verification.json', files['verification.json'])
            with zipfile.ZipFile(path) as archive, self.assertRaises(ValueError): gate.from_zip(archive, prefix, COMMIT)

    def test_rehashed_cross_run_native_verdict_rejected(self):
        files = fixture()
        verdict = json.loads(files['native-verification.json'])
        verdict['expected']['execution_id'] = 'c' * 32
        files['native-verification.json'] = files['native-references/verification.json'] = json.dumps(verdict).encode()
        files['native-references/expected-inputs.json'] = json.dumps(verdict['expected']).encode()
        combined = json.loads(files['verification.json'])
        combined['native_verification_sha256'] = gate.digest(files['native-verification.json'])
        files['verification.json'] = json.dumps(combined).encode()
        with self.assertRaisesRegex(ValueError, 'native audit inputs differ'):
            gate.validate(files, COMMIT)

    def test_distribution_binary_mismatch_and_unsafe_path_rejected(self):
        with tempfile.TemporaryDirectory() as folder:
            for platform in ('Windows', 'Linux'):
                path = Path(folder) / ('test.zip' if platform == 'Windows' else 'test.tar.gz')
                distribution(path, platform); receipt = gate.validate(fixture(platform), COMMIT)
                gate.check_distribution(path, platform, receipt)
                receipt['engine_sha256'] = 'f' * 64
                engine_key = 'icstudio/assets/runtime/ngspice/' + ('ngspice.exe' if platform == 'Windows' else 'ngspice')
                receipt['bundled_runtime_files'][engine_key] = 'f' * 64
                with self.subTest(platform=platform), self.assertRaisesRegex(ValueError, 'binary differs'):
                    gate.check_distribution(path, platform, receipt)
                distribution(path, platform); receipt = gate.validate(fixture(platform), COMMIT)
                if platform == 'Windows':
                    with zipfile.ZipFile(path, 'a') as archive: archive.writestr('../escape', b'x')
                else:
                    with tarfile.open(path, 'w:gz') as archive:
                        member = tarfile.TarInfo('../escape'); member.size = 1; archive.addfile(member, io.BytesIO(b'x'))
                with self.subTest(platform=platform), self.assertRaisesRegex(ValueError, 'Unsafe'):
                    gate.check_distribution(path, platform, receipt)
            path = Path(folder) / 'ambiguous.zip'; distribution(path, 'Windows')
            with zipfile.ZipFile(path, 'a') as archive: archive.writestr('icdesignstudio/icdesignstudio.exe', b'changed')
            with self.assertRaisesRegex(ValueError, 'Ambiguous'):
                gate.check_distribution(path, 'Windows', gate.validate(fixture(), COMMIT))

    def test_distribution_alias_and_ancestor_link_rejected(self):
        receipt = gate.validate(fixture('Linux'), COMMIT)
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            for kind in ('alias', 'symlink', 'hardlink'):
                path = root / (kind + '.tar.gz')
                with tarfile.open(path, 'w:gz') as archive:
                    for name, data in (('ICDesignStudio/ICDesignStudio', EXE),
                            ('ICDesignStudio/_internal/icstudio/assets/runtime/ngspice/ngspice', ENGINE)):
                        member = tarfile.TarInfo(name); member.size = len(data); archive.addfile(member, io.BytesIO(data))
                    if kind == 'alias':
                        member = tarfile.TarInfo('ICDesignStudio/./ICDesignStudio'); member.size = 1
                        archive.addfile(member, io.BytesIO(b'x'))
                    else:
                        member = tarfile.TarInfo('ICDesignStudio/_internal')
                        member.type = tarfile.SYMTYPE if kind == 'symlink' else tarfile.LNKTYPE
                        member.linkname = 'elsewhere'; archive.addfile(member)
                with self.subTest(kind=kind), self.assertRaises(ValueError): gate.check_distribution(path, 'Linux', receipt)
            receipt = gate.validate(fixture('Windows'), COMMIT)
            for kind in ('ads', 'trailing-dot', 'ancestor'):
                path = root / (kind + '.zip'); distribution(path, 'Windows')
                with zipfile.ZipFile(path, 'a') as archive:
                    if kind == 'ads': archive.writestr('ICDesignStudio/ICDesignStudio.exe:evil', b'x')
                    elif kind == 'trailing-dot': archive.writestr('ICDesignStudio/ICDesignStudio.exe.', b'x')
                    else:
                        member = zipfile.ZipInfo('ICDesignStudio/_internal')
                        member.create_system = 3; member.external_attr = (0o120777 << 16)
                        archive.writestr(member, 'elsewhere')
                with self.subTest(kind=kind), self.assertRaises(ValueError): gate.check_distribution(path, 'Windows', receipt)


    def test_changed_missing_or_linked_accepted_dependency_rejected(self):
        with tempfile.TemporaryDirectory() as folder:
            for platform in ('Windows', 'Linux'):
                receipt = gate.validate(fixture(platform), COMMIT)
                relative = 'icstudio/assets/runtime/ngspice/libomp140.x86_64.dll' if platform == 'Windows' else 'libreadline.so.8'
                member = 'ICDesignStudio/_internal/' + relative
                path = Path(folder) / ('runtime.zip' if platform == 'Windows' else 'runtime.tar.gz')
                distribution(path, platform); gate.check_distribution(path, platform, receipt)
                for replacement in (b'coherently replaced dependency', None):
                    distribution(path, platform, {member: replacement})
                    with self.subTest(platform=platform, replacement=replacement), self.assertRaises(ValueError):
                        gate.check_distribution(path, platform, receipt)
                distribution(path, platform, {member: None})
                if platform == 'Windows':
                    with zipfile.ZipFile(path, 'a') as archive:
                        linked = zipfile.ZipInfo(member); linked.create_system = 3
                        linked.external_attr = 0o120777 << 16; archive.writestr(linked, 'elsewhere')
                else:
                    with tarfile.open(path, 'r:gz') as archive:
                        kept = [(m, archive.extractfile(m).read()) for m in archive]
                    with tarfile.open(path, 'w:gz') as archive:
                        for item, data in kept: archive.addfile(item, io.BytesIO(data))
                        linked = tarfile.TarInfo(member); linked.type = tarfile.SYMTYPE
                        linked.linkname = 'elsewhere'; archive.addfile(linked)
                with self.assertRaises(ValueError): gate.check_distribution(path, platform, receipt)
                # Keep both selected executables identical while substituting the initializer.
                distribution(path, platform, {'ICDesignStudio/_internal/icstudio/assets/runtime/ngspice/spinit': b'changed initializer'})
                with self.assertRaises(ValueError): gate.check_distribution(path, platform, receipt)

    def test_resource_mapping_alias_external_dependency_and_digest_rejected(self):
        def mutate(kind):
            def apply(runtime, root):
                if kind == 'alias':
                    row = runtime['elf_dependencies'].pop(root + '/libreadline.so.8')
                    runtime['elf_dependencies'][root + '/./libreadline.so.8'] = row
                elif kind == 'resolved-alias':
                    runtime['elf_dependencies'][root + '/libreadline.so.8']['resolved'] = root + '/other/libreadline.so.8'
                elif kind == 'external':
                    row = runtime['elf_dependencies'].pop(root + '/libreadline.so.8')
                    row['resolved'] = '/usr/lib/x86_64-linux-gnu/libreadline.so.8'
                    runtime['elf_dependencies'][row['resolved']] = row
                elif kind == 'digest': runtime['elf_dependencies'][root + '/libreadline.so.8']['sha256'] = 'invalid'
                elif kind == 'missing': del runtime['elf_dependencies'][root + '/libreadline.so.8']
                elif kind == 'engine': runtime['engine'] = '/other/ngspice'
                elif kind == 'external-file': runtime['files']['/tmp/unreviewed.spice'] = 'd' * 64
            return apply
        for kind in ('alias','resolved-alias','external','digest','missing','engine','external-file'):
            with self.subTest(kind=kind), self.assertRaisesRegex(ValueError, 'runtime'):
                gate.validate(fixture('Linux', mutate(kind)), COMMIT)
        accepted = gate.validate(fixture('Linux'), COMMIT)
        self.assertEqual(set(accepted['bundled_runtime_files']), set(runtime_payload('Linux')))
        self.assertNotIn('/usr/bin/ldd', accepted['bundled_runtime_files'])
        self.assertEqual(accepted['runtime_platform'], 'Linux')

if __name__ == '__main__': unittest.main()
