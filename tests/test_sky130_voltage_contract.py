import copy
import unittest

from scripts import sky130_voltage_contract as v


class VoltageContractTests(unittest.TestCase):
    def fixture(self):
        inst=dict(name='U1',master='hd_logic',pins=[dict(name=p,net=net,direction='INOUT') for p,(net,_) in v.PG.items()]
                  +[dict(name='A',net='in',direction='INPUT'),dict(name='Y',net='out',direction='OUTPUT')])
        inventory=dict(schema=1,top='control',checkpoint_sha256='a'*64,instances=[dict(name='U1',master='hd_logic')],
            nets=[dict(net=name,alias=alias,sig_type=kind,pins=[dict(terminal=name,direction=direction)])
                  for name,alias,kind,direction in (('VDD','P','POWER','INOUT'),('VSS','G','GROUND','INOUT'),
                    ('in','I','SIGNAL','INPUT'),('out','O','SIGNAL','OUTPUT'))])
        ports,_=v.top_ports(inventory)
        contract=dict(schema=1,mode='nominal-single-domain-hd',top='control',checkpoint_sha256='a'*64,
            supplies={'VDD':'1.8','VSS':'0'},power_net_hv=[],ports={name:dict(**p,range_v=['1.8','1.8'] if name=='VDD' else ['0','0'] if name=='VSS' else ['0','1.8']) for name,p in ports.items()})
        cells={'hd_logic':dict(power={name:dict(voltage=value,kind='supply') for name,(_,value) in v.PG.items()},
            pins={'A':dict(direction='INPUT',power='VPWR',ground='VGND'),'Y':dict(direction='OUTPUT',power='VPWR',ground='VGND')})}
        devices=[]
        for model,body in ((v.NFET,'G'),(v.PFET,'P')):
            device=['device','msubckt',model]+['0']*16
            for i,node in ((9,body),(10,'I'),(13,'P'),(16,'O')):device[i]=node
            devices.append(tuple(device))
        return [contract,inventory,dict(version=1,dbu_per_micron=1000,instances=[inst]),cells,
                dict(ground='G',nodes={n:() for n in ('P','G','I','O')},devices=devices)]

    def test_complete_declared_domain(self):
        result=v.validate(*self.fixture())
        self.assertEqual(result['supply_and_bias_pins'],4)
        self.assertEqual(result['mos_bodies'],{'G':1,'P':1})
        self.assertFalse(result['qualified'])

    def test_missing_high_and_invalid_port_voltages(self):
        for change in ('missing','high','negative','reverse','nan','number'):
            with self.subTest(change=change):
                data=self.fixture();contract=data[0]
                if change=='missing':del contract['ports']['in']
                else:contract['ports']['in']['range_v']={'high':['0','3.3'],'negative':['-0.1','1.8'],
                    'reverse':['1.8','0'],'nan':['0','NaN'],'number':[0,1.8]}[change]
                with self.assertRaises(ValueError):v.validate(*data)

    def test_missing_or_high_voltage_net_declaration(self):
        for value in (None,['in'],['VDD']):
            data=self.fixture();data[0]['power_net_hv']=value
            with self.assertRaises(ValueError):v.validate(*data)
        data=self.fixture();del data[0]['power_net_hv']
        with self.assertRaises(ValueError):v.validate(*data)

    def test_supply_voltage_and_bias_wiring(self):
        for pin in v.PG:
            data=self.fixture();p=next(p for p in data[2]['instances'][0]['pins'] if p['name']==pin)
            p['net']='VSS' if p['net']=='VDD' else 'VDD'
            with self.assertRaises(ValueError):v.validate(*data)
        data=self.fixture();data[3]['hd_logic']['power']['VPWR']['voltage']='3.3'
        with self.assertRaises(ValueError):v.validate(*data)

    def test_native_body_unknown_model_and_terminal(self):
        for fault in ('body','model','terminal','kind'):
            data=self.fixture();row=list(data[4]['devices'][0])
            row[{'body':9,'model':2,'terminal':10,'kind':1}[fault]]={'body':'P','model':'unknown','terminal':'unaccounted','kind':'resistor'}[fault]
            data[4]['devices'][0]=row
            with self.assertRaises(ValueError):v.validate(*data)

    def test_native_substrate_and_alias_coverage(self):
        data=self.fixture();data[4]['ground']='P'
        with self.assertRaises(ValueError):v.validate(*data)
        data=self.fixture();del data[4]['nodes']['O']
        with self.assertRaises(ValueError):v.validate(*data)

    def test_unknown_master_missing_pin_duplicate_instance(self):
        for fault in ('unknown','missing','duplicate'):
            data=self.fixture()
            if fault=='unknown':del data[3]['hd_logic']
            elif fault=='missing':data[2]['instances'][0]['pins'].pop()
            else:data[2]['instances'].append(copy.deepcopy(data[2]['instances'][0]))
            with self.assertRaises(ValueError):v.validate(*data)

    def test_port_alias_direction_and_checkpoint_are_bound(self):
        for field,value in (('net','different'),('direction','OUTPUT'),('sig_type','CLOCK')):
            data=self.fixture();data[0]['ports']['in'][field]=value
            with self.assertRaises(ValueError):v.validate(*data)
        data=self.fixture();data[0]['checkpoint_sha256']='b'*64
        with self.assertRaises(ValueError):v.validate(*data)

    def test_unconnected_outputs_count_but_inputs_fail(self):
        data=self.fixture();data[2]['instances'][0]['pins'][-1]['net']=None
        self.assertEqual(v.validate(*data)['unconnected_outputs'],1)
        data=self.fixture();data[2]['instances'][0]['pins'][-2]['net']=None
        with self.assertRaises(ValueError):v.validate(*data)

    def test_unknown_signal_domain_and_duplicate_native_alias(self):
        data=self.fixture();data[3]['hd_logic']['pins']['A']['power']='another_supply'
        with self.assertRaises(ValueError):v.validate(*data)
        data=self.fixture();data[1]['nets'][-1]['alias']='I'
        with self.assertRaises(ValueError):v.validate(*data)

    def test_duplicate_liberty_attribute_and_invalid_values(self):
        self.assertEqual(v.attribute('    voltage_name : "VPWR";\n','voltage_name'),'VPWR')
        with self.assertRaises(ValueError):v.attribute('    voltage_name : "VPWR";\n    voltage_name : "OTHER";','voltage_name')
        for value in (None,True,float('nan'),'NaN','Infinity','invalid'):
            with self.assertRaises(ValueError):v.decimal(value)

    def test_pinned_liberty_structure_and_nested_test_pins(self):
        text='''library ("control") {
    nom_voltage : 1.8000000000;
    voltage_unit : "1V";
    voltage_map("VPWR", 1.8);
    cell ("inv") {
        pg_pin ("VPWR") {
            voltage_name : "VPWR";
            pg_type : "primary_power";
        }
        pin ("Y") {
            direction : "output";
            related_power_pin : "VPWR";
            related_ground_pin : "VGND";
        }
        test_cell () {
            pin ("Y") {
                direction : "output";
            }
        }
    }
}
'''
        parsed=v.liberty(text)
        self.assertEqual(set(parsed['inv']['pins']),{'Y'})
        self.assertEqual(parsed['inv']['power']['VPWR']['voltage'],'1.8')
        for before,after in (('1.8000000000','3.3000000000'),('"1V"','"1mV"'),
                             ('voltage_name : "VPWR"','voltage_name : "unknown"'),
                             ('    voltage_map("VPWR", 1.8);','')):
            with self.assertRaises(ValueError):v.liberty(text.replace(before,after))

    def test_changed_physical_master_source_is_rejected(self):
        with self.assertRaises(ValueError):v.empty_physical_cells('.SUBCKT sky130_fd_sc_hd__fill_1 VGND VNB VPB VPWR\n.ENDS\n')


if __name__=='__main__':unittest.main()
