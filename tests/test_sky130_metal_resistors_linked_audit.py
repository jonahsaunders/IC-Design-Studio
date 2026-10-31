"""Independent mathematical/parser tests, not native qualification evidence."""
import math
import copy
import json
from pathlib import Path
import tempfile
import unittest

from scripts import audit_sky130_metal_resistors_linked as audit


class MetalAuditTests(unittest.TestCase):
    def test_primitive_geometry_temperature_and_multiplicity(self):
        p=dict(rsh=10,dw=0,tol=0,tc1=.01,tc2=.001,tnom=20)
        self.assertEqual(audit.model_resistance(2,4,1,20,p),20)
        self.assertAlmostEqual(audit.model_resistance(2,4,2,30,p),12)
        p['dw']=2
        self.assertEqual(audit.model_resistance(2,4,1,20,p),10)
        self.assertNotAlmostEqual(audit.model_resistance(2,4,1,20,p),40/3)
        # Explicit deck scale changes geometry correction; units are never guessed.
        self.assertAlmostEqual(audit.model_resistance(2,4,1,20,p,scale=2),40/3)

    def test_invalid_resistance_context_rejected(self):
        p=dict(rsh=10,dw=0,tol=0,tc1=0,tc2=0,tnom=20)
        for values in ((0,4,1,20),(2,4,0,20),(2,4,1,-273.15),(math.nan,4,1,20)):
            with self.subTest(values=values),self.assertRaises(ValueError):audit.model_resistance(*values,p)

    def test_loaded_network_complex_transfer_and_thermal_noise(self):
        self.assertEqual(audit.transfer(4,4,1,0),.5)
        self.assertAlmostEqual(audit.transfer(4,4,1,1/(4*math.pi)),.25-.25j)
        k=1.380649e-23
        flat=audit.noise_density(4,4,1,0,26.85,k)
        self.assertAlmostEqual(flat/math.sqrt(8*k*300),1)
        pole=audit.noise_density(4,4,1,1/(4*math.pi),26.85,k)
        self.assertAlmostEqual(pole/flat,1/math.sqrt(2))

    def test_transient_exact_ramp_and_settling(self):
        pulse=dict(low=0,high=1,delay=0,rise=1,width=10,fall=1,period=20)
        at_one=.25+.25*math.exp(-2)
        expected=[0,.25*math.exp(-1),at_one,.5+(at_one-.5)*math.exp(-2)]
        measured=audit.transient_response([0,.5,1,2],1,1,1,pulse)
        for actual,wanted in zip(measured,expected):self.assertAlmostEqual(actual,wanted,places=14)

    def test_transient_breakpoints_do_not_depend_on_output_sampling(self):
        pulse=dict(low=.1,high=1,delay=.25,rise=.1,width=.2,fall=.1,period=1)
        sparse=audit.transient_response([0,.8,1.8],1,2,.3,pulse)
        dense=audit.transient_response([0,.2,.25,.3,.35,.55,.65,.8,1.2,1.8],1,2,.3,pulse)
        self.assertAlmostEqual(sparse[1],dense[7],places=14)
        self.assertAlmostEqual(sparse[-1],dense[-1],places=14)

    def test_comparison_rejects_incomplete_and_nonfinite(self):
        for actual,expected in (([],[]),([1],[1,2]),([math.nan],[1]),([1],[math.inf])):
            with self.subTest(actual=actual),self.assertRaises(ValueError):
                audit.normalized_error(actual,expected,relative_tolerance=1e-6,absolute_tolerance=1e-12)
        self.assertGreater(audit.normalized_error([1.1],[1],relative_tolerance=1e-6,absolute_tolerance=1e-12),1)

    def read(self,text,**kwargs):
        with tempfile.TemporaryDirectory() as temporary:
            path=Path(temporary)/'sample.raw';path.write_text(text,encoding='ascii')
            return audit.read_raw(path,'* identity','AC Analysis',complex_values=True,**kwargs)

    def raw(self):
        return ('Title: * identity\nPlotname: AC Analysis\nFlags: complex\nNo. Variables: 2\nNo. Points: 2\n'
                'Variables:\n0 frequency frequency grid=3\n1 v(out) voltage\nValues:\n0 1,nan\n0.5,-0.5\n1 10,nan\n0.1,-0.2\n')

    def test_ascii_raw_retains_phase_and_unused_frequency_slot(self):
        result=self.read(self.raw())
        self.assertEqual(result['values']['v(out)'],[.5-.5j,.1-.2j])
        self.assertEqual(result['points'],2)

    def test_ascii_raw_rejects_substitution_missing_duplicate_and_nonfinite(self):
        raw=self.raw()
        corrupt=[raw.replace('* identity','* other'),raw.replace('AC Analysis','Transient Analysis'),
                 raw.replace('Flags: complex','Flags: real'),raw.replace('No. Points: 2','No. Points: 3'),
                 raw.replace('1 v(out) voltage','1 frequency frequency'),raw.replace('0.5,-0.5','nan,0'),
                 raw.replace('0.5,-0.5','0.5,nan'),raw+'0,0\n',raw.replace('1 10,nan','2 10,nan'),
                 raw.replace('Title: * identity','Title: * identity\nTitle: * identity')]
        for text in corrupt:
            with self.subTest(text=text[:80]),self.assertRaises(ValueError):self.read(text)

    def test_native_model_dimensions_and_terminal_identity(self):
        good='* real extraction\n.subckt coupon R1 R2\nR0 R1 R2 sky130_fd_pr__res_generic_m3 w=2 l=5\n.ends\n'
        with tempfile.TemporaryDirectory() as temporary:
            path=Path(temporary)/'extracted.spice';path.write_text(good)
            self.assertEqual(audit.native_resistor(path,'m3',2,5)['width_um'],2)
            # M3/M4 can be electrically identical; exact model identity still matters.
            for text in (good.replace('generic_m3','generic_m4'),good.replace('w=2','w=3'),
                         good.replace('l=5','l=6'),good.replace('R0 R1','R0 disconnected'),
                         good.replace('l=5','l=5 m=3'),good+'.option scale=1e-6\n'):
                path.write_text(text)
                with self.subTest(text=text),self.assertRaises(ValueError):audit.native_resistor(path,'m3',2,5)

    def test_mask_geometry_rejects_wrong_layer_terminal_and_marker(self):
        import klayout.db as db
        with tempfile.TemporaryDirectory() as temporary:
            path=Path(temporary)/'coupon.gds'
            def write(layer=68,marker_right=1000,terminal_x=0):
                layout=db.Layout();layout.dbu=.001;cell=layout.create_cell('coupon')
                cell.shapes(layout.layer(layer,20)).insert(db.Box(-1000,-2700,1000,2700))
                cell.shapes(layout.layer(layer,13)).insert(db.Box(-1000,-2500,marker_right,2500))
                labels=cell.shapes(layout.layer(layer,5));labels.insert(db.Text('R1',db.Trans(terminal_x,-2600)));labels.insert(db.Text('R2',db.Trans(0,2600)))
                layout.write(str(path))
            write();audit.physical_geometry(path,'m1',2,5,0)
            for kwargs in (dict(layer=69),dict(marker_right=900),dict(terminal_x=2000)):
                write(**kwargs)
                with self.subTest(kwargs=kwargs),self.assertRaises(ValueError):audit.physical_geometry(path,'m1',2,5,0)
            write()
            with self.assertRaises(ValueError):audit.physical_geometry(path,'m1',2,5,90)

    def fixture(self,root,control='positive',analysis='dc'):
        spec=audit.load(audit.ROOT/audit.CONTRACT);logical,cases=audit.selection(spec,True)
        case=next(c for c in cases if c['control']==control and c['analysis']==analysis)
        folder=root/case['name'];folder.mkdir(exist_ok=True)
        rows=audit.branches(logical,case);execution=dict(root='/var/tmp/metal-audit-fixture',nonce='a'*32)
        selected='ll' if control=='wrong-section' else 'tt';temp=44 if control=='wrong-temperature' else 27
        x=[-.001+i*.0001 for i in range(21)] if analysis=='dc' else [1000*10**(i/3) for i in range(22)]
        data={('v(v-sweep)' if analysis=='dc' else 'frequency'):x,'v(input)':x if analysis=='dc' else [1+0j]*len(x)}
        for row in rows:
            tag=row['branch'];r=audit.resistance(spec,row,'tt' if row['kind']=='analytic' else selected,27 if row['kind']=='analytic' else temp)
            output=[0]*len(x) if row['fault']=='disconnected-terminal' else [v/(1+r) for v in x] if analysis=='dc' else [audit.transfer(r,1,1e-9,f) for f in x]
            data['v(in_'+tag+')']=data['v(input)'];data['v(out_'+tag+')']=output
            data['i(vs_'+tag+')']=[0]*len(x) if row['fault']=='disconnected-terminal' else [(a-b)/r for a,b in zip(data['v(input)'],output)]
        for name,value in spec['sections'][selected]['coefficients'].items():data['v(par_'+name+')']=[value]*len(x)
        self.emit_raw(folder/'result.raw',execution,case,data,analysis)
        return spec,case,rows,execution,data

    def emit_raw(self,path,execution,case,data,analysis):
        names=list(data);count=len(data[names[0]]);complex_values=analysis=='ac'
        lines=['Title: '+audit.context_title(execution,case['name']),
               'Plotname: '+{'dc':'DC transfer characteristic','ac':'AC Analysis','noise':'Noise Spectral Density Curves'}[analysis],
               'Flags: '+('complex' if complex_values else 'real'),f'No. Variables: {len(names)}',f'No. Points: {count}','Variables:']
        lines += [f'{i} {n} '+('frequency' if n=='frequency' else 'current' if n.startswith('i(') else 'voltage') for i,n in enumerate(names)]
        lines += ['Values:']
        for point in range(count):
            for index,name in enumerate(names):
                value=data[name][point];number=f'{complex(value).real:.17g},{complex(value).imag:.17g}' if complex_values else f'{value:.17g}'
                lines.append((str(point)+' ' if index==0 else '')+number)
        path.write_text('\n'.join(lines)+'\n',encoding='ascii')

    def test_real_context_controls_require_changed_physics_and_preserved_numeric_reference(self):
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary)
            for control in ('positive','wrong-section','wrong-temperature'):
                spec,case,rows,execution,data=self.fixture(root,control)
                observation,count=audit.check_observation(root,spec,case,rows,execution)
                self.assertEqual(count,10 if control=='positive' else 8)
                # The retained wrong-context labels cannot stand in for changed outputs.
                clean=copy.deepcopy(data);tag='a_m1_g1_r0_m1';r=audit.resistance(spec,rows[0],'tt',27)
                if control=='positive':r*=1.2
                clean['v(out_'+tag+')']=[v/(1+r) for v in clean['v(input)']]
                clean['i(vs_'+tag+')']=[v/(1+r) for v in clean['v(input)']]
                self.emit_raw(root/case['name']/'result.raw',execution,case,clean,'dc')
                with self.assertRaises(ValueError):audit.check_observation(root,spec,case,rows,execution)

    def test_actual_dc_ac_current_coefficients_and_branch_substitution_reject(self):
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary)
            for analysis in ('dc','ac'):
                spec,case,rows,execution,data=self.fixture(root,analysis=analysis)
                audit.check_observation(root,spec,case,rows,execution)
                mutations=[]
                value=copy.deepcopy(data);value['i(vs_a_m1_g1_r0_m1)'][0]*=-1;mutations.append(value)
                value=copy.deepcopy(data);value['v(par_mc_mm_switch)']=[1]*len(value['v(input)']);mutations.append(value)
                value=copy.deepcopy(data);value['v(out_a_m1_g1_r0_m1)']=value['v(out_a_m1_g1_r0_m3)'];mutations.append(value)
                value=copy.deepcopy(data);value.pop('v(out_n_m1_g1_r0_m1)');mutations.append(value)
                for value in mutations:
                    self.emit_raw(root/case['name']/'result.raw',execution,case,value,analysis)
                    with self.assertRaises(ValueError):audit.check_observation(root,spec,case,rows,execution)

    def test_noise_branch_identity_and_thermal_shape_reject(self):
        spec=audit.load(audit.ROOT/audit.CONTRACT);logical,cases=audit.selection(spec,True)
        case=next(c for c in cases if c['analysis']=='noise');rows=audit.branches(logical,case)
        execution=dict(root='/var/tmp/noise-fixture',nonce='c'*32);x=[1000*10**(i/3) for i in range(22)]
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary);folder=root/case['name'];folder.mkdir()
            for row in rows:
                r=audit.resistance(spec,row,'tt',27);tag=row['branch']
                data={'frequency':x,'noise_'+tag:[audit.noise_density(r,1,1e-9,f,27,1.38064852e-23) for f in x]}
                self.emit_raw(folder/f'noise_{tag}.raw',execution,case,data,'noise')
            audit.check_observation(root,spec,case,rows,execution)
            path=folder/'noise_a_m1_g1_r0_m1.raw';original=path.read_text()
            for text in (original.replace('noise_a_m1_g1_r0_m1','noise_a_m1_g1_r0_m3'),original.replace('No. Points: 22','No. Points: 21')):
                path.write_text(text)
                with self.assertRaises(ValueError):audit.check_observation(root,spec,case,rows,execution)
            data={'frequency':x,'noise_a_m1_g1_r0_m1':[1e-12]*len(x)}
            self.emit_raw(path,execution,case,data,'noise')
            with self.assertRaises(ValueError):audit.check_observation(root,spec,case,rows,execution)

    def test_saved_summary_corruption_and_extra_directives_reject(self):
        value=dict(branches=dict(a=dict(maximum_normalized_error=.02,resistance_ohm=.3,samples=21)),parameters=dict(rm1=.125),samples=21)
        audit.compare_summary(copy.deepcopy(value),value)
        for key in ('resistance_ohm','samples','maximum_normalized_error'):
            changed=copy.deepcopy(value);changed['branches']['a'][key]+=1
            with self.assertRaises(ValueError):audit.compare_summary(changed,value)
        for text in ('R1 A B model w=3 l=5','R1 A C model w=2 l=5','R1 A B other w=2 l=5','R1 A B model w=2 l=5\n.option scale=2'):
            with self.assertRaises(ValueError):audit.same_lines(text,['R1 A B model w=2 l=5'])
        audit.same_lines('R1 A B model w=2.0 l=5e0',['R1 A B model w=2 l=5'])

    def test_deck_native_substitution_switch_override_and_noise_branch_reject(self):
        from scripts import qualify_sky130_metal_resistors_linked as producer
        spec=audit.load(audit.ROOT/audit.CONTRACT);logical,cases=audit.selection(spec,True)
        package=audit.load(audit.ROOT/spec['package']['path']/'package.json');tech=copy.deepcopy(package['technology'])
        tech.update(package_root=str(audit.ROOT/spec['package']['path']),package_lock={k:package[k] for k in ('id','revision','files')})
        execution=dict(root='/var/tmp/deck-fixture',nonce='b'*32);selected={s:'.lib pdk-models/locked.spice '+s for s in audit.SECTIONS}
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary);(root/'contract.json').write_text(json.dumps(spec))
            sources={};bindings={}
            for rotation in (0,90):
                key='m1-w2-l5-r'+str(rotation);path=root/(key+'.spice')
                path.write_text('.subckt coupon R1 R2\nR0 R2 R1 sky130_fd_pr__res_generic_m1 w=2 l=5\n.ends\n')
                sources[key]=path;bindings[key]=dict(path=path.as_posix(),sha256=audit.sha(path))
            for analysis in ('dc','ac','tran','noise'):
                case=next(c for c in cases if c['analysis']==analysis and c['control']=='positive');rows=audit.branches(logical,case)
                folder=root/case['name'];folder.mkdir();project=producer.fixture(tech,rows,analysis)
                app=producer.spice(project,project['top'],hierarchical=False);(folder/'application.spice').write_text(app)
                text,_,_=producer.deck(spec,case,rows,app,selected,sources,execution)
                if analysis=='noise':
                    import re
                    text=re.sub(r'(?m)^write (noise_\S+\.raw)',lambda m:'write '+execution['root']+'/'+case['name']+'/'+m[1],text)
                path=folder/'input.cir';path.write_text(text);audit.check_deck(root,case,rows,selected,bindings,execution)
                controls=[text.replace('sky130_fd_pr__res_generic_m1','sky130_fd_pr__res_generic_m2',1),
                          text.replace('.temp 27','.temp 28'),text.replace('.end\n','.param mc_mm_switch=1\n.end\n'),
                          text.replace('.include '+sources['m1-w2-l5-r0'].as_posix(),'.include /unbound/substitute.spice')]
                if analysis=='noise':controls += [text.replace('noise v(out_a_m1_g1_r0_m1)','noise v(out_a_m1_g1_r0_m3)')]
                if analysis=='tran':controls += [text.replace(' chgtol=1e-24 trtol=1','')]
                for changed in controls:
                    path.write_text(changed)
                    with self.assertRaises(ValueError):audit.check_deck(root,case,rows,selected,bindings,execution)


if __name__=='__main__':unittest.main()
