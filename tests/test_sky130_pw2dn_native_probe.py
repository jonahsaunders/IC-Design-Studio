"""Focused guardrails for the finite, unqualified pw2dn native producer."""
import json,os,subprocess,tempfile,unittest
from pathlib import Path
from unittest import mock
from icstudio import pw2dn_native_probe as probe
from scripts import audit_installed_sky130_pw2dn_native as auditor
from scripts import installed_mim_inputs

def deck(fault=None):
    lines=[]
    for i,(_,_,area,perim) in enumerate(probe.POINTS):
        pins=['0','d'+str(i)] if fault=='polarity' else ['d'+str(i),'0']
        a=area*.5 if fault=='area' else area;p=perim*1.5 if fault=='perimeter' else perim
        lines.append(f'X_D{i} {pins[0]} {pins[1]} {probe.MODEL} area={a:g} perim={p:g}')
    return '\n'.join(lines)+'\n'

class NativeProbeTests(unittest.TestCase):
    def test_exact_calls_and_faults_are_distinct(self):
        probe.calls(deck())
        for fault in probe.FAULTS:
            probe.calls(deck(fault),fault)
            with self.assertRaises(ValueError):probe.calls(deck(fault))
        with self.assertRaises(ValueError):probe.calls(deck().replace('X_D2','X_D1'))
        with self.assertRaises(ValueError):probe.calls(deck().replace('area=4','area=4 extra=1'))

    def test_finite_contract_is_explicit(self):
        self.assertEqual(probe.POINTS,((2,2,4,8),(4,2,8,12),(10,10,100,40)))
        self.assertEqual(len(probe.CONDITIONS),9)
        self.assertEqual(probe.FAULTS,('polarity','area','perimeter'))

