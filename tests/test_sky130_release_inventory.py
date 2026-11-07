import copy
import hashlib
import io
import json
import struct
import tarfile
import tempfile
import types
import unittest
from pathlib import Path
from unittest import mock

from scripts.inventory_sky130_release import (
    ASSETS, RELEASE, RELEASE_ID, REPOSITORY, archive_rows, catalog_reconciliation,
    gds, index_rows, liberty, reconcile, selected_cells, semantic, spice,
    verified_metadata, node_metadata, source_text_identity,
)


class ReleaseIdentityTests(unittest.TestCase):
    def inputs(self):
        return dict(repository=REPOSITORY, tag=RELEASE, release_id=RELEASE_ID,
                    archives=[dict(name=name, id=identity, bytes=size, sha256=digest,
                                   upstream_digest=None, local_path='host-specific/' + name,
                                   url=f'https://github.com/{REPOSITORY}/releases/download/{RELEASE}/{name}',
                                   api_url=f'https://api.github.com/repos/{REPOSITORY}/releases/assets/{identity}')
                              for name, (identity, size, digest) in ASSETS.items()])

    def test_all_seven_exact_release_assets_and_portable_metadata(self):
        result = verified_metadata(self.inputs())
        self.assertEqual(len(result['archives']), 7)
        self.assertNotIn('local_path', json.dumps(result))

    def test_missing_duplicate_extra_and_changed_assets_fail(self):
        for fault in ('missing', 'duplicate', 'extra', 'hash', 'size', 'id', 'url', 'api', 'digest', 'release'):
            data = self.inputs()
            if fault == 'missing':
                data['archives'].pop()
            elif fault == 'duplicate':
                data['archives'][-1] = copy.deepcopy(data['archives'][0])
            elif fault == 'extra':
                data['archives'].append(dict(data['archives'][0], name='new-library.tar.zst'))
            elif fault == 'release':
                data['release_id'] += 1
            else:
                field = {'hash': 'sha256', 'size': 'bytes', 'api': 'api_url', 'digest': 'upstream_digest'}.get(fault, fault)
                data['archives'][0][field] = 'changed'
            with self.subTest(fault=fault), self.assertRaises(ValueError):
                verified_metadata(data)


