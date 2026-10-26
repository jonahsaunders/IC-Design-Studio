"""Portable tests for the independent ESD execution-identity reader."""
import copy,importlib.util,json,tempfile,unittest
from pathlib import Path
spec=importlib.util.spec_from_file_location('esd_reader_v2',Path(__file__).resolve().parents[1]/'scripts/audit_sky130_esd_nvt.py')
a=importlib.util.module_from_spec(spec);spec.loader.exec_module(a)
ID='a'*32

def raw_text(drive,title):
    names=['v(v-sweep)' if drive=='dc' else 'frequency']+[f'i(vq{i}{p})' for i in range(6) for p in 'dgsb']
    domain=[i*.03 for i in range(41)] if drive=='dc' else [1e3*10**(i/5) for i in range(31)]
    rows=['Title: '+title.lower(),'Command: ngspice-46, Build Mar 29 2026','Plotname: '+('DC transfer characteristic' if drive=='dc' else 'AC Analysis'),
          'Flags: '+('real' if drive=='dc' else 'complex'),'No. Variables: 25','No. Points: '+str(len(domain)),'Variables:']
    rows.extend(f'{i} {name} '+('frequency grid=3' if i==0 and drive!='dc' else 'current') for i,name in enumerate(names));rows.append('Values:')
    for index,x in enumerate(domain):
        rows.append(f'{index} {x:.17g}'+('' if drive=='dc' else ',nan'))
        rows.extend(['0' if drive=='dc' else '0,0']*24)
    return '\n'.join(rows)+'\n'


