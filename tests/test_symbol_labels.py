"""Imported annotation visibility and live instance values."""
from pathlib import Path
import tempfile
import unittest

from icstudio.catalog_migration import symbol_context
from icstudio.model import device
from icstudio.symbol_geometry import visible_text
from icstudio.symbol_io import import_symbol, symbol_text


class SymbolLabelTests(unittest.TestCase):
    def test_imported_alignment_visibility_and_bold_survive_roundtrip(self):
        with tempfile.TemporaryDirectory() as td:
            path=Path(td)/'part.sym'
            path.write_text('v {xschem version=3.4.8 file_version=1.2}\n'
                            'K {type=subcircuit template="name=X1"}\n'
                            'T {@name} -15 -10 1 1 0.2 0.2 {hide=instance hcenter=true vcenter=true weight=bold}\n',encoding='utf-8')
            symbol,_,_=import_symbol(path)
            item=symbol['primitives'][0]
            self.assertEqual(item['rotation'],90)
            self.assertTrue(all(item[key] for key in ('mirror','hidden','hcenter','vcenter','bold')))
            self.assertEqual(item['text_anchor'],'corner')
            self.assertEqual(visible_text(item,{'name':'X7'}),'')
            self.assertEqual(visible_text(item),'@name')
            exported=symbol_text(symbol)
            self.assertIn('1 1 0.2 0.2 {hcenter=true vcenter=true hide=instance weight=bold}',exported)
            path.write_text(exported,encoding='utf-8')
            restored,_,_=import_symbol(path)
            self.assertEqual(restored['primitives'],symbol['primitives'])

    def test_legacy_diagnostics_hide_but_unknown_design_parameters_remain_visible(self):
        for text in ('@#0:net_name','@#1:pinnumber','I = @spice_get_current'):
            self.assertEqual(visible_text({'text':text},{}),'')
        self.assertEqual(visible_text({'text':'W=@missing'},{}),'W=@missing')
        self.assertEqual(visible_text({'text':'W=@W'},{'W':'4u'}),'W=4u')

    def test_native_edits_override_captured_text_case_aliases(self):
        part=device('SPICE','R7',symbol_context={'value':'1k','W':'2u'},
                    native_spice={'parameters':{'value':'22k','w':'5u'}})
        context=symbol_context(part,{})
        self.assertEqual(context['value'],'22k')
        self.assertEqual(context['W'],'5u')
        self.assertEqual(context['w'],'5u')
        self.assertEqual(context['name'],'R7')

    def test_catalog_default_multiplicity_and_model_resolve_on_canvas(self):
        from icstudio.model import load_project
        project=load_project(Path(__file__).resolve().parents[1]/'examples/sky130_two_stage_opamp.icproj')
        cap=next(d for d in project['cells'][0]['devices'] if d['name']=='CC1')
        context=symbol_context(cap,project['pdk'])
        self.assertEqual(context['MF'],'1')
        self.assertEqual(context['model'],'sky130_fd_pr__cap_mim_m3_1')

    def test_bundled_child_sheet_resolves_its_project_library(self):
        from icstudio.getting_started import example_copy
        project=example_copy({'file':'xschem-amplifier/blocks/gain.sch'})
        transistor=next(d for c in project['cells'] for d in c['devices'] if d['name']=='M1')
        self.assertNotIn('Missing symbol',str(transistor.get('symbol',{})))
        self.assertEqual(set(transistor['nets']),{'D','G','S','B'})


if __name__=='__main__':unittest.main()
