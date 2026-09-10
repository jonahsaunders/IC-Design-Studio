"""One workflow for every catalog, independent of process names."""
import json
import tempfile
import unittest
from pathlib import Path
from icstudio.model import example,clone,file_digest,validate
from icstudio.project_templates import create,TEMPLATES
from icstudio.pdks import PDKRegistry
from icstudio.interchange import spice


def install_fixture(root,identifier):
    root.mkdir(parents=True,exist_ok=True)
    (root/'models.spice').write_text('.subckt nfet d g s b w=1 l=1\nR1 d s 1k\n.ends\n.subckt pfet d g s b w=1 l=1\nR1 d s 1k\n.ends\n')
    technology=example()['pdk'];technology['name']=identifier
    catalog={}
    for kind,model in (('NMOS','nfet'),('PMOS','pfet')):
        catalog[model]={'kind':kind,'label':model,'model':model,'prefix':'X','pin_order':['d','g','s','b'],
            'parameters':{'w':{'default':'1','positive':True},'l':{'default':'.5','positive':True}},
            'parameter_scale':{'w':1e6,'l':1e6},'emit_parameters':{'w':'w','l':'l'}}
    technology['simulation']={'includes':[{'path':'models.spice'}],'catalog':catalog,'devices':{}}
    manifest={'schema':1,'id':identifier,'revision':'fixture','technology':technology,'files':{'models.spice':file_digest(root/'models.spice')}}
    path=root/'package.json';path.write_text(json.dumps(manifest));return path


class PDKTemplateTests(unittest.TestCase):
    def test_same_templates_accept_four_process_ids_and_a_future_pdk(self):
        # These are small contract fixtures, not process qualification models.
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);registry=PDKRegistry(root/'registry')
            for identifier in ('sky130A','gf180mcuC','gf180mcuD','ihp-sg13g2','future-process'):
                technology=registry.technology(registry.install(install_fixture(root/identifier,identifier)))
                for template in TEMPLATES:
                    with self.subTest(pdk=identifier,template=template):
                        p,cid,key=create(technology,template,1.2,'nfet','pfet');validate(p)
                        self.assertEqual(p['pdk']['package_lock']['id'],identifier)
                        text=spice(p);self.assertIn('nfet',text);self.assertIn('w=1 l=0.5',text)
                        if template in ('inverter','ring'):self.assertIn('pfet',text)
                        bench=next(c for c in p['cells'] if c['id']==p['top']);sources=[d for d in bench['devices'] if d['kind'] in ('V','I','R','C')]
                        self.assertEqual(len({(d['x'],d['y']) for d in sources}),len(sources))

    def test_missing_model_is_explained_instead_of_substituting_another_process(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);registry=PDKRegistry(root/'registry');tech=registry.technology(registry.install(install_fixture(root/'pdk','future-process')))
            tech['simulation']['catalog'].pop('pfet')
            with self.assertRaisesRegex(ValueError,'PMOS'):create(tech,'inverter')
            p,_,_=create(tech,'current_mirror');self.assertEqual(p['pdk']['package_lock']['id'],'future-process')


if __name__=='__main__':unittest.main()
