import array,json,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
from icstudio.model import clone,save_project,load_project
from icstudio.xschem_project import property_text,apply_review
from icstudio.xschem_compat import review_project,export_capture
from icstudio.xschem_runtime import netlist,prepare_program,read_plot


def fixture(root,program=None):
    root=Path(root);root.mkdir(parents=True,exist_ok=True)
    program=program or '.control\nforeach T 1 2\nreset\nalter v1 dc=$T\nsave all\nop\ntran 10u 1m\nac dec 5 10 10k\necho level $T\ndestroy all\nend\n.endc'
    rows=['v {xschem version=3.4.4 file_version=1.2}','G {}','K {}','V {}','S {}','E {}']
    for symbol,x,y,rotation,props in [('vsource',0,0,0,{'name':'V1','value':'DC 1 AC 1'}),('res',100,-30,1,{'name':'R1','value':'1k','m':'1'}),('capa',160,0,0,{'name':'C1','value':'1u','m':'1'}),('gnd',0,30,0,{'name':'g1','lab':'GND'}),('lab_wire',160,-30,0,{'name':'p1','lab':'out'}),('code_shown',300,50,0,{'name':'sim','value':program})]:
        rows.append(f'C {{{symbol}.sym}} {x} {y} {rotation} 0 '+'{'+property_text(props)+'}')
    rows+=['N 0 -30 70 -30 {}','N 130 -30 160 -30 {}','N 0 30 160 30 {}'];path=root/'capture.sch';path.write_text('\n'.join(rows)+'\n');return path


