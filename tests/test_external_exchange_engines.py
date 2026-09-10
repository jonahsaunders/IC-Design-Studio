"""Destination-tool tests; CI installs real Xschem and Magic executables."""
import os
import re
import shutil
import tempfile
import unittest
from pathlib import Path
from icstudio.external_tools import xschem_netlist,magic_workspace,magic_workspace_export
from icstudio.model import example,uid,file_digest
from icstudio.layout import rect
from icstudio.layout_exchange import review

XSCHEM=os.environ.get('ICSTUDIO_TEST_XSCHEM') or shutil.which('xschem')
MAGIC=os.environ.get('ICSTUDIO_TEST_MAGIC') or shutil.which('magic')


class ExternalExchangeEngineTests(unittest.TestCase):
    @unittest.skipUnless(XSCHEM,'Set ICSTUDIO_TEST_XSCHEM or install Xschem for destination-tool tests.')
    def test_xschem_executes_vector_and_tcl_semantics_and_retains_evidence(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);source=root/'source';source.mkdir()
            (source/'vector.sym').write_text('v {xschem version=3.4.7 file_version=1.2}\nK {type=primitive format="tcleval(@name @pinlist [expr {2*1000}])" template="name=R1"}\nB 5 -2 -32 2 -28 {name=p dir=inout}\nB 5 -2 28 2 32 {name=n dir=inout}\n')
            path=source/'top.sch';path.write_text('v {xschem version=3.4.7 file_version=1.2}\nC {vector.sym} 0 0 0 0 {name=R[1:0]}\nC {lab_pin.sym} 0 -30 0 0 {name=p1 lab=data[1:0]}\nC {gnd.sym} 0 30 0 0 {name=g1 lab=GND}\n')
            report=xschem_netlist(path,root/'run',XSCHEM);self.assertEqual(report['status'],'complete')
            text='\n'.join(p.read_text() for p in (root/'run/netlists').glob('*.spice'))
            self.assertIn('data[1]',text);self.assertIn('data[0]',text);self.assertIn('2000',text);self.assertNotIn('tcleval',text)
            self.assertTrue((root/'run/engine.log').is_file());self.assertTrue(report['inputs'])
            path.write_text(path.read_text().replace('vector.sym','missing.sym'))
            with self.assertRaises((ValueError,RuntimeError)):xschem_netlist(path,root/'broken',XSCHEM)

    @unittest.skipUnless(MAGIC,'Set ICSTUDIO_TEST_MAGIC or install Magic for destination-tool tests.')
    def test_native_magic_cells_ports_and_moved_instance_roundtrip(self):
        candidates=[Path(os.environ['ICSTUDIO_TEST_MAGIC_TECH'])] if os.environ.get('ICSTUDIO_TEST_MAGIC_TECH') else [Path('/usr/lib/x86_64-linux-gnu/magic/sys/scmos.tech'),Path('/usr/local/lib/magic/sys/scmos.tech')]
        technology=next((p for p in candidates if p.is_file()),None)
        if technology is None:self.fail('The installed Magic test runtime must provide scmos.tech or ICSTUDIO_TEST_MAGIC_TECH.')
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);p=example('empty');c=p['cells'][0];c['ports']=['A'];c['shapes']=[rect('metal1',0,0,4000,4000)]
            p['pdk']['layers']=[{'name':'metal1','gds':49,'datatype':1,'color':'#68a6f4','width':0,'space':0}]
            c['layout_ports']=[{'name':'A','point':[1000,1000],'layer':'metal1','class':'input','use':'signal'}]
            c['layout_texts']=[{'text':'A','x':1000,'y':1000,'layer':'metal1'}];c['layout_label_mode']='explicit'
            child={'id':uid(),'name':'child','ports':[],'devices':[],'shapes':[rect('metal1',0,0,4000,4000)]};p['cells'].append(child)
            ident=uid();c['layout_instances']=[{'id':ident,'name':'U1','cell':child['id'],'x':8000,'y':0,'rotation':0}]
            record=magic_workspace(p,p['top'],root/'workspace',MAGIC,technology);self.assertTrue(record['interface']['equal'])
            native=root/'workspace/native/top.mag';text=native.read_text();self.assertIn('studio_'+ident,text)
            text,count=re.subn(r'(?m)^(transform 1 0 )([0-9-]+)( 0 1 [0-9-]+)$',lambda m:m[1]+str(int(m[2])+2)+m[3],text)
            self.assertEqual(count,1);native.write_text(text)
            exported=magic_workspace_export(root/'workspace',root/'review',MAGIC);merged=review(p,exported['layout'])
            self.assertFalse(merged['errors']);self.assertFalse(merged['conflicts'])
            actual=merged['candidate']['cells'][0]['layout_instances'][0]
            self.assertEqual(actual['id'],ident);self.assertGreater(actual['x'],8000)
            self.assertEqual(actual['name'],'U1');self.assertEqual(merged['candidate']['cells'][0]['ports'],['A'])


if __name__=='__main__':unittest.main()
