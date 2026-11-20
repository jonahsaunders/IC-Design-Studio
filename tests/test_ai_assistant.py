import json
import os
import shutil
import tempfile
import unittest
from icstudio import ai_providers as providers, ai_testbench, analog_guided, simulation, testbenches
from icstudio.model import clone, example


def rc_spec():
    return dict(name='rc_check', analysis=dict(type='tran', step='1u', stop='100u'), connections={},
                probes=['vin','vout'], measurements=[dict(name='output',node='vout',min=0, max=1.8)])


class ProviderContracts(unittest.TestCase):
    def test_profiles(self):
        bases = dict(qwen='https://workspace.ap-southeast-1.maas.aliyuncs.com/compatible-mode/v1',
                     azure='https://studio.openai.azure.com/openai/v1',
                     vertex='https://aiplatform.googleapis.com/v1/projects/test-project/locations/global/publishers/google/models',
                     custom='https://local.example/v1')
        for key, profile in providers.PROVIDERS.items():
            with self.subTest(provider=key):
                base = bases.get(key, profile.base)
                url, headers, body = providers.request_parts(key, base, 'model-1', 'example-token', 'explain')
                self.assertNotIn('example-token', url + json.dumps(body))
                self.assertIn('example-token', ' '.join(headers.values()))
                if key == 'anthropic':
                    self.assertEqual(url, base + '/messages')
                    self.assertEqual(headers['x-api-key'], 'example-token')
                    self.assertEqual(body['messages'][0]['content'], 'explain')
                    data = {'content':[{'type':'text','text':'ok'}]}
                elif key in ('openai', 'perplexity'):
                    self.assertEqual(url, base + ('/responses' if key == 'openai' else '/agent'))
                    self.assertEqual(body['input'], 'explain')
                    self.assertEqual(body.get('store') if key == 'openai' else body['tools'], False if key == 'openai' else [])
                    data = {'output':[{'type':'message','content':[{'type':'output_text','text':'ok'}]}]}
                elif key == 'bedrock':
                    self.assertEqual(url, base + '/model/model-1/converse')
                    self.assertEqual(body['messages'][0]['content'], [{'text':'explain'}])
                    data = {'output':{'message':{'content':[{'text':'ok'}]}}}
                elif key == 'vertex':
                    self.assertEqual(url, base + '/model-1:generateContent')
                    self.assertEqual(body['contents'][0]['parts'], [{'text':'explain'}])
                    data = {'candidates':[{'content':{'parts':[{'text':'private', 'thought':True},{'text':'ok'}]}}]}
                else:
                    self.assertEqual(url, base + '/chat/completions')
                    self.assertEqual(body, dict(model='model-1', messages=[{'role':'user','content':'explain'}]))
                    data = {'choices':[{'message':{'content':'ok'}}]}
                self.assertEqual(headers.get('api-key' if key=='azure' else 'Authorization'),
                                 'example-token' if key=='azure' else None if key=='anthropic' else 'Bearer example-token')
                self.assertEqual(providers.response_text(key,data), 'ok')
                with self.assertRaises(ValueError):
                    providers.response_text(key, {})

    def test_credentials_scoped_to_official_hosts(self):
        for key, url in [('azure','https://studio.openai.azure.com.example.org/openai/v1'),
                         ('vertex','https://127.0.0.1'), ('custom','http://private.example/v1'),
                         ('custom','https://name:password@example.org/v1'), ('openai','https://other.example/v1')]:
            with self.subTest(key=key), self.assertRaises(ValueError):
                providers.endpoint(key,url)
        providers.request_parts('ollama', providers.PROVIDERS['ollama'].base, 'llama3.2', '', 'hello')


class TestbenchContracts(unittest.TestCase):
    @unittest.skipUnless(os.environ.get('ICSTUDIO_NGSPICE') or shutil.which('ngspice'), 'ngspice is not installed')
    def test_saved_bench_runs_in_ngspice(self):
        project = example()
        cells, bench, _ = ai_testbench.propose(project, project['cells'][0], json.dumps(rc_spec()))
        project['cells'].extend(cells)
        project['testbenches'] = [bench]
        with tempfile.TemporaryDirectory() as folder:
            result = testbenches.simulate(project, bench, os.environ.get('ICSTUDIO_NGSPICE') or shutil.which('ngspice'), folder)
        self.assertEqual(result['testbench_id'], bench['id'])
        self.assertEqual(result['measurements']['status'], 'passed')
        self.assertGreater(result['measurements']['samples'], 20)

    def test_standalone_preserves_rc_waveform(self):
        project = example()
        original = clone(project)
        cells, bench, description = ai_testbench.propose(project, project['cells'][0], json.dumps(rc_spec()))
        self.assertEqual(project, original)
        self.assertIn('snapshot', description)
        project['cells'].extend(cells)
        project['testbenches'] = [bench]
        expected = simulation.run(original, original['top'], bench['analysis'])
        measured = simulation.run(project, bench['bench_cell'], bench['analysis'])
        self.assertEqual(expected['traces']['vout'], measured['traces']['vout'])
        self.assertEqual(testbenches.measure(measured,bench)['status'], 'passed')

    def test_ported_dut_and_rejected_drafts(self):
        project,cid = analog_guided.teaching_example(example(), 'amplifier')
        dut = next(c for c in project['cells'] if c['id'] == cid)
        spec = dict(name='amp_check', analysis={'type':'op'}, probes=['OUT'], measurements=[],
                    connections={'IN':dict(kind='dc',value='.8'), 'OUT':dict(kind='observe'),
                                 'VDD':dict(kind='dc',value='1.8'), 'VSS':dict(kind='ground')})
        cells,bench,_ = ai_testbench.propose(project,dut,json.dumps(spec))
        self.assertEqual((len(cells),bench['dut_cell']), (1,cid))
        for bad in [dict(probes=['made_up']),dict(analysis=dict(type='shell')),dict(name='../x'),dict(connections={}),
                    dict(connections={**spec['connections'],'VDD':dict(kind='dc',value='NaN')}),
                    dict(measurements=[dict(name='output',node='OUT',min=2,max=1)]),dict(command='unrecognized')]:
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                ai_testbench.propose(project,dut,json.dumps({**spec, **bad}))
