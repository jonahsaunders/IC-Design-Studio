"""Focused controls for the finite, source-backed enclosure runner."""
import copy
from pathlib import Path
import tempfile
import unittest

from scripts.qualify_ihp_cmim_enclosures import build_case, source_locked_contract, validate_case, validate_fault
from scripts.check_ihp_cmim_enclosures import check_stream, expected_masks, extraction_command, reference_device, selection


def layout():
    layers = [{'name': name, 'gds': n, 'datatype': 0} for name, n in
              [('mim', 36), ('metal5', 67), ('top', 126), ('vmim', 129), ('topvia', 125), ('via4', 66)]]
    shapes = [dict(id='m5', layer='metal5', points=[[-4100, -4100], [4100, 4100]]),
              dict(id='top', layer='top', points=[[-3300, -3300], [3300, 3300]]),
              dict(id='cut', layer='vmim', points=[[-210, -210], [210, 210]])]
    return {'pdk': {'layers': layers}, 'cells': [{'id': 'c', 'shapes': shapes, 'ports': ['C1', 'C2'],
                                                  'layout_ports': [], 'layout_texts': []}]}


class EnclosureControls(unittest.TestCase):
    def test_full_selection_rejects_pilot_missing_duplicate_and_reordered_faults(self):
        cases = [dict(rule=r, margin_nm=m, rotation=a) for r, values in (('MIM.c',(580,600,620)), ('MIM.d',(340,360,380))) for m in values for a in (0,90)]
        faults = [dict(fault=n) for n in ('missing-vmim','missing-topvia','wrong-contact-layer','cross-plate-short','wrong-reference-width','swapped-electrodes')]
        report = dict(schema=1,status='OBSERVED_FULL_SELECTION',pilot=False,cases=cases,faults=faults)
        selection(report)
        for mutation in ('pilot','missing','duplicate','reordered','unknown','bool_rotation'):
            bad = copy.deepcopy(report)
            if mutation == 'pilot': bad['pilot'] = True
            elif mutation == 'missing': bad['faults'].pop()
            elif mutation == 'duplicate': bad['faults'][-1] = copy.deepcopy(bad['faults'][0])
            elif mutation == 'reordered': bad['faults'].reverse()
            elif mutation == 'unknown': bad['faults'][0]['fault'] = 'other'
            else: bad['cases'][0]['rotation'] = False
            with self.subTest(mutation=mutation), self.assertRaises(ValueError): selection(bad)

    def test_contract_sources_are_bound(self):
        self.assertEqual(len(source_locked_contract()) >= 21, True)

    def test_metal_enclosure_changes_only_one_edge_and_preserves_vmim(self):
        original = layout(); untouched = copy.deepcopy(original)
        for margin, right in ((580, 4080), (600, 4100), (620, 4120)):
            q = build_case(original, 'MIM.c', margin)
            shapes = q['cells'][0]['shapes']
            self.assertEqual(shapes[0]['points'], [[-4100, -4100], [right, 4100]])
            self.assertEqual(shapes[1:], untouched['cells'][0]['shapes'][1:])
        self.assertEqual(original, untouched)

    def test_topvia_enclosure_uses_actual_125_layer_and_fixed_top_plate(self):
        for margin, right in ((340, 3160), (360, 3140), (380, 3120)):
            q = build_case(layout(), 'MIM.d', margin); shapes = q['cells'][0]['shapes']
            self.assertFalse(any(s['layer'] == 'vmim' for s in shapes))
            self.assertEqual(next(s for s in shapes if s['layer'] == 'top')['points'], [[-3300, -3300], [3580, 3300]])
            self.assertEqual(next(s for s in shapes if s['layer'] == 'topvia')['points'], [[right - 420, -210], [right, 210]])
        with self.assertRaises(ValueError):
            build_case(layout(), 'MIM.d', 350)

    def test_case_requires_exact_target_and_all_three_checks(self):
        stages = {name: 'passed' for name in ('preflight', 'layout_export', 'drc', 'lvs_extraction', 'lvs', 'integrity')}
        stages['drc'] = 'failed'
        checks = [dict(name='main', violations=1, categories=["'MIM.c'"]),
                  dict(name='maximal', violations=0, categories=[]), dict(name='metal-spacing', violations=0, categories=[])]
        result = dict(stages=stages, three_decks=checks)
        validate_case(result, 'MIM.c', True)
        for mutation in ('missing', 'reordered', 'unrelated', 'extra', 'bad-lvs'):
            bad = copy.deepcopy(result)
            if mutation == 'missing': bad['three_decks'].pop()
            elif mutation == 'reordered': bad['three_decks'].reverse()
            elif mutation == 'unrelated': bad['three_decks'][0]['categories'] = ["'MIM.d'"]
            elif mutation == 'extra': bad['three_decks'][2].update(violations=1, categories=["'M5.e'"])
            else: bad['stages']['lvs'] = 'failed'
            with self.subTest(mutation=mutation), self.assertRaises(ValueError):
                validate_case(bad, 'MIM.c', True)

    def test_reference_reader_rejects_extra_device_and_changed_properties(self):
        original = '.subckt coupon C1 C2\nX_C1 C1 C2 cap_cmim l=7e-06 m=1 mm_ok=1 w=7e-06\n.ends coupon\n'
        projected = '.subckt coupon C1 C2\nCX_C1 C1 C2 cap_cmim w=7e-06 l=7e-06 m=1 A=4.9E-11 P=0.000028\n.ends coupon\n'
        reference_device(original, 'X_C1', '7e-6'); reference_device(projected, 'CX_C1', '7e-6')
        for text,prefix in ((original.replace('.ends', 'X_extra C1 C2 cap_cmim w=7e-6\n.ends'),'X_C1'),
                     (original.replace('X_C1 C1 C2','X_C1 C2 C1'),'X_C1'),
                     (original.replace('mm_ok=1','mm_ok=1 mm_ok=1'),'X_C1'), (projected.replace('4.9E-11','0'),'CX_C1'),
                     (projected.replace('w=7e-06','w=NaN'),'CX_C1'), (original.replace('.ends','.param x=1\n.ends'),'X_C1'),
                     (original.replace('.subckt coupon C1 C2','.subckt coupon C2 C1'),'X_C1')):
            with self.subTest(text=text), self.assertRaises(ValueError):
                reference_device(text, prefix, '7e-6')

    def test_extraction_command_rejects_changed_input_and_simplification(self):
        root='/run/lvs-extraction'
        settings=dict(input=root+'/labels.gds',topcell='coupon',report=root+'/extraction.lvsdb',
                      target_netlist=root+'/native.cir',log=root+'/native.log',run_mode='flat',net_only='true',
                      top_lvl_pins='true',no_simplify='true',combine_devices='false',purge='false',
                      purge_nets='false',purge_devices='false',implicit_nets='',disable_tap_extraction='false')
        command=['klayout','-b','-r',root+'/deck/sg13g2.lvs']
        for key,value in settings.items():command+=['-rd',key+'='+value]
        extraction_command(command,settings,'klayout')
        for key,value in (('no_simplify','false'),('input','/other/lvs-extraction/labels.gds'),('topcell','other')):
            bad=copy.deepcopy(settings);bad[key]=value
            changed=['klayout','-b','-r',root+'/deck/sg13g2.lvs']
            for name,item in bad.items():changed+=['-rd',name+'='+item]
            with self.subTest(key=key),self.assertRaises(ValueError):extraction_command(changed,bad,'klayout')

    def test_fault_requires_real_disconnection_and_completed_extraction(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); flow = root / 'job/physical-flow/lvs-extraction'; flow.mkdir(parents=True)
            raw = '.SUBCKT coupon C2\nC$1 \\$4 C2 cap_cmim w=7u l=7u A=49p P=28u m=1\n.ENDS coupon\n'
            console = '\n'.join(('NET_ONLY enabled', 'LVS Total Run time', '[layout_netlist] simplify: SKIPPED',
                                 '[layout_netlist] combine_devices: SKIPPED', '[layout_netlist] purge: SKIPPED',
                                 '[layout_netlist] purge_nets: SKIPPED', '[layout_netlist] purge_devices: SKIPPED'))
            (flow / 'native.cir').write_text(raw); (flow / 'console.log').write_text(console)
            stages = dict(preflight='passed', layout_export='passed', drc='failed', lvs_extraction='failed', lvs='not_run', integrity='not_run')
            checks = [dict(name='main', categories=[], violations=0), dict(name='maximal', categories=["'MIM.h'"], violations=1), dict(name='metal-spacing', categories=[], violations=0)]
            observed = dict(stages=stages, three_decks=checks, error='IHP extracted port names differ from the schematic.')
            validate_fault('missing-topvia', observed, root)
            for mutation in ('short', 'wrong-rule', 'wrong-guard', 'incomplete'):
                bad = copy.deepcopy(observed); (flow / 'native.cir').write_text(raw); (flow / 'console.log').write_text(console)
                if mutation == 'short': (flow / 'native.cir').write_text(raw.replace('\\$4', 'C2'))
                elif mutation == 'wrong-rule': bad['three_decks'][1]['categories'] = ["'MIM.d'"]
                elif mutation == 'wrong-guard': bad['error'] = 'tool crashed'
                else: (flow / 'console.log').write_text('engine failed')
                with self.subTest(mutation=mutation), self.assertRaises(ValueError):
                    validate_fault('missing-topvia', bad, root)

    def test_written_stream_reader_rejects_contact_layer_and_enclosure_mutations(self):
        import klayout.db as k
        with tempfile.TemporaryDirectory() as tmp:
            for mutation in ('none', 'wrong-contact', 'wrong-enclosure', 'wrong-port'):
                ly=k.Layout();ly.dbu=.001;cell=ly.create_cell('coupon');masks=expected_masks('MIM.d',360,0)
                if mutation=='wrong-contact':masks[(66,0)]=masks.pop((125,0))
                if mutation=='wrong-enclosure':masks[(125,0)]=k.Region(k.Box(2740,-210,3160,210))
                for (layer,datatype),region in masks.items():
                    for poly in region.each():cell.shapes(ly.layer(layer,datatype)).insert(poly)
                cell.shapes(ly.layer(126,2)).insert(k.Text('C2' if mutation=='wrong-port' else 'C1',k.Trans(0,0)))
                cell.shapes(ly.layer(67,2)).insert(k.Text('C2',k.Trans(3600,0)))
                path=Path(tmp)/(mutation+'.gds');ly.write(str(path))
                if mutation=='none':check_stream(path,'MIM.d',360,0)
                else:
                    with self.subTest(mutation=mutation),self.assertRaises(ValueError):check_stream(path,'MIM.d',360,0)


if __name__ == '__main__':
    unittest.main()
