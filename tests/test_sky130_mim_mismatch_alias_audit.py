"""Independent parser/identity controls; synthetic fixtures are not native evidence."""
import copy
import hashlib
import json
import math
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from scripts import audit_sky130_mim_mismatch_aliases as audit


class AliasAuditTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.execution = dict(root='C:\\evidence\\native', nonce='a' * 32)
        self.case = audit.cases(True)['tt-m1-application-base']
        self.spec = json.loads((audit.ROOT/audit.CONTRACT).read_bytes())

    def raw(self, case=None):
        case = case or self.case
        names = ['frequency'] + [v for t in audit.TAGS for v in (f'v({t})', f'i(v{t})')]
        names += [f'v(par_{k})' for k in audit.PARAMETERS]
        values = audit.coefficients(case['actual_section'], self.spec)
        lines = ['Title: '+audit.context_title(self.execution, case['name']), 'Plotname: AC Analysis',
                 'Flags: complex', 'No. Variables: 29', 'No. Points: 3', 'Variables:']
        for i, name in enumerate(names):
            kind = 'frequency grid=3' if i == 0 else ('current' if name.startswith('i(') else 'voltage')
            lines.append(f'{i} {name} {kind}')
        lines.append('Values:')
        for index, frequency in enumerate((1000, 10000, 100000)):
            sample = [complex(frequency, float('nan'))]
            for tag in audit.TAGS:
                resistance, capacitance = audit.rc(int(tag[1]), values)
                sample += [1+0j, -1/complex(resistance, -1/(2*math.pi*frequency*capacitance))]
            sample += [complex(values[k]) for k in audit.PARAMETERS]
            for i, value in enumerate(sample):
                lines.append((str(index)+' ' if i == 0 else '')+f'{value.real:.17e},{value.imag:.17e}')
        return '\n'.join(lines)+'\n'

    def write_raw(self, text):
        p = self.root/'sample.raw'; p.write_text(text, encoding='ascii'); return p

    def test_actual_channels_reconstruct_rc_and_saved_summary(self):
        result = audit.observe(self.write_raw(self.raw()), self.case, self.execution, self.spec)
        self.assertEqual(set(result['raw_summary']['samples']), set(audit.TAGS))
        self.assertEqual(len(result['raw_summary']['samples']['p1t0']), 3)
        self.assertAlmostEqual(result['capacitances']['p1t0'], 4.394225e-14, delta=1e-26)
        self.assertEqual(result['raw_summary']['coefficients']['mc_mm_switch'], 0)

    def test_raw_identity_plot_count_duplicate_and_nonfinite_rejected(self):
        raw = self.raw()
        mutations = [raw.replace('AC Analysis', 'Operating Point'), raw.replace('Flags: complex', 'Flags: real'),
                     raw.replace('No. Points: 3', 'No. Points: 2'), raw.replace('v(p1t1)', 'v(p1t0)'),
                     raw.replace('Title:', 'Title: incorrect\nTitle:', 1),
                     raw.replace('1.00000000000000000e+00,0.00000000000000000e+00', 'nan,0', 1),
                     raw.replace('0 frequency frequency grid=3', '0 frequency voltage'), raw+'0,0\n',
                     raw.replace(audit.context_title(self.execution, self.case['name']), '* another-execution')]
        for i, text in enumerate(mutations):
            with self.subTest(i=i), self.assertRaises(ValueError):
                audit.observe(self.write_raw(text), self.case, self.execution, self.spec)

    def test_wrong_current_voltage_switch_and_frequency_rejected(self):
        raw = self.raw()
        for old, new in [('1.00000000000000000e+00,0.00000000000000000e+00', '2,0'),
                         ('0 1.00000000000000000e+03,nan', '0 2000,nan')]:
            with self.subTest(old=old), self.assertRaises(ValueError):
                audit.observe(self.write_raw(raw.replace(old,new,1)), self.case, self.execution, self.spec)
        alias = dict(self.case, actual_section='tt_mm')
        with self.assertRaisesRegex(ValueError, 'switch'):
            audit.observe(self.write_raw(raw), alias, self.execution, self.spec)

    def deck(self, case):
        selected = {case['actual_section']: '.lib models.spice '+case['actual_section']}
        count = '' if case['variant'] == 'missing-m' else f" m={case['multiplier']}"
        calls = [f"X_{t} {t} 0 sky130_fd_pr__cap_mim_m3_{t[1]} w=2 l=10 mf={case['multiplier']}{count}" for t in audit.TAGS]
        lines = [audit.context_title(self.execution,case['name']),selected[case['actual_section']],'.option seed=20261024 tnom=27','.temp 27']
        lines += [f'V{t} {t} 0 DC 0 AC 1' for t in audit.TAGS] + calls
        lines += [f'Vpar_{k} par_{k} 0 DC {{{k}}} AC {{{k}}}' for k in audit.PARAMETERS]
        channels = [v for t in audit.TAGS for v in (f'v({t})',f'i(v{t})')] + [f'v(par_{k})' for k in audit.PARAMETERS]
        lines += ['.save '+' '.join(channels),'.ac dec 1 1k 100k','.end']
        return '\n'.join(lines), selected, {case['multiplier']:'\n'.join(calls)}

    def test_deck_rejects_alias_override_seed_geometry_and_extra_element(self):
        case = audit.cases(True)['tt-m1-application-alias']
        text, selected, application = self.deck(case)
        audit.check_deck(text,case,selected,self.execution,application)
        for changed in [text.replace('tt_mm','ll_mm'),text.replace('.temp 27','.param mc_mm_switch=1\n.temp 27'),
                        text.replace('seed=20261024','seed=1'),text.replace('w=2','w=3',1),
                        text.replace('.end','Rhidden p1t0 0 100\n.end'),text.replace('mf=1','mf=4',1)]:
            with self.subTest(text=changed[-80:]), self.assertRaises(ValueError):
                audit.check_deck(changed,case,selected,self.execution,application)

    def test_missing_m_control_requires_literal_omission(self):
        case = audit.cases(True)['tt-m4-missing-m']
        text, selected, application = self.deck(case)
        audit.check_deck(text,case,selected,self.execution,application)
        with self.assertRaisesRegex(ValueError,'Parameter'):
            audit.check_deck(text.replace('mf=4','mf=4 m=1'),case,selected,self.execution,application)

    def test_paired_mapping_and_each_fault_must_be_observable(self):
        observations = {}
        for case in audit.cases(True).values():
            m, variant = case['multiplier'], case['variant']
            delta = .01 if variant != 'application-base' else 0
            cap = 100*m*(1+delta/math.sqrt(m))
            if variant == 'wrong-mf': cap = 400*1.01
            if variant == 'missing-m': cap = 100*1.005
            observations[case['name']] = dict(capacitances={t:cap for t in audit.TAGS}, coefficients=audit.coefficients(case['actual_section'],self.spec))
        self.assertEqual(len(audit.compare(observations,['tt'])),1)
        for variant in ('literal-alias','wrong-mf','missing-m'):
            changed = copy.deepcopy(observations)
            key = 'tt-m4-'+variant
            if variant == 'literal-alias': changed[key]['capacitances']['p1t0'] *= 1.01
            else: changed[key]['capacitances'] = changed['tt-m4-application-alias']['capacitances']
            with self.subTest(variant=variant),self.assertRaises(ValueError): audit.compare(changed,['tt'])

    def test_context_supports_both_platforms_and_rejects_other_run(self):
        linux = dict(root='/var/tmp/native',nonce='a'*32)
        self.assertNotEqual(audit.context_title(linux,'case'),audit.context_title(self.execution,'case'))
        with self.assertRaises(ValueError): audit.context_title(dict(root='relative',nonce='a'*32),'case')

    def test_runtime_initializer_and_linux_closure_substitution_rejected(self):
        # Fail before blob parsing: rehashed unreviewed configuration is not a new profile.
        (self.root/'runtime-assets.json').write_text('{}')
        common = dict(engine='C:\\engine\\ngspice.exe',platform='win32',machine='AMD64',sha256=audit.ENGINE_SHA,
                      environment={'SystemRoot':'C:\\Windows'},elf_dependencies={},dependency_listing=None)
        with self.assertRaisesRegex(ValueError,'companion manifest'):
            audit.runtime_profile(self.root,common,self.execution)
        linux = dict(engine='/usr/bin/ngspice',platform='linux',machine='x86_64',sha256=audit.LINUX_ENGINE_SHA,
                     environment={},files={},elf_dependencies={})
        with self.assertRaisesRegex(ValueError,'complete resolved library closure'):
            audit.runtime_profile(self.root,linux,dict(root='/var/tmp/native',nonce='a'*32))

    def test_json_duplicate_nonfinite_and_path_escape_rejected(self):
        p = self.root/'x.json'
        for text in ('{"x":1,"x":2}','{"x":NaN}'):
            p.write_text(text)
            with self.assertRaises(ValueError): audit.load(p)
        for name in ('../outside','a/../outside','/outside','C:/outside','a\\b'):
            with self.assertRaises(ValueError): audit.relative(name)


if __name__ == '__main__': unittest.main()