class SemanticDeclarationTests(unittest.TestCase):
    def test_spice_continuations_parameters_and_comments_preserve_terminal_order(self):
        result = spice('* .subckt invented A B\n.subckt actual D G\n+ S B params: w=1 l=2\n'
                       '* + wrong_terminal\n.model bin.0 nmos (level=54\n+ vth0=.5)\n.ends\n', '.spice')
        self.assertEqual(result['declarations'][0]['terminals'], ['D', 'G', 'S', 'B'])
        self.assertEqual(result['declarations'][0]['parameters'], ['l', 'w'])
        self.assertEqual(result['declarations'][1]['model_type'], 'nmos')
        self.assertEqual(result['declarations'][1]['parameters'], ['level', 'vth0'])
        self.assertEqual(result['declarations'][1]['parent'], 'actual')

    def test_liberty_uses_declarations_not_filename_comments_or_functions(self):
        data = b'''/* cell (fake) { } */
        library(real) {
          operating_conditions(tt) { voltage:1.8; temperature:25; process:1; }
          cell(actual) { pin(A) { direction:input; }
             pin(Z) { direction:output; function:"A /*literal*/ {"; }
             pg_pin(VDD) { pg_type:primary_power; } }
        }'''
        parsed = semantic('sky130A/libs.ref/test/lib/misleading.lib', data)
        self.assertEqual([r['name'] for r in parsed['declarations']], ['actual'])
        self.assertEqual(parsed['declarations'][0]['pins'][1]['function_identity'], source_text_identity('A /*literal*/ {'))
        self.assertNotIn('function', parsed['declarations'][0]['pins'][1])
        self.assertEqual(parsed['operating_conditions'][0]['voltage'], '1.8')
        with self.assertRaisesRegex(ValueError, 'Unclosed'):
            liberty('library(x) { cell(y) { pin(A) {} }')

    def test_lef_pins_and_verilog_unelaborated_power_options_are_explicit(self):
        lef = semantic('sky130A/x.lef', b'MACRO actual\n PIN A\n DIRECTION INPUT ;\n END A\nEND actual\n')
        self.assertEqual(lef['declarations'][0]['pins'], [dict(name='A', direction='input')])
        verilog = semantic('sky130A/x.v', b'// module fake();\nmodule actual (A,\n`ifdef USE_POWER_PINS\nVDD,\n`endif\nZ); endmodule')
        self.assertEqual(verilog['declarations'][0]['name'], 'actual')
        self.assertFalse(verilog['declarations'][0]['elaborated'])
        self.assertEqual(verilog['declarations'][0]['conditional_macros'], ['USE_POWER_PINS'])
        self.assertNotIn('interface', verilog['declarations'][0])

    def test_gds_structure_names_are_read_from_records_and_truncation_rejected(self):
        record = lambda kind, dtype=0, value=b'': struct.pack('>HBB', len(value)+4, kind, dtype) + value
        data = (record(0, 2, b'\0\3') + record(1, 2, b'\0'*24) + record(2, 6, b'lib\0') +
                record(5, 2, b'\0'*24) + record(6, 6, b'cell') + record(7) + record(4))
        self.assertEqual(gds(data)['declarations'], [dict(kind='gds_structure', name='cell')])
        for bad in (data[:-1], b'\0\0\6\6', record(6, 6, b'cell'), b''):
            with self.subTest(data=bad), self.assertRaises(ValueError):
                gds(bad)

    def test_quoted_fake_liberty_and_verilog_declarations_never_enter_inventory(self):
        parsed = liberty('library(real) { comment:"cell(fake) {pin(FAKE) {direction:input;}}"; '
                         'cell(actual) {comment:"pin(FAKE) {direction:input;}"; '
                         'pin(A) {comment:"direction:output;"; direction:input;}} }')
        self.assertEqual([d['name'] for d in parsed['declarations']], ['actual'])
        self.assertEqual(parsed['declarations'][0]['pins'], [dict(name='A', kind='pin', direction='input')])
        result = semantic('sky130A/x.v', b'module actual(input A); initial $display("module fake(input F); endmodule"); endmodule')
        self.assertEqual([d['name'] for d in result['declarations']], ['actual'])

    def test_escaped_verilog_and_inline_lef_interfaces_are_retained(self):
        result = semantic('sky130A/x.v', b'module \\actual.with.dot (input A); endmodule')
        self.assertEqual(result['declarations'][0]['name'], 'actual.with.dot')
        self.assertEqual(result['declarations'][0]['literal_identifier'], '\\actual.with.dot')
        for value in (b'MACRO actual PIN A DIRECTION INPUT ; END A END actual',
                      b'MACRO actual # comment\nPIN A DIRECTION INPUT ; END A END actual'):
            with self.subTest(value=value):
                result = semantic('sky130A/x.lef', value)
                self.assertEqual(result['declarations'][0]['pins'], [dict(name='A', direction='input')])

    def test_verilog_lifetime_is_not_a_cell_name_and_broken_quotes_fail(self):
        result = semantic('sky130A/x.v', b'module automatic actual(input A); endmodule')
        self.assertEqual(result['declarations'][0]['name'], 'actual')
        self.assertEqual(result['declarations'][0]['lifetime'], 'automatic')
        for path, content in (('sky130A/x.v', b'module actual(input A); initial $display("module fake(); endmodule'),
                              ('sky130A/x.lib', b'library(real) {comment:"cell(fake) {}}')):
            with self.subTest(path=path), self.assertRaisesRegex(ValueError, 'Unterminated quoted'):
                semantic(path, content)

    def test_magic_names_are_explicitly_filename_identity_not_electrical_evidence(self):
        result = semantic('sky130A/libs.ref/fonts/mag/glyph.mag', b'magic\ntech sky130A\nuse child inst\n<< end >>\n')
        self.assertEqual(result['declarations'], [])
        self.assertIn('not an electrical', result['identifier_basis'])
        self.assertEqual(result['referenced_cells'], ['child'])


