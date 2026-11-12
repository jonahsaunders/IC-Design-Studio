"""The process comparison independently checks the native raw observable."""
import math
import json
from pathlib import Path
import tempfile
import unittest
import zipfile

from scripts import check_ihp_cmim_process_control as reader
from scripts.check_ihp_cmim_process_control import CASES, measurement
from scripts.qualify_ihp_cmim_process_control import deck


def raw_plot(plot, flags, variables, values):
    columns = ''.join(f'\t{i}\t{name}\t{unit}\n' for i, (name, unit) in enumerate(variables))
    body = '\n'.join(values)
    return (f'Plotname: {plot}\nFlags: {flags}\nNo. Variables: {len(variables)}\nNo. Points: 1\n'
            f'Variables:\n{columns}Values:\n 0\t{body}\n')


class CmimProcessControlReaderTests(unittest.TestCase):
    def test_raw_current_and_scope_controls(self):
        spec = CASES['voltage-4']
        probes = [('v(upper)','voltage'), ('v(lower)','voltage'), ('i(vdrive)','current')]
        op = raw_plot('Operating Point', 'real', [probes[1], *probes], ['10', '0', '10', '0'])
        ac = raw_plot('AC Analysis', 'complex', [('frequency','frequency'), *probes],
                      ['1000000,0', '0,0', '1,0', '-1e-14,-4.7e-7'])
        log = 'Doing analysis at TEMP = 26.850000 and TNOM = 27.000000\n'*2
        original = {'input.cir': deck(spec), 'op.raw': op, 'ac.raw': ac, 'engine.log': log}
        controls = (
            ('ac.raw', ac.replace('1000000,0', '100000,0'), 'frequency differs'),
            ('ac.raw', ac.replace('-4.7e-7', '4.7e-7'), 'current sign/passivity'),
            ('ac.raw', ac.replace('-4.7e-7', 'NaN'), 'Nonfinite'),
            ('ac.raw', ac+'\t99\n', 'row shape'),
            ('op.raw', op.replace('0\t10', '0\t11'), 'scale/duplicate'),
            ('input.cir', original['input.cir'].replace('cap_typ','cap_wcs'), 'model section'),
        )
        for statement, anchor in (('Cunreviewed lower 0 1p', '.control'),
                                  ('.param cap_carea=0', '.control'),
                                  ('alter Vdrive 0', 'op\n')):
            injected = original['input.cir'].replace(anchor, statement+'\n'+anchor, 1)
            controls += (('input.cir', injected, 'Unexpected stimulus deck statement'),)
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for name, text in original.items():
                (root/name).write_text(text, encoding='ascii')
            row = measurement(root, spec)
            self.assertEqual(row['capacitance_f'], 4.7e-7/(2*math.pi*1_000_000))
            self.assertEqual(row['temperature_k'], 300)
            self.assertEqual(row['op']['v(lower)'], 10)
            for name, text, failure in controls:
                with self.subTest(failure=failure):
                    (root/name).write_text(text, encoding='ascii')
                    with self.assertRaisesRegex(ValueError, failure):
                        measurement(root, spec)
                    (root/name).write_text(original[name], encoding='ascii')


class PublicPlateEvidenceTests(unittest.TestCase):
    def test_included_raw_evidence_reconstructs_physical_electrode_mapping(self):
        source = reader.source_contract(reader.ROOT)
        result = reader.plate_evidence(reader.ROOT, reader.DEFAULT_ARCHIVE)
        manifest = json.loads((reader.ROOT / reader.PUBLIC_PLATES / 'SOURCE.json').read_bytes())
        self.assertEqual(result['archive_sha256'], reader.PUBLIC_ARCHIVE_SHA)
        self.assertEqual(result['parent_archive_sha256'], reader.ARCHIVE_SHA)
        self.assertNotEqual(result['archive_sha256'], result['parent_archive_sha256'])
        self.assertEqual(result['top'], ['c0', 'PLUS', 'C1', 'TopMetal1'])
        self.assertEqual(result['lower'], ['c1', 'MINUS', 'C2', 'Metal5'])
        self.assertEqual({result['selected_member_prefix'] + name: digest
                          for name, digest in result['files'].items()},
                         {name: row['sha256'] for name, row in manifest['selected_members'].items()})
        self.assertEqual(source['files'][reader.PUBLIC_PLATES + '/physical-evidence.zip'],
                         reader.PUBLIC_ARCHIVE_SHA)

    def test_changed_missing_and_repacked_native_evidence_are_not_trusted(self):
        with zipfile.ZipFile(reader.DEFAULT_ARCHIVE) as archive:
            original = {name: archive.read(name) for name in archive.namelist()}
        native = 'default-7-0/job/physical-flow/lvs-extraction/native.cir'
        mask = 'default-7-0/job/physical-flow/layout.gds'
        for fault in ('missing-native', 'changed-native', 'changed-mask', 'repacked'):
            with self.subTest(fault=fault), tempfile.TemporaryDirectory() as folder:
                content = dict(original)
                if fault == 'missing-native':
                    del content[native]
                if fault == 'changed-native':
                    content[native] = content[native].replace(b'C1 C2', b'C2 C1')
                    self.assertNotEqual(content[native], original[native])
                if fault == 'changed-mask':
                    content[mask] = content[mask][:-1] + bytes([content[mask][-1] ^ 1])
                path = Path(folder) / 'changed.zip'
                with zipfile.ZipFile(path, 'x', compression=zipfile.ZIP_STORED) as archive:
                    for name, data in content.items():
                        archive.writestr(name, data)
                with self.assertRaisesRegex(ValueError, 'Audited physical evidence archive differs'):
                    reader.plate_evidence(reader.ROOT, path)

    def test_public_provenance_manifest_must_match_its_source_lock(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            directory = root / reader.PUBLIC_PLATES
            directory.mkdir(parents=True)
            manifest = json.loads((reader.ROOT / reader.PUBLIC_PLATES / 'SOURCE.json').read_bytes())
            manifest['parent_archive_sha256'] = '0' * 64
            (directory / 'SOURCE.json').write_text(json.dumps(manifest), encoding='utf-8')
            with self.assertRaisesRegex(ValueError, 'Public physical evidence manifest differs'):
                reader.plate_evidence(root, reader.DEFAULT_ARCHIVE)


if __name__ == '__main__':
    unittest.main()
