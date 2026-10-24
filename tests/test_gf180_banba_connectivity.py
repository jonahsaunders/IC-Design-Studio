"""Real stream controls for analog ground, body contacts and MIM connectivity."""
from pathlib import Path
import tempfile,unittest
import klayout.db as k
from scripts.check_gf180_banba_connectivity import inspect

EXAMPLE=Path(__file__).resolve().parents[1]/'examples/gf180-banba/layout'


class WrittenAnalogConnectivityTests(unittest.TestCase):
    def test_original_and_filled_streams_cover_every_terminal_and_port(self):
        for source in (EXAMPLE/'banba-layout.gds',EXAMPLE/'density/banba-density.gds'):
            with self.subTest(source=source):
                result=inspect(source,EXAMPLE/'banba-layout.icproj')
                self.assertTrue(result['passed'],result['failures'])
                self.assertEqual((result['terminals'],result['ports'],result['body_contacts']),(293,3,64))

    def test_physical_opens_short_and_missing_contact_are_rejected(self):
        controls=[('ground-port',(42,0),(-15,-37,-14,-35),'open'),
            ('tap-via',(35,0),(87.41,1.86,87.69,2.14),'open'),
            ('tap-contact',(33,0),(87.43,1.88,87.67,2.12),'missing-body-contact'),
            ('power-short',(42,0),(-10,-36,-9,-24),'short')]
        with tempfile.TemporaryDirectory() as tmp:
            for name,pair,box,expected in controls:
                with self.subTest(name=name):
                    ly=k.Layout();ly.read(str(EXAMPLE/'banba-layout.gds'));top=ly.top_cell();top.flatten(True)
                    index=ly.find_layer(*pair);before=k.Region(top.begin_shapes_rec(index));brush=k.Region(k.Box(*[round(v/ly.dbu) for v in box]))
                    after=before+brush if expected=='short' else before-brush
                    self.assertFalse((before^after).is_empty());top.shapes(index).clear();top.shapes(index).insert(after)
                    path=Path(tmp)/(name+'.gds');ly.write(str(path));result=inspect(path,EXAMPLE/'banba-layout.icproj')
                    self.assertFalse(result['passed']);self.assertEqual(result['failure_counts'],{expected:1})


if __name__=='__main__':unittest.main()
