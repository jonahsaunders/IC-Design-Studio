"""Negative readback controls for actual MiM terminal bias and native evidence."""
import json
import copy
import math
from pathlib import Path
import struct
import tempfile
import unittest

from scripts import audit_sky130_mim_bias_boundaries as audit

CONTRACT = json.loads((Path(__file__).resolve().parents[1] / 'docs/qualification/sky130-mim-contract-v1.json').read_bytes())
COEFFICIENTS = CONTRACT['passive_sections']['tt']['coefficients']


def samples(analysis='op', bias=5, ground=0):
    result = []
    for i in range(1 if analysis == 'op' else 8):
        row = {'v(par_' + name + ')': complex(COEFFICIENTS.get(name, 0)) for name in audit.PARAMETERS}
        if analysis == 'ac':
            frequency = 1000 * 10 ** i
            row['frequency'] = complex(frequency)
            # Independent fixed-source equation for the first 2 x 10 wrapper.
            w = 2 + 1e6 * (COEFFICIENTS['m3_dw'] + COEFFICIENTS['tol_m3'])
            l = 10 + 1e6 * (COEFFICIENTS['m3_dw'] + COEFFICIENTS['tol_m3'])
            r = COEFFICIENTS['rm3'] * l / w + COEFFICIENTS['rcvia3'] * .56 ** 2 / (w * l)
            c = COEFFICIENTS['camimc'] * w * l + 2 * COEFFICIENTS['cpmimc'] * (w + l)
            y = 1 / complex(r, -1 / (2 * math.pi * frequency * c))
        for branch in audit.BRANCHES:
            row['v(p_' + branch + ')'] = complex(bias if analysis == 'op' else 1)
            row['v(n_' + branch + ')'] = complex(ground if analysis == 'op' else 0)
            row['i(vp_' + branch + ')'] = complex(0) if analysis == 'op' else -y
            row['i(vn_' + branch + ')'] = complex(0) if analysis == 'op' else y
        result.append(row)
    return result


def write_raw(path, rows, analysis='op', binary=False):
    names = list(rows[0])
    header = ('Title: independent native readback fixture\n'
              'Date: retained fixture\n'
              f'Plotname: {"Operating Point" if analysis == "op" else "AC Analysis"}\n'
              f'Flags: {"real" if analysis == "op" else "complex"}\n'
              f'No. Variables: {len(names)}\nNo. Points: {len(rows)}\nVariables:\n')
    header += ''.join(f'\t{i}\t{name}\t{"current" if name.startswith("i(") else "voltage"}\n' for i, name in enumerate(names))
    if binary:
        data = (header + 'Binary:\n').encode()
        data += b''.join(struct.pack('<dd', row[name].real, row[name].imag) if analysis == 'ac' else struct.pack('<d', row[name].real) for row in rows for name in names)
    else:
        text = header + 'Values:\n'
        for i, row in enumerate(rows):
            for j, name in enumerate(names):
                value = row[name]
                token = f'{value.real:.17g},{value.imag:.17g}' if analysis == 'ac' else f'{value.real:.17g}'
                text += (f'{i}\t' if j == 0 else '\t') + token + '\n'
        data = text.encode()
    path.write_bytes(data)


def deck_text(bias=5, analysis='op', fault=None):
    high = 0 if fault == 'missing-bias' else -bias if fault == 'sign-reversed' else math.copysign(4.99, bias) if fault == 'clamped-bias' else bias
    low = .5 if fault == 'displaced-ground' else 0
    text = '* Independent deck fixture\n.lib /locked/models tt\n.param mc_mm_switch=0 mc_pr_switch=0\n.option tnom=27\n.temp 27\n'
    for name in ('schematic', 'independent'):
        text += f'.subckt {name} P N\nX1 P N sky130_fd_pr__cap_mim_m3_1 w=2 l=10 m=1\n.ends {name}\n'
    text += '.include /retained/physical/1/valid-0-plain/lvs-extraction/extracted.spice\n'
    for name in audit.BRANCHES:
        dc = '' if fault == 'missing-bias' else f'DC {high:g} '
        text += f'VP_{name} p_{name} 0 {dc}AC 1\nVN_{name} n_{name} 0 DC {low:g} AC 0\n'
        text += f'X_{name} p_{name} n_{name} ' + ('device_coupon' if name == 'extracted' else name) + '\n'
    for name in audit.PARAMETERS:
        text += f'VPAR_{name} par_{name} 0 DC {{{name}}} AC {{{name}}}\n'
    text += '.op\n' if analysis == 'op' else '.ac dec 1 1k 10G\n'
    return text + '.save ' + ' '.join(sorted(audit.channels('op'))) + '\n.end\n'


class MiMBiasNativeReadbackTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.op = self.root / 'op.raw'
        self.ac = self.root / 'ac.raw'

    def test_real_and_complex_ascii_and_binary_plots_are_read(self):
        for binary in (False, True):
            for bias in (-5, 0, 5):
                with self.subTest(binary=binary, bias=bias):
                    write_raw(self.op, samples(bias=bias), binary=binary)
                    result = audit.check_op(self.op, bias, COEFFICIENTS)
                    self.assertEqual(result['extracted']['differential_V'], bias)
            write_raw(self.ac, samples('ac'), 'ac', binary)
            self.assertEqual(len(audit.check_ac(self.ac, 1, COEFFICIENTS)), 8)

    def test_native_frequency_grid_metadata_is_narrowly_supported(self):
        write_raw(self.ac, samples('ac'), 'ac')
        original = self.ac.read_bytes()
        # The fixture has coefficient channels first; use a raw list with the
        # actual native frequency-first ordering for this metadata check.
        ordered = [{'frequency': row['frequency'], **{k:v for k,v in row.items() if k != 'frequency'}} for row in samples('ac')]
        write_raw(self.ac, ordered, 'ac')
        original = self.ac.read_bytes().replace(b'0\tfrequency\tvoltage', b'0\tfrequency\tfrequency\tgrid=3')
        self.ac.write_bytes(original)
        self.assertEqual(len(audit.check_ac(self.ac, 1, COEFFICIENTS)), 8)
        self.ac.write_bytes(original.replace(b'grid=3', b'grid=4'))
        with self.assertRaisesRegex(ValueError, 'variable table'):
            audit.check_ac(self.ac, 1, COEFFICIENTS)

    def test_unchanged_ac_does_not_hide_missing_wrong_or_clamped_bias(self):
        write_raw(self.ac, samples('ac'), 'ac')
        self.assertEqual(len(audit.check_ac(self.ac, 1, COEFFICIENTS)), 8)
        for actual in (0, -5, 4.99):
            write_raw(self.op, samples(bias=actual))
            with self.subTest(actual=actual), self.assertRaisesRegex(ValueError, 'signed OP'):
                audit.check_op(self.op, 5, COEFFICIENTS)

    def test_correct_differential_does_not_hide_displaced_common_mode(self):
        write_raw(self.op, samples(bias=5.1, ground=.1))
        with self.assertRaisesRegex(ValueError, 'signed OP'):
            audit.check_op(self.op, 5, COEFFICIENTS)

    def test_each_branch_terminal_and_both_currents_are_required(self):
        for branch in audit.BRANCHES:
            for name, value in ((f'v(p_{branch})', 0), (f'v(n_{branch})', .01), (f'i(vp_{branch})', 1e-5), (f'i(vn_{branch})', 1e-5)):
                rows = samples(); rows[0][name] = complex(value)
                write_raw(self.op, rows)
                with self.subTest(name=name), self.assertRaises(ValueError):
                    audit.check_op(self.op, 5, COEFFICIENTS)

    def test_nonfinite_voltage_current_and_coefficient_are_rejected(self):
        for name in ('v(p_extracted)', 'i(vp_schematic)', 'v(par_rm3)'):
            for value in (float('nan'), float('inf'), -float('inf')):
                rows = samples(); rows[0][name] = complex(value)
                write_raw(self.op, rows)
                with self.subTest(name=name, value=value), self.assertRaisesRegex(ValueError, 'Nonfinite'):
                    audit.check_op(self.op, 5, COEFFICIENTS)

    def test_missing_duplicated_wrong_and_truncated_op_plots_are_rejected(self):
        write_raw(self.op, samples())
        original = self.op.read_bytes()
        mutations = [original + original, original.replace(b'Operating Point', b'AC Analysis'), original.replace(b'Flags: real', b'Flags: complex'), original.replace(b'No. Points: 1', b'No. Points: 2'), original[:original.index(b'Values:')], original[:-12]]
        for data in mutations:
            self.op.write_bytes(data)
            with self.subTest(data=data[-50:]), self.assertRaises((ValueError, UnicodeDecodeError)):
                audit.check_op(self.op, 5, COEFFICIENTS)

    def test_missing_or_duplicated_terminal_channel_is_rejected(self):
        rows = samples(); del rows[0]['v(n_extracted)']
        write_raw(self.op, rows)
        with self.assertRaisesRegex(ValueError, 'channels'):
            audit.check_op(self.op, 5, COEFFICIENTS)
        write_raw(self.op, samples())
        self.op.write_bytes(self.op.read_bytes().replace(b'v(n_extracted)', b'v(p_extracted)'))
        with self.assertRaisesRegex(ValueError, 'Duplicated native variable'):
            audit.check_op(self.op, 5, COEFFICIENTS)

    def test_coefficient_section_and_current_balance_cannot_be_forged(self):
        for name, factor in (('v(par_camimc)', 1.1), ('i(vn_extracted)', 0), ('i(vp_schematic)', 1.2), ('v(n_independent)', 1)):
            rows = samples('ac')
            for row in rows:
                row[name] = row[name] * factor if name != 'v(n_independent)' else complex(1)
            write_raw(self.ac, rows, 'ac')
            with self.subTest(name=name), self.assertRaises(ValueError):
                audit.check_ac(self.ac, 1, COEFFICIENTS)

    def test_domain_is_not_extended_by_successful_simulation(self):
        write_raw(self.op, samples())
        for bias in (-5.001, 5.001, float('nan'), float('inf'), -float('inf'), True):
            with self.subTest(bias=bias), self.assertRaisesRegex(ValueError, 'Unsupported requested'):
                audit.check_op(self.op, bias, COEFFICIENTS)

    def test_fault_must_be_the_declared_mutation_not_any_failure(self):
        for fault, high, low in (('missing-bias', 0, 0), ('sign-reversed', -5, 0), ('clamped-bias', 4.99, 0), ('displaced-ground', 5, .5)):
            write_raw(self.op, samples(bias=high, ground=low))
            self.assertTrue(audit.check_fault_op(self.op, 5, COEFFICIENTS, fault))
            write_raw(self.op, samples(bias=high + 1, ground=low))
            with self.subTest(fault=fault), self.assertRaisesRegex(ValueError, 'declared terminal'):
                audit.check_fault_op(self.op, 5, COEFFICIENTS, fault)

    def test_fault_control_requires_current_balance_below_individual_limits(self):
        rows = samples(bias=0)
        rows[0]['i(vp_extracted)'] = complex(9e-13)
        rows[0]['i(vn_extracted)'] = complex(9e-13)
        write_raw(self.op, rows)
        with self.assertRaisesRegex(ValueError, 'KCL imbalance'):
            audit.check_fault_op(self.op, 5, COEFFICIENTS, 'missing-bias')

    def test_saved_bias_and_currents_must_match_raw_not_just_status(self):
        write_raw(self.op, samples())
        record = {'status': 'PASS', 'coefficients': {key: COEFFICIENTS.get(key, 0) for key in audit.PARAMETERS},
                  'paths': {key: {'p_V': 5, 'n_V': 0, 'differential_V': 5, 'i_p_A': 0, 'i_n_A': 0} for key in audit.BRANCHES}}
        audit.check_saved_op(self.op, record)
        for name in ('p_V', 'n_V', 'differential_V', 'i_p_A', 'i_n_A'):
            original = record['paths']['extracted'][name]
            for replacement in (original + 1, float('nan')):
                record['paths']['extracted'][name] = replacement
                with self.subTest(name=name, replacement=replacement), self.assertRaises(ValueError):
                    audit.check_saved_op(self.op, record)
            record['paths']['extracted'][name] = original


class MiMBiasDeckAuditTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / 'probe.cir'
        self.native = '/retained/physical/1/valid-0-plain/lvs-extraction/extracted.spice'
        self.staged = {'tt': '.lib /locked/models tt'}

    def check(self, analysis='op', bias=5, fault=None):
        audit.check_deck(self.path, analysis, 'tt', self.staged, self.native, 1, bias, fault)

    def test_exact_positive_and_declared_negative_decks_pass(self):
        for analysis in ('op', 'ac'):
            for bias in (-5, 0, 5):
                self.path.write_text(deck_text(bias, analysis))
                self.check(analysis, bias)
        for fault in ('missing-bias', 'sign-reversed', 'clamped-bias', 'displaced-ground'):
            self.path.write_text(deck_text(fault=fault)); self.check(fault=fault)

    def test_rehashed_path_model_section_and_bias_substitutions_are_rejected(self):
        original = deck_text()
        changes = [(self.native, self.native.replace('valid-0', 'valid-90')),
                   (self.native, '/manual/identical-netlist.spice'), ('/locked/models tt', '/locked/models hh'),
                   ('m3_1 w=2', 'm3_2 w=2'), ('w=2 l=10', 'w=2.4 l=10'), ('m=1', 'm=2'),
                   ('DC 5 AC 1', 'AC 1'), ('DC 5 AC 1', 'DC -5 AC 1'),
                   ('VN_extracted n_extracted 0 DC 0', 'VN_extracted n_extracted 0 DC .5'),
                   ('X_extracted p_extracted n_extracted', 'X_extracted p_extracted 0'),
                   ('.temp 27', '.temp 125'), ('.end', '.include /unbound/model\n.end')]
        for before, after in changes:
            self.path.write_text(original.replace(before, after))
            with self.subTest(before=before, after=after), self.assertRaises(ValueError):
                self.check()

    def test_duplicate_stimulus_and_missing_saved_terminal_are_rejected(self):
        original = deck_text()
        for mutated in (original.replace('.op', 'VP_schematic p_schematic 0 DC 5 AC 1\n.op'),
                        original.replace(' v(n_extracted)', ''),
                        original.replace('.op', '.op\n.op')):
            self.path.write_text(mutated)
            with self.assertRaises(ValueError): self.check()


