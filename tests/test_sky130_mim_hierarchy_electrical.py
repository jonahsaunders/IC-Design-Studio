"""Bounded candidate controls; no simulator or physical engine execution."""
import importlib.util
import json
import math
from pathlib import Path
import re
import tempfile
import unittest
from unittest.mock import patch

HERE = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('candidate_mim_hierarchy_electrical', HERE/'scripts/qualify_sky130_mim_hierarchy_electrical.py')
q = importlib.util.module_from_spec(spec); spec.loader.exec_module(q)
NATIVE = '.subckt mim_pair P1 N1 P2 N2\nX0 P1 N1 sky130_fd_pr__cap_mim_m3_1 l=10 w=2\nX1 P2 N2 sky130_fd_pr__cap_mim_m3_1 l=10 w=2\n.ends\n'


class HierarchyElectricalTests(unittest.TestCase):
    def coefficients(self, section='tt'):
        return q.load(q.ROOT/'docs/qualification/sky130-mim-contract-v1.json')['passive_sections'][section]['coefficients']

    def synthetic(self, plate, section, profile):
        coeff = self.coefficients(section)
        names = ['frequency']
        for tag in q.PATHS:
            for port in q.PORTS: names += [f'v({tag}_{port})',f'i(v_{tag}_{port})']
        names += ['v(par_'+name+')' for name in q.PARAMETERS]
        rows=[]
        for index in range(8):
            frequency=10**(index+3);row=[complex(frequency,float('nan'))]
            for tag in q.PATHS:
                currents=q.expected_currents(tag,q.PROFILES[profile],frequency,plate,coeff)
                for voltage,current in zip(q.PROFILES[profile],currents):row += [complex(voltage),-current]
            row += [complex({**coeff,'mc_mm_switch':0,'mc_pr_switch':0}[name]) for name in q.PARAMETERS]
            rows.append(row)
        return names,rows,True

    def observe(self, rows, profile='e1', plate=1, section='tt'):
        case=dict(name=f'p{plate}-r0-{section}',plate=plate,rotation=0,section=section)
        title=q.title('/declared/original','a'*32,case['name'],profile)
        with tempfile.TemporaryDirectory() as temp:
            path=Path(temp)/'result.raw';path.write_text('Title: '+title+'\n')
            with patch.object(q,'parse_raw',return_value=rows):return q.observe(path,case,profile,self.coefficients(section),title)

    def test_exact_selection_scope_and_independent_profiles(self):
        self.assertEqual(len(q.selected()),20);self.assertEqual(len(q.selected(True)),2)
        self.assertEqual([(x[0]-x[1],x[2]-x[3]) for x in q.PROFILES.values()],[(1,0),(0,1)])
        report={'mode':'source-integration',**dict.fromkeys(('qualified','installed','release_ready','signoff','chunk_complete','full_family'),False)}
        q.scope_check(report)
        for key in ('installed','full_family','signoff'):
            with self.assertRaises(ValueError):q.scope_check({**report,key:True})

    def test_exact_native_graph_and_only_declared_negative_edits(self):
        q.native_graph(NATIVE,1)
        for fault in ('cross','missing','width'):
            text=q.mutated_native(NATIVE,1,fault);q.native_graph(text,1,fault)
            with self.assertRaises(ValueError):q.native_graph(text,1)
        for altered in (NATIVE.replace('X1 P2 N2','X1 N2 P2'),NATIVE.replace('X1','X0'),
                        NATIVE.replace('l=10','l=11',1),NATIVE.replace('m3_1','m3_2',1),
                        NATIVE.replace(' w=2',' w=2 m=2',1),NATIVE.replace(' P2 N2\n',' P1 N1\n')):
            with self.assertRaises(ValueError):q.native_graph(altered,1)

    def test_decks_include_actual_whole_network_once_with_all_terminal_probes(self):
        case=q.selected()[0];networks={k:Path('/original/'+k+'.spice') for k in q.PATHS}
        for profile in q.PROFILES:
            deck=q.deck(case,profile,networks,'.lib /locked/models tt','/original/output','b'*32)
            self.assertEqual(deck.count('Xwhole P1 N1 P2 N2 mim_pair'),6)
            for tag in q.PATHS:
                self.assertEqual(deck.count(f'.include "/original/{tag}.spice"'),1)
                for port in q.PORTS:
                    self.assertIn(f'v({tag}_{port})',deck);self.assertIn(f'i(v_{tag}_{port})',deck)
            self.assertEqual(deck.splitlines()[0],q.title('/original/output','b'*32,case['name'],profile))
        self.assertNotEqual(q.title('/a','b'*32,case['name'],'e1'),q.title('/a','b'*32,case['name'],'e2'))

    def test_conditioned_offsets_are_exact_and_old_profile_remains_excluded(self):
        contract=q.read_contract();self.assertEqual(contract['conditioning']['delta_V'],2**-16)
        self.assertIn('failed and unqualified',contract['predecessor']['status'])
        self.assertEqual(contract['predecessor']['profiles']['e1'],[1.25,.25,-.5,-.5])
        for profile,values in q.PROFILES.items():
            text=q.deck(q.selected()[0],profile,{k:Path('/source/'+k) for k in q.PATHS},'.lib /source/model tt','/output','a'*32)
            for tag in q.PATHS:
                actual=[float(re.search(rf'(?m)^V_{tag}_{p} {tag}_{p} 0 DC 0 AC (.+)$',text)[1]) for p in q.PORTS]
                self.assertEqual(actual,list(values))
                self.assertEqual(actual[1]-actual[3],2**-15)
            # Six significant digits would silently change the intended offset.
            active=values[0] if profile=='e1' else values[2]
            self.assertNotEqual(float(format(active,'g')),active)

    def test_all_selected_analytical_profiles_and_controls(self):
        for plate in (1,2):
            for section in q.SECTIONS:
                results={p:self.observe(self.synthetic(plate,section,p),p,plate,section) for p in q.PROFILES}
                for fault in ('cross','missing','width'):
                    self.assertTrue(any(r['detections'][fault] for r in results.values()))
                self.assertFalse(results['e1']['detections']['missing'])
                self.assertFalse(results['e1']['detections']['width'])

    def test_nonnumeric_current_cross_coupling_and_wrong_applied_voltage_reject(self):
        for channel,value in [('i(v_native_p1)',complex(float('nan'))),('i(v_native_p2)',1e-9),
                              ('v(native_n2)',.5),('v(par_mc_mm_switch)',1)]:
            names,rows,c=self.synthetic(1,'tt','e1');rows[0][names.index(channel)]=value
            with self.assertRaises(ValueError):self.observe((names,rows,c))

    def test_missing_or_falsely_clean_fault_response_rejects(self):
        names,rows,c=self.synthetic(1,'tt','e2')
        for row in rows:
            for port in q.PORTS:row[names.index('i(v_width_'+port+')')]=row[names.index('i(v_native_'+port+')')]
        with self.assertRaises(ValueError):self.observe((names,rows,c),'e2')
        names,rows,c=self.synthetic(1,'tt','e1')
        with self.assertRaises(ValueError):self.observe((names[:-1],[row[:-1] for row in rows],c))

    def test_context_title_rejects_other_orientation_and_duplicate(self):
        case=q.selected()[0];expected=q.title('/original','c'*32,case['name'],'e1')
        with tempfile.TemporaryDirectory() as temp:
            path=Path(temp)/'result.raw'
            for content in ('Title: '+q.title('/original','c'*32,'p1-r90-tt','e1')+'\n',
                            'Title: '+expected+'\nTitle: '+expected+'\n'):
                path.write_text(content)
                with self.assertRaises(ValueError):q.observe(path,case,'e1',self.coefficients(),expected)

    def test_explicit_binding_counterpart_exports_two_real_child_occurrences(self):
        # Synthetic old-revision/ABI fixture. Actual archive lineage is checked
        # separately by the acceptance reader; the portable unit lane has no
        # dependency on private machine paths or retained native archives.
        tech,_=q.load_technology('sky130A')
        with tempfile.TemporaryDirectory() as temp:
            for plate in (1,2):
                oldtech=q.clone(tech);oldtech['package_lock']['revision']='9a491f0ebd51a0aa'
                key=f'sky130_fd_pr/cap_mim_m3_{plate}.sym'
                oldtech['simulation']['catalog'][key]['emit_parameters']=q.read_contract()['counterpart']['old_emit_parameters'][str(plate)]
                original=q.create_device(oldtech,key,'C1');original['nets']=dict(c0='P',c1='N');original['model_params'].update(w=2,l=10,mf=1)
                old=dict(top='leaf',pdk=oldtech,cells=[dict(id='leaf',devices=[original])])
                data=(json.dumps(old,sort_keys=True)+'\n').encode()
                leaf=Path(temp)/f'leaf{plate}.icproj';leaf.write_bytes(data);folder=Path(temp)/f'app{plate}'
                result=q.application(leaf,tech,folder)
                parent=q.load(folder/'schematic.icproj');top=next(c for c in parent['cells'] if c['id']==parent['top'])
                self.assertEqual([d['kind'] for d in top['devices']],['X','X'])
                self.assertEqual(len({d['cell'] for d in top['devices']}),1)
                exported=(folder/'application.spice').read_text()
                self.assertEqual(exported.count(f'sky130_fd_pr__cap_mim_m3_{plate}'),2)
                self.assertIn('P1 N1',exported);self.assertIn('P2 N2',exported)
                self.assertNotIn('vm=',exported);self.assertEqual(exported.count('mf=1'),2)
                self.assertEqual(result['old_model_ref']['revision'],'9a491f0ebd51a0aa')
                self.assertEqual(result['new_model_ref']['revision'],'47dbd4fe43bfa7e4')
                self.assertEqual(leaf.read_bytes(),data)


if __name__=='__main__':unittest.main()