class ReconciliationTests(unittest.TestCase):
    def fixture(self):
        profile = dict(corners={'typical': ['lib/selected.lib']})
        base = 'sky130A/libs.ref/sky130_fd_sc_hd/'
        rows = []
        for path, content in (
            ('lib/selected.lib', b'library(tt) { cell(actual) { pin(A) {direction:input;} pin(Z) {direction:output;} pg_pin(VDD) {pg_type:primary_power;} } }'),
            ('lef/misleading-name.lef', b'MACRO actual\nPIN A\nDIRECTION INPUT ;\nEND A\nPIN Z\nDIRECTION OUTPUT ;\nEND Z\nPIN VDD\nUSE POWER ;\nEND VDD\nEND actual\n'),
            ('spice/misleading-name.spice', b'.subckt actual A Z VDD\n.ends\n')):
            rows.append(dict(path=base+path, process='sky130A', library='sky130_fd_sc_hd', semantic=semantic(base+path, content)))
        for process in ('sky130A', 'sky130B'):
            rows.append(dict(path=process+'/.config/nodeinfo.json', process=process, library='(technology/support)',
                             nodeinfo=dict(node=process, commit={'open_pdks': RELEASE.removeprefix('sky130-')},
                                           options=['METAL5', 'MIM'], description='fixture',
                                           stdcells={'sky130_fd_sc_hd': 'present', 'sky130_fd_sc_hs': 'unknown'})))
        return rows, profile

    def test_selected_profile_reconciles_real_identifiers_and_preserves_missing_views(self):
        rows, profile = self.fixture()
        report = reconcile(rows, {}, profile)
        cell = report['selected_hd_cells'][0]
        self.assertFalse(cell['qualified'])
        self.assertEqual([r['status'] for r in cell['comparisons']],
                         ['pin_sets_agree', 'pin_sets_agree', 'missing_same_identifier', 'missing_same_identifier', 'missing_same_identifier'])
        unknown = report['process_options'][0]['options'][1]
        self.assertEqual(unknown['disposition'], 'upstream_unknown_not_in_release')
        self.assertFalse(unknown['release_library_present'])

    def test_same_filename_wrong_declared_cell_does_not_match(self):
        rows, profile = self.fixture()
        rows[1]['semantic']['declarations'][0]['name'] = 'other'
        files, index = index_rows(rows)
        cell = selected_cells(files, index, profile)[0]
        self.assertEqual(cell['comparisons'][0]['status'], 'missing_same_identifier')

    def test_missing_cell_in_another_selected_corner_is_explicit(self):
        rows, profile = self.fixture()
        profile['corners']['fast'] = ['lib/fast.lib']
        rows.append(dict(path='sky130A/libs.ref/sky130_fd_sc_hd/lib/fast.lib', process='sky130A', library='sky130_fd_sc_hd',
                         semantic=liberty('library(fast) {cell(other) {pin(A) {direction:input;}}}')))
        result = reconcile(rows, {}, profile)
        actual = next(r for r in result['selected_cell_corner_coverage'] if r['name'] == 'actual')
        self.assertEqual(actual['corners']['fast'], 'missing_from_selected_corner')

    def test_upstream_unknown_with_present_library_remains_an_explicit_conflict(self):
        rows, profile = self.fixture()
        rows[-2]['nodeinfo']['stdcells']['sky130_fd_sc_hd'] = 'unknown'
        result = reconcile(rows, {}, profile)
        hd = next(r for r in result['process_options'][0]['options'] if r['name'] == 'sky130_fd_sc_hd')
        self.assertEqual(hd['disposition'], 'upstream_unknown_but_library_present_review_required')

    def test_missing_pin_changed_direction_and_extra_terminal_are_findings(self):
        for fault in ('missing_pin', 'direction', 'extra_terminal'):
            rows, profile = self.fixture()
            if fault == 'missing_pin':
                rows[1]['semantic']['declarations'][0]['pins'].pop(0)
            elif fault == 'direction':
                rows[1]['semantic']['declarations'][0]['pins'][0]['direction'] = 'output'
            else:
                rows[2]['semantic']['declarations'][0]['terminals'].append('UNEXPECTED')
            files, index = index_rows(rows)
            comparisons = selected_cells(files, index, profile)[0]['comparisons']
            check = comparisons[1 if fault == 'extra_terminal' else 0]
            with self.subTest(fault=fault):
                self.assertIn('difference_review_required', check['status'])

    def test_missing_selected_corner_wrong_process_and_duplicate_paths_fail(self):
        for fault in ('corner', 'process', 'duplicate'):
            rows, profile = self.fixture()
            if fault == 'corner':
                rows.pop(0)
            elif fault == 'process':
                rows[-1]['nodeinfo']['commit']['open_pdks'] = 'wrong'
            else:
                rows.append(copy.deepcopy(rows[0]))
            with self.subTest(fault=fault), self.assertRaises(ValueError):
                reconcile(rows, {}, profile)

    def test_model_suffix_aliases_are_not_silently_bound_and_unavailability_blocks(self):
        rows, profile = self.fixture()
        rows.append(dict(path='sky130A/model.spice', process='sky130A', library='sky130_fd_pr',
                         semantic=spice('.subckt cap_nhv C0 C1 B SHIELD\n.ends\n', '.spice')))
        _, index = index_rows(rows)
        catalog = {'one': dict(model='cap', prefix='X', pin_order=['C0', 'C1', 'B']),
                   'two': dict(model='cap_nhv', prefix='X', pin_order=['C0', 'C1', 'B'], unavailable='No validated mapping')}
        result = catalog_reconciliation(catalog, index)
        self.assertEqual(result[0]['declarations'], [])
        self.assertEqual(result[1]['disposition'], 'catalog_unavailable_still_blocks')
        self.assertFalse(result[1]['matching_terminal_order_present'])

    def test_bus_without_bit_expansion_cannot_pass_pin_comparison(self):
        rows, profile = self.fixture()
        rows[0]['semantic'] = liberty('library(tt) {cell(actual) {bus(A) {bus_type:BUS2;direction:input;} pg_pin(VDD) {pg_type:primary_power;}}}')
        rows[1]['semantic'] = semantic('sky130A/x.lef', b'MACRO actual PIN VDD USE POWER ; END VDD END actual')
        files, index = index_rows(rows)
        check = selected_cells(files, index, profile)[0]['comparisons'][0]
        self.assertEqual(check['status'], 'bus_interface_requires_expansion_review')

    def test_declared_internal_timing_pin_is_not_an_external_layout_terminal(self):
        rows, profile = self.fixture()
        rows[0]['semantic']['declarations'][0]['pins'].append(dict(kind='pin', name='M0', direction='internal'))
        files, index = index_rows(rows)
        result = selected_cells(files, index, profile)[0]
        self.assertEqual(result['declared_internal_pins'], ['M0'])
        self.assertEqual(result['comparisons'][0]['status'], 'pin_sets_agree')

    def test_explicit_pinless_pdk_control_is_not_counted_as_missing_device(self):
        result = catalog_reconciliation({'corner': dict(model='corner', kind='PDK', unavailable='No electrical pins in this symbol.')}, {})
        self.assertEqual(result[0]['disposition'], 'non_electrical_pdk_control_metadata')

    def test_nested_decoy_and_wrong_prefix_do_not_establish_catalog_binding(self):
        content = '.subckt wrapper A B\n.subckt decoy A B\n.ends\n.ends\n.model wrong nmos (level=54)\n'
        row = dict(path='sky130A/models.spice', process='sky130A', library='sky130_fd_pr',
                   semantic=spice(content, '.spice'))
        _, index = index_rows([row])
        result = catalog_reconciliation({'decoy': dict(model='decoy', prefix='X'),
                                         'wrong': dict(model='wrong', prefix='X')}, index)
        self.assertTrue(all(r['declarations'] == [] for r in result))

    def test_scope_conditions_and_case_insensitive_terminal_comparison_preserved(self):
        content = '.lib tt\n.if (ENABLE)\n.subckt Device A b\n.ends\n.endif\n.endl tt\n'
        row = dict(path='sky130A/models.spice', process='sky130A', library='sky130_fd_pr',
                   semantic=spice(content, '.spice'))
        _, index = index_rows([row])
        result = catalog_reconciliation({'device': dict(model='DEVICE', prefix='X', pin_order=['a', 'B'])}, index)[0]
        self.assertEqual(result['declarations'][0]['section'], 'tt')
        condition = result['declarations'][0]['conditions'][0][0]
        self.assertEqual(condition, dict(operator='.if', **source_text_identity('.if (ENABLE)')))
        self.assertTrue(result['matching_terminal_order_present'])
        self.assertFalse(result['qualified'])

    def test_retained_metadata_contains_no_source_headers_prose_or_expressions(self):
        node = node_metadata(dict(node='sky130A', description='Unique upstream descriptive prose', options=['METAL5']))
        verilog = semantic('sky130A/x.v', b'module actual(input UNIQUE_SOURCE_HEADER); endmodule')
        lib = liberty('library(x) {cell(actual) {pin(Z) {direction:output; function:"UNIQUE_BOOLEAN_SOURCE";}}}')
        model = spice('.if (UNIQUE_CONDITION_SOURCE)\n.subckt actual A B\n.ends\n.endif\n', '.spice')
        text = json.dumps(dict(node=node, verilog=verilog, lib=lib, model=model))
        for fragment in ('Unique upstream descriptive prose', 'UNIQUE_SOURCE_HEADER', 'UNIQUE_BOOLEAN_SOURCE', 'UNIQUE_CONDITION_SOURCE'):
            self.assertNotIn(fragment, text)
        self.assertEqual(node['options'], ['METAL5'])
        self.assertEqual(model['declarations'][0]['conditions'][0][0]['operator'], '.if')


