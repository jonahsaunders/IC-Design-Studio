"""Reference connectivity and transactional layout; actual PVT lives in qualification."""
import json
import unittest
from pathlib import Path

from icstudio.model import clone, digest
from icstudio.two_stage_opamp import reference, generate_layout


def technology():
    root=Path(__file__).resolve().parents[1]/'icstudio/assets/pdks/sky130A'
    package=json.loads((root/'package.json').read_text())
    tech=package['technology']
    tech.update(package_root=str(root),package_lock={k:package[k] for k in ('id','revision','files')})
    return tech


class TwoStageReference(unittest.TestCase):
    def test_layout_connects_every_device_and_port_and_keeps_requirements(self):
        from icstudio.physical import connectivity
        from icstudio.analog_constraints import findings
        p,cid,_=reference(technology())
        definitions=digest(p['testbenches'])
        ids=[d['id'] for c in p['cells'] for d in c['devices']]
        generate_layout(p,cid)
        self.assertEqual(digest(p['testbenches']),definitions)
        self.assertEqual([d['id'] for c in p['cells'] for d in c['devices']],ids)
        self.assertFalse(connectivity(p,cid)['issues'])
        self.assertFalse(findings(p,cid))
        cell=next(c for c in p['cells'] if c['id']==cid)
        self.assertEqual(len(cell['layout_pins']),8*4+2*2)
        self.assertEqual({v['name'] for v in cell['layout_ports']},set(cell['ports']))
        before=clone(p)
        with self.assertRaisesRegex(ValueError,'replacement'):
            generate_layout(p,cid)
        self.assertEqual(p,before)

    def test_invalid_device_aborts_generated_geometry_atomically(self):
        p,cid,_=reference(technology())
        cell=next(c for c in p['cells'] if c['id']==cid)
        # The last compensation cell is checked after the transistors; partial
        # placement must not leak when its process dimensions are rejected.
        cell['devices'][-1]['model_params']['mf']='2'
        before=clone(p)
        with self.assertRaises(ValueError):generate_layout(p,cid)
        self.assertEqual(p,before)


if __name__=='__main__':unittest.main()
