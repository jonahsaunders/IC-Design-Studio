"""Bus names must survive the upstream reader's unsafe character stripping."""
import unittest
from scripts.ihp_lvs_reference import encode_reference


class IHPReferenceTests(unittest.TestCase):
    def fixture(self):
        raw='.SUBCKT top a[0] a0 out VDD VSS\nXcell[0] out a[0] a0 VDD VSS gate\n.ENDS top\n'
        masters='.SUBCKT gate Y A B VDD VSS\nM1 Y A VSS VSS sg13_lv_nmos W=1u L=130n\n.ENDS\n'
        db=dict(top='top',ports=[dict(name=p,net=p) for p in ('a[0]','a0','out','VDD','VSS')],
                database=dict(instances=[dict(name='cell[0]',master='gate',pins=[dict(name=p,net=n) for p,n in
                    zip(('Y','A','B','VDD','VSS'),('out','a[0]','a0','VDD','VSS'))])]))
        return raw,masters,db

    def test_collision_prone_bus_names_stay_distinct_and_connected(self):
        raw,masters,db=self.fixture();text,mapping=encode_reference(raw,masters,db)
        self.assertNotEqual(mapping['nets']['a[0]'],mapping['nets']['a0'])
        lines=text.splitlines();header=lines[1].split();element=lines[2].split()
        self.assertEqual(header[2:4],element[2:4])
        self.assertIn(masters,text)
        self.assertEqual(mapping['checked_terminals'],5)

    def test_wrong_pin_binding_cannot_be_encoded(self):
        raw,masters,db=self.fixture()
        with self.assertRaisesRegex(ValueError,'terminal differs'):
            encode_reference(raw.replace('out a[0] a0','out a0 a[0]'),masters,db)

    def test_missing_filler_instance_cannot_be_hidden(self):
        raw,masters,db=self.fixture()
        with self.assertRaisesRegex(ValueError,'omitted implementation'):
            encode_reference('\n'.join([raw.splitlines()[0],raw.splitlines()[-1]]),masters,db)

    def test_changed_port_is_rejected(self):
        raw,masters,db=self.fixture()
        with self.assertRaisesRegex(ValueError,'ports differ'):
            encode_reference(raw.replace('.SUBCKT top a[0]','.SUBCKT top a9'),masters,db)

    def test_boundary_net_alias_is_bound_to_the_real_port(self):
        raw,masters,db=self.fixture()
        next(p for p in db['ports'] if p['name']=='out')['net']='internal_output'
        db['database']['instances'][0]['pins'][0]['net']='internal_output'
        _,mapping=encode_reference(raw,masters,db)
        self.assertEqual(mapping['boundary_net_names']['internal_output'],'out')

    def test_isolated_unused_terminal_is_captured(self):
        raw,masters,db=self.fixture()
        db['database']['instances'][0]['pins'][2]['net']=''
        raw=raw.replace('out a[0] a0','out a[0] _unconnected_0')
        _,mapping=encode_reference(raw,masters,db)
        self.assertEqual(mapping['disconnected_terminals'],{'_unconnected_0':{'instance':'cell[0]','pin':'B'}})
        with self.assertRaisesRegex(ValueError,'disconnected terminal'):
            encode_reference(raw.replace('_unconnected_0','out'),masters,db)