class ReferenceEnvironmentTests(unittest.TestCase):
    """Real Git source checks around simulated isolated native production."""
    def fixture(self):
        from icstudio import engines,acceptance_runtime
        temporary=tempfile.TemporaryDirectory();self.addCleanup(temporary.cleanup)
        root=Path(temporary.name);native=root/'native';native.mkdir()
        (native/'report.json').write_bytes(b'{}')
        gui=root/'gui';(gui/'new').mkdir(parents=True)
        (gui/'new/project.icproj').write_bytes(b'{"top":"fixture"}')
        engine=root/'engine/ngspice.exe';engine.parent.mkdir();engine.write_bytes(b'fixture, never executed')
        out=root/'references';source='scripts/fixture_reader.py'
        candidate=root/'source';path=candidate/source;path.parent.mkdir(parents=True)
        path.write_bytes(b'# Immutable independent reader fixture\n')
        git_env={key:value for key,value in os.environ.items() if not key.upper().startswith('GIT_')}
        git_env.update(GIT_CONFIG_NOSYSTEM='1',GIT_CONFIG_GLOBAL=os.devnull)
        def git(*args):
            return subprocess.check_output(['git',*args],cwd=candidate,env=git_env,stderr=subprocess.PIPE,text=True).strip()
        git('init','--quiet','--template=')
        git('add','--',source)
        git('-c','user.name=Reader fixture','-c','user.email=reader@example.invalid',
            '-c','core.hooksPath='+str(root/'empty-hooks'),'commit','--quiet','--no-gpg-sign','-m','Immutable fixture')
        commit=git('rev-parse','HEAD')
        env={'PATH':str(engine.parent),'LANG':'C','HOME':str(out/'environment/empty-home')}
        expected={'mode':'installed','source_root':str(candidate),'source_files':{source:auditor.sha(path)},
                  'reader_files':{str(path):auditor.sha(path)},'commit':commit,
                  'native_report_sha256':auditor.sha(native/'report.json'),'native_inventory':auditor.inventory(native),
                  'candidate_root':str(root/'candidate'),'engine_sha256':auditor.sha(engine),
                  'resource_root':str(root),'runtime':{'environment':env,'scope':'fixture'}}
        outer=dict(os.environ);execute=engines.execute;runs=[]
        def produce(*args):
            self.assertEqual(dict(os.environ),env)
            self.assertIsNot(engines.execute,execute)
            runs.append(args)
            return {'status':'simulated production; no electrical verdict'}
        patches=(mock.patch.object(installed_mim_inputs,'ROOT',candidate),
                 mock.patch.object(auditor,'candidate'),mock.patch.object(auditor,'python_identity',return_value={}),
                 mock.patch.object(auditor,'modules',return_value={}),
                 mock.patch.object(auditor,'literal_inputs',return_value=('* literal fixture\n.end\n',b'* models\n')),
                 mock.patch.object(acceptance_runtime,'native_environment',return_value=env),
                 mock.patch.object(acceptance_runtime,'runtime',side_effect=lambda binding,engine,environment:{'environment':environment,'scope':'fixture'}),
                 mock.patch.object(engines,'run_deck',side_effect=produce))
        for patch in patches:patch.start();self.addCleanup(patch.stop)
        return native,gui,engine,out,expected,outer,execute,runs

    def test_installed_reference_readback_restores_git_environment(self):
        from icstudio import engines
        native,gui,engine,out,expected,outer,execute,runs=self.fixture()
        def readback(*args):
            self.assertEqual(dict(os.environ),outer)
            self.assertIs(engines.execute,execute)
            # This is the actual second Git object check which failed on the
            # hosted Windows runner after its engine-only PATH was inherited.
            auditor.source_identity(args[3])
            return {'status':'TEST_ORCHESTRATION_ONLY'}
        with mock.patch.object(auditor,'readback',side_effect=readback),mock.patch.object(auditor,'source_identity',wraps=auditor.source_identity) as identity:
            result=auditor.verify(native,gui,engine,expected,out)
        self.assertEqual(result['status'],'TEST_ORCHESTRATION_ONLY')
        self.assertEqual(identity.call_count,2)
        self.assertEqual(len(runs),18)
        self.assertEqual(dict(os.environ),outer)
        self.assertIs(engines.execute,execute)

    def test_postproduction_source_mismatch_still_fails_and_restores(self):
        from icstudio import engines
        native,gui,engine,out,expected,outer,execute,runs=self.fixture()
        def readback(*args):
            changed=dict(args[3]);source=next(iter(expected['source_files']))
            changed_root=out/'changed-source';path=changed_root/source;path.parent.mkdir(parents=True)
            path.write_bytes(b'* rehashed changed reader source\n')
            changed.update(source_root=str(changed_root),source_files={source:auditor.sha(path)},reader_files={str(path):auditor.sha(path)})
            auditor.source_identity(changed)
            self.fail('Changed source was accepted.')
        with mock.patch.object(auditor,'readback',side_effect=readback):
            with self.assertRaisesRegex(ValueError,'External checker source differs from candidate'):
                auditor.verify(native,gui,engine,expected,out)
        self.assertEqual(len(runs),18)
        self.assertEqual(dict(os.environ),outer)
        self.assertIs(engines.execute,execute)
        self.assertEqual(json.loads((out/'failure.json').read_bytes())['status'],'FAIL')

    def test_failed_reference_production_still_restores_environment(self):
        from icstudio import engines
        native,gui,engine,out,expected,outer,execute,runs=self.fixture()
        with mock.patch.object(engines,'run_deck',side_effect=RuntimeError('reference failed')),mock.patch.object(auditor,'readback') as readback:
            with self.assertRaisesRegex(RuntimeError,'reference failed'):
                auditor.verify(native,gui,engine,expected,out)
        readback.assert_not_called()
        self.assertEqual(dict(os.environ),outer)
        self.assertIs(engines.execute,execute)
        self.assertEqual(json.loads((out/'failure.json').read_bytes())['status'],'FAIL')

if __name__=='__main__':unittest.main()
