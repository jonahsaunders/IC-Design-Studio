"""Candidate whole-network observability controls; no native execution."""
import copy
import importlib.util
import json
import math
from pathlib import Path
import tempfile
import unittest

HERE=Path(__file__).resolve()
SPEC=importlib.util.spec_from_file_location('candidate_mim_network_audit',HERE.parents[1]/'scripts/audit_sky130_mim_hierarchy_electrical.py')
audit=importlib.util.module_from_spec(SPEC);SPEC.loader.exec_module(audit)
REPO=audit.ROOT


def actual_native(plate):
    return f'.subckt mim_pair P1 N1 P2 N2\nX0 P1 N1 sky130_fd_pr__cap_mim_m3_{plate} w=2 l=10\nX1 P2 N2 sky130_fd_pr__cap_mim_m3_{plate} w=2 l=10 m=1\n.ends\n'


def sample(plate,section,frequency,profile):
    contract=json.loads((REPO/'docs/qualification/sky130-mim-contract-v1.json').read_bytes())
    coefficients=audit.source_coefficients(contract,section)
    def admittance(width):
        metal=str(plate+2);delta=(coefficients['m'+metal+'_dw']+coefficients['tol_m'+metal])*1e6
        w,l=width+delta,10+delta
        resistance=coefficients['rm'+metal]*l/w+coefficients['rcvia'+metal]*(.56 if plate==1 else .73)**2/(w*l)
        capacitance=coefficients['camimc']*w*l+coefficients['cpmimc']*2*(w+l)
        return 1/(resistance-1j/(2*math.pi*frequency*capacitance))
    voltage=audit.PROFILES[profile];y1,y2=admittance(2),admittance(3)
    result={'frequency':complex(frequency)}
    result.update({f'v(par_{k})':complex(v) for k,v in coefficients.items()})
    for path in audit.PATHS:
        first=(voltage[0]-voltage[1])*y1
        second=(voltage[2]-voltage[3])*(y2 if path=='width' else y1)
        values=(-first,first,-second,second)
        if path=='missing':values=(-first,first,0j,0j)
        if path=='cross':
            second=(voltage[0]-voltage[3])*y1;values=(-first-second,first,0j,second)
        for terminal,v,i in zip(('p1','n1','p2','n2'),voltage,values):
            result[f'v({path}_{terminal})']=complex(v);result[f'i(v_{path}_{terminal})']=i
    return result,coefficients