class MiMBiasBindingAuditTests(unittest.TestCase):
    def test_elf_dependency_reader_distinguishes_dependency_free_modules(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / 'fixture.so'
            data = bytearray(400)
            data[:6] = b'\x7fELF\x02\x01'
            struct.pack_into('<Q', data, 32, 64)
            struct.pack_into('<HH', data, 54, 56, 2)
            struct.pack_into('<IIQQQQQQ', data, 64, 1, 0, 0, 0x1000, 0, 400, 400, 1)
            struct.pack_into('<IIQQQQQQ', data, 120, 2, 0, 200, 0x1000 + 200, 0, 48, 48, 1)
            struct.pack_into('<qQqQqQ', data, 200, 1, 0, 5, 0x1000 + 300, 0, 0)
            data[300:310] = b'libc.so.6\0'
            path.write_bytes(data)
            self.assertEqual(audit.elf_needed(path), {'libc.so.6'})
            struct.pack_into('<qQ', data, 200, 0, 0)
            path.write_bytes(data)
            self.assertEqual(audit.elf_needed(path), set())
            path.write_bytes(data[:120])
            with self.assertRaisesRegex(ValueError, 'program table'):
                audit.elf_needed(path)

    def test_case_inventory_rejects_omitted_duplicate_and_false_bias_context(self):
        full = [f'p{p}-{s}-r{r}-b{b}' for p in (1, 2) for s in ('tt', 'll', 'hh', 'hl', 'lh') for r in (0, 90) for b in ('m5', '0', 'p5')]
        row = {'name': 'p1-tt-r0-bp5', 'plate': 1, 'section': 'tt', 'rotation': 0, 'bias_V': 5, 'status': 'PASS'}
        report = {'full_declared_cases': full, 'selected_cases': [row['name']], 'cases': [row]}
        audit.case_inventory(report)
        for field, value in (('cases', []), ('cases', [row, row]), ('selected_cases', [row['name'], row['name']]), ('full_declared_cases', full[:-1])):
            changed = copy.deepcopy(report); changed[field] = value
            with self.subTest(field=field), self.assertRaises(ValueError): audit.case_inventory(changed)
        for field, value in (('bias_V', 0), ('rotation', 90), ('plate', 2), ('section', 'hh'), ('status', 'RUNNING')):
            changed = copy.deepcopy(report); changed['cases'][0][field] = value
            with self.subTest(field=field), self.assertRaises(ValueError): audit.case_inventory(changed)

    def test_execution_paths_flags_environment_and_completion_are_bound(self):
        with tempfile.TemporaryDirectory() as temp:
            folder = Path(temp); origin = '/original/p1-tt-r0-bp5/op'
            context = {'execution_root': '/original', 'case': 'p1-tt-r0-bp5'}
            title = audit.execution_title(**context, analysis='op')
            (folder / 'probe.cir').write_text(title + '\nsaved deck')
            (folder / 'probe.raw').write_text('Title: ' + title + '\nVariables:\nsaved raw')
            (folder / 'console.log').write_text('ngspice\nDoing analysis at TEMP = 27.000000 and TNOM = 27.000000\nNo. of Data Rows : 1\n')
            result = {'command': [audit.ENGINE, '-n', '-D', 'filetype=ascii', '-D', 'ngbehavior=hsa', '-b', '-r', origin + '/probe.raw', origin + '/probe.cir'],
                      'cwd': origin, 'environment': dict(audit.NATIVE_ENV),
                      'deck_sha256': audit.sha(folder / 'probe.cir'), 'raw_sha256': audit.sha(folder / 'probe.raw')}
            audit.check_execution(folder, origin, result, 'op', **context)
            changes = []
            changed = copy.deepcopy(result); changed['command'][0] = '/other/ngspice'; changes.append(changed)
            changed = copy.deepcopy(result); changed['command'].remove('-n'); changes.append(changed)
            changed = copy.deepcopy(result); changed['command'][-1] = '/substitute/probe.cir'; changes.append(changed)
            changed = copy.deepcopy(result); changed['cwd'] = '/other'; changes.append(changed)
            changed = copy.deepcopy(result); changed['environment']['HOME'] = '/home/user'; changes.append(changed)
            for changed in changes:
                with self.assertRaisesRegex(ValueError, 'Native command'):
                    audit.check_execution(folder, origin, changed, 'op', **context)
            for log in ('No. of Data Rows : 8\n', 'No. of Data Rows : 1\nNo. of Data Rows : 1\n', 'No. of Data Rows : 1\nError: unexpected failure\n'):
                (folder / 'console.log').write_text(log)
                with self.assertRaises(ValueError): audit.check_execution(folder, origin, result, 'op', **context)

    def test_rehashed_output_swaps_are_bound_to_original_run_case_analysis_and_fault(self):
        with tempfile.TemporaryDirectory() as temp:
            folder = Path(temp); origin = '/original/p1-tt-r0-bp5/op'
            context = {'execution_root': '/original', 'case': 'p1-tt-r0-bp5', 'analysis': 'op', 'fault': None}
            title = audit.execution_title(**context)
            (folder / 'probe.cir').write_text(title + '\n.end\n')
            (folder / 'console.log').write_text('Doing analysis at TEMP = 27 and TNOM = 27\nNo. of Data Rows : 1\n')
            result = {'command': [audit.ENGINE, '-n', '-D', 'filetype=ascii', '-D', 'ngbehavior=hsa', '-b', '-r', origin + '/probe.raw', origin + '/probe.cir'],
                      'cwd': origin, 'environment': dict(audit.NATIVE_ENV), 'deck_sha256': audit.sha(folder / 'probe.cir')}
            for key, value in (('execution_root', '/other-run'), ('case', 'p1-tt-r90-bp5'), ('analysis', 'ac'), ('fault', 'missing-bias')):
                changed = dict(context); changed[key] = value
                (folder / 'probe.raw').write_text('Title: ' + audit.execution_title(**changed) + '\nVariables:\n')
                result['raw_sha256'] = audit.sha(folder / 'probe.raw')
                with self.subTest(key=key), self.assertRaisesRegex(ValueError, 'raw execution title'):
                    audit.check_execution(folder, origin, result, **context)
            (folder / 'probe.raw').write_text('Title: ' + title + '\nVariables:\n')
            result['raw_sha256'] = audit.sha(folder / 'probe.raw')
            audit.check_execution(folder, origin, result, **context)
            # A relocated archive still uses original execution identity.
            (folder / 'probe.cir').write_text(title.replace('v1 ', 'v2 ') + '\n.end\n')
            result['deck_sha256'] = audit.sha(folder / 'probe.cir')
            with self.assertRaisesRegex(ValueError, 'deck execution title'):
                audit.check_execution(folder, origin, result, **context)

    def test_transitive_elf_dependency_omission_is_rejected(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            def elf(path, needed):
                data = bytearray(400); data[:6] = b'\x7fELF\x02\x01'
                struct.pack_into('<Q', data, 32, 64)
                struct.pack_into('<HH', data, 54, 56, 2)
                struct.pack_into('<IIQQQQQQ', data, 64, 1, 0, 0, 0x1000, 0, 400, 400, 1)
                struct.pack_into('<IIQQQQQQ', data, 120, 2, 0, 200, 0x1000 + 200, 0, 48, 48, 1)
                if needed:
                    struct.pack_into('<qQqQqQ', data, 200, 1, 0, 5, 0x1000 + 300, 0, 0)
                    value = needed.encode() + b'\0'; data[300:300 + len(value)] = value
                path.write_bytes(data)
            exe, first, transitive = root / 'program', root / 'libfirst.so', root / 'libindirect.so'
            elf(exe, first.name); elf(first, transitive.name); elf(transitive, None)
            audit.check_elf_closure(exe.as_posix(), {first.as_posix(): {}, transitive.as_posix(): {}})
            with self.assertRaisesRegex(ValueError, 'Missing actual ELF dependency'):
                audit.check_elf_closure(exe.as_posix(), {first.as_posix(): {}})


if __name__ == '__main__':
    unittest.main()