class CompatibleXschemTests(unittest.TestCase):
    def setUp(self):self.tmp=tempfile.TemporaryDirectory();self.root=Path(self.tmp.name);self.path=fixture(self.root/'source')
    def tearDown(self):self.tmp.cleanup()
    def project(self):
        r=review_project(self.path);self.assertEqual(r['errors'],[]);self.assertEqual(r['mode'],'compatible');return apply_review(r)
    def test_offline_standard_symbols_and_opaque_control(self):
        with patch('urllib.request.urlopen',side_effect=AssertionError('Import must be offline')):p=self.project()
        c=p['cells'][0];self.assertEqual(len(c['devices']),4);self.assertFalse(p['xschem_exchange']['unresolved']);self.assertIn('foreach T',next(d for d in c['devices'] if d['name']=='sim')['xschem']['properties']['value'])
        d=next(d for d in c['devices'] if d['name']=='C1');self.assertEqual(set(d['nets'].values()),{'out','0'})
    def test_saved_capture_survives_deleted_originals(self):
        p=self.project();save_project(p,self.root/'p.icproj');self.path.unlink();q=load_project(self.root/'p.icproj');report=export_capture(q,self.root/'portable');review=review_project(self.root/'portable'/report['top']);self.assertFalse(review['errors']);self.assertFalse(review['candidate']['xschem_exchange']['unresolved'])
    def test_roundtrip_identity_properties_specs_and_edits(self):
        p=self.project();c=p['cells'][0];d=next(d for d in c['devices'] if d['name']=='R1');d['xschem']['properties']['value']='2k';c['specifications']=[{'name':'Target','expression':'final(V("out"))','min':'0','max':'2.1','unit':'V'}]
        report=export_capture(p,self.root/'export');q=apply_review(review_project(self.root/'export'/report['top']));self.assertEqual(p['id'],q['id']);self.assertEqual(p['top'],q['top']);self.assertEqual(c['specifications'],q['cells'][0]['specifications']);actual=next(a for a in q['cells'][0]['devices'] if a['id']==d['id']);self.assertEqual(actual['xschem']['properties']['value'],'2k')
        text=netlist(q,self.root/'run');self.assertIn('2k',text);self.assertNotIn('tcleval',text)
    def test_missing_custom_symbol_is_visible_and_blocks_only_simulation(self):
        self.path.write_text(self.path.read_text().replace('{res.sym}','{private_resistor.sym}'));r=review_project(self.path);self.assertTrue(r['candidate']);p=apply_review(r);d=next(d for d in p['cells'][0]['devices'] if d['name']=='R1');self.assertEqual(d['nets'],{});self.assertTrue(d['xschem']['missing'])
        with self.assertRaisesRegex(ValueError,'needs these files'):netlist(p,self.root/'run')
    def test_stale_files_and_tampered_metadata_are_rejected(self):
        r=review_project(self.path);self.path.write_text(self.path.read_text()+'\n')
        with self.assertRaisesRegex(ValueError,'changed after review'):apply_review(r)
        p=self.project();report=export_capture(p,self.root/'export');native=self.root/'export/studio-project.icproj';native.write_text(native.read_text()+'\n');r=review_project(self.root/'export'/report['top']);self.assertIsNone(r['candidate']);self.assertIn('metadata',' '.join(r['errors']))
    def test_gf180_dynamic_installation_path_and_alias(self):
        props={'name':'sim','value':'.include "$::env(PDK_ROOT)/gf180mcuD/libs.tech/ngspice/design.ngspice"\n.lib "$::env(PDK_ROOT)/gf180mcuD/libs.tech/ngspice/sm141064.ngspice" typical\n.control\nop\n.endc'}
        self.path.write_text('v {xschem version=3.4.4 file_version=1.2}\nG {}\nK {}\nV {}\nS {}\nE {}\nC {gf180mcu_fd_pr/nfet_05v0.sym} 0 0 0 0 {name=M1 L=1u W=2u}\nC {code_shown.sym} 0 100 0 0 {'+property_text(props)+'}\n')
        p=self.project();self.assertFalse(p['xschem_exchange']['unresolved']);text=netlist(p,self.root/'run');self.assertIn('nfet_05v0 L=1u W=2u',text);self.assertNotIn('$::env',text);self.assertIn('gf180mcu',p['xschem_exchange']['library_lock']['libraries'])
    def test_program_case_tracking_paths_and_shell_handling(self):
        p=self.project();text=netlist(p,self.root/'run');program,count,relocations=prepare_program(text,self.root/'run',{'probes':'v(out) i(v1)'});self.assertEqual(count,6);self.assertIn('echo level $t',program);self.assertIn('case{$&const.studio_case}.raw',program);self.assertEqual(program.count('ICSTUDIO_CASE_BEGIN'),3)
        for statement in ('shell rm -rf /tmp/anything','echo hello > ../file','source unreviewed.cir'):
            bad='title\n.control\n'+statement+'\nop\n.endc\n.end'
            with self.assertRaises(ValueError):prepare_program(bad,self.root/'run',{'probes':'v(out)'})
        good='title\n.control\nshell mkdir -p /foss/designs/output\necho yes > /foss/designs/output/result.txt\nop\nshell ls -lah /foss/designs/output\n.endc\n.end';program,_,paths=prepare_program(good,self.root/'run',{'probes':'v(out)'});self.assertNotIn('/foss/',program);self.assertEqual(len(paths),1)
    def test_binary_waveforms_keep_all_sample_values(self):
        header=b'Title: test\nPlotname: Transient Analysis\nFlags: real\nNo. Variables: 2\nNo. Points: 3\nVariables:\n0 time time\n1 v(out) voltage\nBinary:\n';values=array.array('d',[0,1,.5,2,1,4]);path=self.root/'wave.raw';path.write_bytes(header+values.tobytes());r=read_plot(path);self.assertEqual(r['x'],[0,.5,1]);self.assertEqual(r['traces']['out'],[1,2,4])
        from icstudio.measurements import evaluate
        marker={'kind':'XY','x':.75,'y':3.1,'trace':'out','rule':'<=','id':'m'};self.assertEqual(evaluate({'settings':{'type':'xschem'},**r},marker)['verdict'],'PASS')
    def test_saved_waveforms_reopen_after_moving_run_folder(self):
        import shutil
        from icstudio.model import design_digest
        from icstudio.job_store import read_result
        p=self.project();run=self.root/'old run';run.mkdir();(run/'waveforms').mkdir()
        (run/'waveforms/case1.raw').write_text('Title: moved\nPlotname: Transient Analysis\nFlags: real\nNo. Variables: 2\nNo. Points: 2\nVariables:\n0 time time\n1 v(out) voltage\nValues:\n0 0\n1\n1 1\n2\n')
        result={'project_id':p['id'],'cell_id':p['top'],'design_hash':design_digest(p),'x':[0,1],'traces':{'out':[1,2]},'xschem_cases':[{'number':1,'file':'waveforms/case1.raw'}],'case_directory':str(run)}
        (run/'input.json').write_text(json.dumps({'project':p,'cell':p['top']}));(run/'result.json').write_text(json.dumps(result));(run/'status.json').write_text('{"status":"complete"}')
        moved=self.root/'different computer';shutil.move(run,moved);restored=read_result(moved/'result.json',p['id']);plot=read_plot(Path(restored['case_directory'])/restored['xschem_cases'][0]['file']);self.assertEqual(plot['traces']['out'],[1,2])


if __name__=='__main__':unittest.main()
