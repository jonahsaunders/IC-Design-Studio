"""CLI generation/regen and failure atomicity for physical process devices."""
import contextlib
import io
import tempfile
import unittest
from pathlib import Path

from icstudio.cli import main
from icstudio.model import load_project,save_project
from icstudio.physical import connectivity
from tests.test_sky130_parallel import project


class ProcessDeviceCLITests(unittest.TestCase):
    def invoke(self,args):
        out,err=io.StringIO(),io.StringIO()
        with contextlib.redirect_stdout(out),contextlib.redirect_stderr(err):status=main(args)
        return status,out.getvalue(),err.getvalue()

    def test_named_generation_and_regeneration_preserve_terminals(self):
        p,c,d=project(count=3);c['shapes']=[];c['layout_pins']=[];c['pdk_layouts']=[];d['nets']['b']=d['nets']['s']
        with tempfile.TemporaryDirectory() as tmp:
            source=Path(tmp)/'source.icproj';generated=Path(tmp)/'generated.icproj';updated=Path(tmp)/'updated.icproj';save_project(p,source)
            args=['pdk-device-layout',str(source),'--cell',c['name'],'--device',d['name'],'--output',str(generated),'--x','5000','--y','10000','--body-tie','source']
            status,_,error=self.invoke(args);self.assertEqual(status,0,error)
            q=load_project(generated);cell=q['cells'][0];self.assertFalse(connectivity(q,cell['id'])['issues'])
            self.assertEqual(cell['pdk_layouts'][0]['origin'],[5000,10000]);pins=cell['layout_pins']
            cell['devices'][0]['model_params']['mult']=4;save_project(q,generated)
            status,_,error=self.invoke(['pdk-device-layout',str(generated),'--cell',cell['id'],'--device',d['id'],'--output',str(updated),'--regenerate'])
            self.assertEqual(status,0,error);q=load_project(updated);cell=q['cells'][0]
            self.assertEqual(cell['layout_pins'],pins);self.assertEqual(cell['pdk_layouts'][0]['parallel_units']['count'],4)
            self.assertEqual(cell['devices'][0]['physical_body_tie'],'source');self.assertFalse(connectivity(q,cell['id'])['issues'])

    def test_invalid_parameters_never_replace_output(self):
        p,c,d=project(count=2)
        with tempfile.TemporaryDirectory() as tmp:
            source=Path(tmp)/'source.icproj';output=Path(tmp)/'keep.icproj';save_project(p,source);output.write_text('preserve this file')
            base=['pdk-device-layout',str(source),'--cell',c['name'],'--device',d['name'],'--output',str(output)]
            for extra in ([],['--body-tie','source','--regenerate'],['--regenerate','--x','1000']):
                status,_,_=self.invoke(base+extra);self.assertEqual(status,1);self.assertEqual(output.read_text(),'preserve this file')
            self.assertEqual(load_project(source)['cells'],p['cells'])


if __name__=='__main__':unittest.main()
