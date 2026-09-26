import tempfile
from pathlib import Path
import unittest
from unittest.mock import patch
import klayout.db as db
from scripts.qualify_virtuoso_exchange import prepare,checked_bundle,check_return


class VirtuosoHandoffTests(unittest.TestCase):
    def test_geometry_and_independent_strict_lvs_are_both_required(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td);ly=db.Layout();ly.dbu=.001;c=ly.create_cell('top');layer=ly.layer(34,0)
            c.shapes(layer).insert(db.Box(0,0,1000,1000));ly.write(str(root/'source.gds'))
            (root/'source.cdl').write_text('.subckt top A B\nR1 A B 1000\n.ends top\n')
            (root/'setup.tcl').write_text('permute default\nproperty default\n')
            bundle=root/'bundle';result=prepare(root/'source.gds',root/'source.cdl','top',bundle)
            self.assertEqual(result['status'],'prepared-unverified')
            with patch('scripts.qualify_virtuoso_exchange.netgen_lvs',return_value='Circuits match uniquely.\nCell pin lists are equivalent.'):
                result=check_return(bundle,root/'source.gds',root/'source.cdl','netgen',root/'setup.tcl',root/'check')
                self.assertEqual(result['status'],'passed')
                c.shapes(layer).insert(db.Text('extra_pin',db.Trans(0,0)));ly.write(str(root/'changed.gds'))
                with self.assertRaisesRegex(ValueError,'text changed'):
                    check_return(bundle,root/'changed.gds',root/'source.cdl','netgen',root/'setup.tcl',root/'changed-check')
            with patch('scripts.qualify_virtuoso_exchange.netgen_lvs',return_value='Circuits match uniquely.\nCell pin lists are equivalent.\nProperty errors'):
                with self.assertRaises(ValueError):check_return(bundle,root/'source.gds',root/'source.cdl','netgen',root/'setup.tcl',root/'bad-lvs')
            (bundle/'reference.cdl').write_text('tampered')
            with self.assertRaisesRegex(ValueError,'changed'):checked_bundle(bundle)


if __name__=='__main__':unittest.main()