class WholeNetworkMiMAuditTests(unittest.TestCase):
    def test_exact_single_occurrence_mutation_preserves_unrelated_native_bytes(self):
        for plate in (1,2):
            raw=actual_native(plate).encode()
            expected={'cross':raw.replace(b'X1 P2 N2',b'X1 P1 N2'),
                      'missing':b''.join(line for line in raw.splitlines(keepends=True) if not line.startswith(b'X1 ')),
                      'width':raw.replace(b'X1 P2 N2 sky130_fd_pr__cap_mim_m3_'+str(plate).encode()+b' w=2',
                                          b'X1 P2 N2 sky130_fd_pr__cap_mim_m3_'+str(plate).encode()+b' w=3')}
            for kind,value in expected.items():self.assertEqual(audit.fault_bytes(raw,plate,kind),value)
            with self.assertRaises(ValueError):audit.fault_bytes(raw+raw,plate,'cross')

    def test_exact_whole_network_deck_and_common_mode_profiles(self):
        for plate in (1,2):
            for rotation in (0,90):
                for section in audit.SECTIONS:
                    case=dict(name=f'p{plate}-r{rotation}-{section}',plate=plate,rotation=rotation,section=section)
                    for profile,volts in audit.PROFILES.items():
                        origin='C:/qualified/output';nonce='a'*32;networks={t:'C:/actual/'+t+'.spice' for t in audit.PATHS}
                        lines=[audit.title(origin,nonce,case['name'],profile),'.lib C:/locked/pdk tt',
                            '.param mc_mm_switch=0 mc_pr_switch=0','.option tnom=27','.temp 27'];saves=[]
                        for tag in audit.PATHS:
                            lines.extend([f'.subckt whole_{tag} P1 N1 P2 N2',f'.include "{networks[tag]}"',
                                          'Xwhole P1 N1 P2 N2 mim_pair',f'.ends whole_{tag}'])
                            for port,voltage in zip(('p1','n1','p2','n2'),volts):
                                lines.append(f'V_{tag}_{port} {tag}_{port} 0 DC 0 AC {voltage:.17g}')
                                saves.extend([f'v({tag}_{port})',f'i(v_{tag}_{port})'])
                            lines.append('X_'+tag+' '+' '.join(tag+'_'+p for p in ('p1','n1','p2','n2'))+' whole_'+tag)
                        for key in audit.PARAMETERS:
                            lines.append(f'VPAR_{key} par_{key} 0 DC {{{key}}} AC {{{key}}}');saves.append(f'v(par_{key})')
                        deck='\n'.join(lines+['.ac dec 1 1k 10G','.save '+' '.join(saves),'.end',''])
                        audit.check_deck(deck,case,profile,networks,'.lib C:/locked/pdk tt',origin,nonce)
                        for bad in (deck.replace('X_native native_p1 native_n1 native_p2 native_n2','X_native native_p1 native_n1 native_p1 native_n2'),
                                    deck.replace('native.spice','app.spice'),deck.replace('.temp 27','.temp 28'),
                                    deck.replace('V_native_n2 native_n2 0 DC 0 AC '+format(volts[3],'.17g'),'V_native_n2 native_n2 0 DC 0 AC 0'),
                                    deck.replace('AC '+format(volts[0],'.17g'),'AC '+format(volts[0],'g'),1)):
                            with self.assertRaises(ValueError):audit.check_deck(bad,case,profile,networks,'.lib C:/locked/pdk tt',origin,nonce)

    def test_actual_text_raw_parser_title_saved_current_sign_and_fault_detection(self):
        case=dict(name='p2-r90-hh',plate=2,rotation=90,section='hh');profile='e2'
        expected_title=audit.title('/actual/output','e'*32,case['name'],profile)
        rows=[sample(2,'hh',10**(i+3),profile)[0] for i in range(8)];coeff=sample(2,'hh',1e3,profile)[1]
        names=list(rows[0]);lines=['Title: '+expected_title,'Plotname: AC Analysis','Flags: complex',
                                 'No. Variables: '+str(len(names)),'No. Points: 8','Variables:']
        lines += [f'{i} {name} '+('frequency grid=3' if i==0 else 'voltage') for i,name in enumerate(names)]
        lines.append('Values:')
        for i,row in enumerate(rows):
            for j,name in enumerate(names):
                z=row[name];lines.append((str(i)+' ' if j==0 else '')+f'{z.real:.17g},{z.imag:.17g}')
        observations=[]
        for row in rows:
            paths={}
            for tag in audit.PATHS:
                v=[row[f'v({tag}_{p})'] for p in ('p1','n1','p2','n2')]
                currents=[-row[f'i(v_{tag}_{p})'] for p in ('p1','n1','p2','n2')]
                paths[tag]=dict(voltages=[[z.real,z.imag] for z in v],currents=[[z.real,z.imag] for z in currents])
            observations.append(dict(frequency_hz=row['frequency'].real,paths=paths))
        saved=dict(samples=8,max_normalized_current_error=0.0,detections=dict.fromkeys(('cross','missing','width'),True),observations=observations)
        with tempfile.TemporaryDirectory() as temp:
            path=Path(temp)/'raw';text='\n'.join(lines)+'\n';path.write_text(text)
            result=audit.check_raw(path,case,profile,coeff,expected_title,saved)
            self.assertEqual(result['active_pair_samples'],24);self.assertEqual(result['inactive_pair_samples'],24)
            bad=copy.deepcopy(saved);bad['observations'][0]['paths']['native']['currents'][2][1]*=-1
            with self.assertRaises(ValueError):audit.check_raw(path,case,profile,coeff,expected_title,bad)
            for raw in (text.replace('Title: '+expected_title,'Title: different'),
                        text.replace('Plotname: AC Analysis','Plotname: Operating Point'),
                        text.replace('i(v_native_n2)','i(v_native_p2)')):
                path.write_text(raw)
                with self.assertRaises(ValueError):audit.check_raw(path,case,profile,coeff,expected_title,saved)

    def test_complete_reference_and_native_graph_keep_ordered_independent_terminals(self):
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'network.spice'
            for plate in (1,2):
                raw=actual_native(plate);path.write_text(raw);audit.network(path,plate,native=True)
                for changed in (raw.replace('X1 P2 N2','X1 N2 P2'),raw.replace('X1 P2 N2','X1 P1 N2'),raw.replace('w=2','w=3'),
                                raw.replace('X1','X0'),raw.replace('m=1','m=2'),raw+'.include substitute\n'):
                    path.write_text(changed)
                    with self.assertRaises(ValueError):audit.network(path,plate,native=True)
                path.write_text(audit.physical.reference_text(plate));audit.network(path,plate,native=False)
                for changed in (audit.physical.reference_text(plate,'merged-reference-terminal'),audit.physical.reference_text(plate,'missing-reference-instance')):
                    path.write_text(changed)
                    with self.assertRaises(ValueError):audit.network(path,plate,native=False)

    def test_all_predeclared_profiles_sections_frequencies_per_device_and_fault_vectors(self):
        for plate in (1,2):
            for section in audit.SECTIONS:
                for profile in audit.PROFILES:
                    for frequency in (1e3,1e4,1e5,1e6,1e7,1e8,1e9,1e10):
                        with self.subTest(plate=plate,section=section,profile=profile,f=frequency):
                            row,coeff=sample(plate,section,frequency,profile)
                            result=audit.sample_observations(row,plate,coeff,frequency,profile)
                            self.assertEqual(set(result),set(audit.PATHS))
                            active='1' if profile=='e1' else '2'
                            for path in ('app','reference','native'):
                                self.assertLess(result[path]['devices'][active]['relative_error'],1e-6)
                            if profile=='e2':
                                for path in ('cross','missing','width'):
                                    self.assertGreater(result[path]['positive_current_normalized_difference'],1e-6)

    def test_inactive_current_and_cross_response_cannot_hide_behind_equal_stimuli(self):
        row,coeff=sample(1,'tt',1e8,'e1')
        # The inactive occurrence must not inherit the active occurrence's current.
        bad=copy.deepcopy(row);bad['i(v_native_p2)']=bad['i(v_native_p1)'];bad['i(v_native_n2)']=bad['i(v_native_n1)']
        with self.assertRaisesRegex(ValueError,'current vector'):audit.sample_observations(bad,1,coeff,1e8,'e1')
        bad=copy.deepcopy(row)
        for node in ('p1','n1','p2','n2'):bad[f'i(v_native_{node})']=bad[f'i(v_cross_{node})']
        with self.assertRaisesRegex(ValueError,'current vector'):audit.sample_observations(bad,1,coeff,1e8,'e1')
        bad=copy.deepcopy(row);bad['v(native_p2)']=.5+0j
        with self.assertRaisesRegex(ValueError,'stimulus'):audit.sample_observations(bad,1,coeff,1e8,'e1')

    def test_both_source_currents_coefficients_and_finite_channels_are_required(self):
        row,coeff=sample(2,'hl',1e7,'e2')
        changes=[]
        bad=copy.deepcopy(row);bad['i(v_native_n2)']=0j;changes.append(bad)
        bad=copy.deepcopy(row);bad['i(v_native_p2)']*=1.1;changes.append(bad)
        bad=copy.deepcopy(row);bad['v(par_mc_mm_switch)']=1+0j;changes.append(bad)
        bad=copy.deepcopy(row);bad['v(par_camimc)']*=2;changes.append(bad)
        bad=copy.deepcopy(row);bad.pop('i(v_app_n1)');changes.append(bad)
        bad=copy.deepcopy(row);bad['i(v_native_p2)']=complex(float('nan'),1);changes.append(bad)
        for value in changes:
            with self.assertRaises(ValueError):audit.sample_observations(value,2,coeff,1e7,'e2')

    def test_fault_outputs_must_follow_the_actual_declared_mutation(self):
        row,coeff=sample(1,'ll',1e9,'e2')
        for path in ('cross','missing','width'):
            bad=copy.deepcopy(row)
            for node in ('p1','n1','p2','n2'):bad[f'i(v_{path}_{node})']=bad[f'i(v_native_{node})']
            with self.subTest(path=path),self.assertRaisesRegex(ValueError,'current vector'):
                audit.sample_observations(bad,1,coeff,1e9,'e2')

    def test_rehashed_finite_saved_observables_do_not_replace_native_values(self):
        row,coeff=sample(2,'hh',1e10,'e2');expected=audit.sample_observations(row,2,coeff,1e10,'e2')
        audit.numeric(expected,expected)
        bad=copy.deepcopy(expected);bad['native']['currents_A'][2][1]*=1.01
        with self.assertRaisesRegex(ValueError,'numerical observable'):audit.numeric(bad,expected)


if __name__=='__main__':unittest.main()