class IndependentESDIdentityTests(unittest.TestCase):
    def test_actual_application_and_literal_reference_ac_domains(self):
        for role,limits in [('application',['1000','1000000000']),('independent',['1k','1g'])]:
            tokens=['.ac','dec','5',*limits]
            a.analysis_directive(tokens,'d',role)
            for bad in (['.ac','lin','5',*limits],['.ac','dec','6',*limits],
                        ['.ac','dec','5',limits[0],'1e8'],tokens+['extra']):
                with self.assertRaisesRegex(ValueError,'AC analysis'):a.analysis_directive(bad,'d',role)

    def test_exact_engine_specific_raw_header_profiles(self):
        title='* icstudio-esd-nvt-v2 '+ID+' nominal-27-dc independent'
        with tempfile.TemporaryDirectory() as temp:
            path=Path(temp)/'raw'
            for drive in ('dc','g'):
                windows=raw_text(drive,title)
                linux=windows.replace('Command: ngspice-46, Build Mar 29 2026\n','')
                path.write_text(linux);a.raw(path,drive,'42',title)
                with self.assertRaisesRegex(ValueError,'Windows46'):a.raw(path,drive,'46',title)
                for text in (windows,linux.replace('Title:','Command: ngspice-42, Build Jan 1 2024\nTitle:'),
                             linux.replace('Title:','Command: \nTitle:')):
                    path.write_text(text)
                    with self.assertRaisesRegex(ValueError,'Linux42'):a.raw(path,drive,'42',title)
                path.write_text(windows.replace('Command:','Command: ngspice-46, Build duplicate\nCommand:'))
                with self.assertRaisesRegex(ValueError,'Windows46'):a.raw(path,drive,'46',title)
                path.write_text(linux)
                with self.assertRaisesRegex(ValueError,'Unreviewed'):a.raw(path,drive,'43',title)

    def test_raw_exact_title_plot_domain_and_unique_headers(self):
        title='* icstudio-esd-nvt-v2 '+ID+' nominal-27-dc independent'
        with tempfile.TemporaryDirectory() as temp:
            path=Path(temp)/'raw'
            for drive in ('dc','g'):
                text=raw_text(drive,title);path.write_text(text);a.raw(path,drive,'46',title)
                for modified in (text.replace(title,'unrelated-output'),text.replace('Plotname: ','Plotname: wrong-'),
                    text.replace('Title: '+title,'Title: '+title+'\nTitle: '+title),
                    text.replace('i(vq0s)','i(vq0d)'),text.replace('No. Points: ','No. Points: 0\nDiscarded: '),
                    text.replace('ngspice-46','ngspice-42')):
                    path.write_text(modified)
                    with self.assertRaises((ValueError,IndexError)):a.raw(path,drive,'46',title)

    def fixture(self,folder,role='application'):
        report=dict(execution_id=ID,execution_root='C:\\accepted\\output',engine='C:\\engine\\ngspice.exe',engine_sha256=next(iter(a.ENGINES)))
        case='nominal-27-dc';root=a.native_path(report['execution_root']);cwd=root/case/role
        deck='reference.cir' if role=='independent' else 'input.cir';raw='deck.raw' if role=='independent' else 'result.raw'
        label='icstudio-esd-nvt-v2 '+ID+' '+case+' '+role
        title='* '+label if role=='independent' else '* IC Design Studio / '+label+' / revision 0'
        (folder/deck).write_text(title+'\n.end\n');(folder/raw).write_text(raw_text('dc',title));(folder/'engine.log').write_text('retained engine stdout\n')
        record=dict(schema=1,status='PASS',execution_id=ID,case=case,role=role,engine_sha256=report['engine_sha256'],
            deck_filename=deck,raw_filename=raw,deck_sha256=a.sha(folder/deck),raw_sha256=a.sha(folder/raw),log_sha256=a.sha(folder/'engine.log'),
            command=[report['engine'],'-n','-D','filetype=ascii','-D','ngbehavior=hsa','-b','-r',str(cwd/raw),str(cwd/deck)],cwd=str(cwd),
            timeout_seconds=180,started_utc='2026-10-26T21:00:00+00:00',ended_utc='2026-10-26T21:00:01+00:00',elapsed_seconds=1.)
        return report,record,title

    def test_actual_command_deck_raw_log_and_original_cwd_binding(self):
        with tempfile.TemporaryDirectory() as temp:
            folder=Path(temp)
            for role in ('application','independent'):
                report,record,title=self.fixture(folder,role)
                (folder/'execution-receipt.json').write_text(json.dumps(record))
                self.assertEqual(a.execution(folder,report,'nominal-27-dc',role),title)
                bad=[]
                for key,value in [('case','nominal-85-dc'),('role','wrong-body'),('execution_id','b'*32),('status','RUNNING'),
                    ('cwd','C:\\other'),('engine_sha256','0'*64),('raw_filename','other.raw'),('timeout_seconds',360),
                    ('ended_utc','2026-10-26T20:59:59+00:00'),('raw_sha256','0'*64),('log_sha256','0'*64)]:
                    bad.append(dict(record,**{key:value}))
                changed=copy.deepcopy(record);changed['command'][-1]=changed['command'][-1].replace('accepted','different');bad.append(changed)
                for value in bad:
                    (folder/'execution-receipt.json').write_text(json.dumps(value))
                    with self.assertRaises(ValueError):a.execution(folder,report,'nominal-27-dc',role)

    def test_rehashed_deck_title_and_cross_role_raw_are_rejected(self):
        with tempfile.TemporaryDirectory() as temp:
            folder=Path(temp);report,record,title=self.fixture(folder)
            path=folder/'input.cir';path.write_text(path.read_text().replace('application','wrong-gate'));record['deck_sha256']=a.sha(path)
            (folder/'execution-receipt.json').write_text(json.dumps(record))
            with self.assertRaisesRegex(ValueError,'deck title'):a.execution(folder,report,'nominal-27-dc','application')
            path=folder/'result.raw';path.write_text(raw_text('dc',title.replace('application','wrong-gate')))
            with self.assertRaisesRegex(ValueError,'title'):a.raw(path,'dc','46',title)

    def test_complete_inventory_includes_nested_manifest_names(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);(root/'evidence-manifest.json').write_text('{}');(root/'nested').mkdir()
            (root/'nested/evidence-manifest.json').write_text('retained unrelated artifact')
            self.assertEqual(set(a.inventory(root)),{'nested/evidence-manifest.json'})


if __name__=='__main__':unittest.main()