class ArchiveIntegrityTests(unittest.TestCase):
    def scan(self, members, fault=None):
        decoder = types.SimpleNamespace(stream_reader=lambda stream: io.BytesIO(stream.read()))
        fake = types.SimpleNamespace(ZstdDecompressor=lambda: decoder)
        with tempfile.TemporaryDirectory() as tmp, mock.patch.dict('sys.modules', zstandard=fake):
            path = Path(tmp) / 'test.tar.zst'
            with tarfile.open(path, 'w') as archive:
                for name, kind in members:
                    item = tarfile.TarInfo(name)
                    item.type = kind
                    item.size = 4 if kind == tarfile.REGTYPE else 0
                    archive.addfile(item, io.BytesIO(b'data') if item.size else None)
            digest = hashlib.sha256(path.read_bytes()).hexdigest()
            size = path.stat().st_size
            return archive_rows(path, '0'*64 if fault == 'hash' else digest, size + (1 if fault == 'size' else 0))

    def test_changed_size_hash_unsafe_duplicate_nonregular_and_other_process_rejected(self):
        for fault in ('size', 'hash'):
            with self.subTest(fault=fault), self.assertRaises(ValueError):
                self.scan([('sky130A/source', tarfile.REGTYPE)], fault)
        for members in ([('sky130A/source', tarfile.REGTYPE)]*2,
                        [('sky130A/../source', tarfile.REGTYPE)],
                        [('sky130C/source', tarfile.REGTYPE)],
                        [('sky130A/link', tarfile.SYMTYPE)]):
            with self.subTest(members=members), self.assertRaises(ValueError):
                self.scan(members)

    def test_all_processes_retained_without_execution(self):
        rows = self.scan([('sky130A/tool.py', tarfile.REGTYPE), ('sky130B/tool.py', tarfile.REGTYPE)])
        self.assertEqual([r['process'] for r in rows], ['sky130A', 'sky130B'])
        self.assertTrue(all('semantic' not in r for r in rows))


if __name__ == '__main__':
    unittest.main()
