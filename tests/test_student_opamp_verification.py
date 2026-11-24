"""Run the verification fixtures and fault cases through both student tools."""

import math
import os
from pathlib import Path
import tempfile
import unittest

from icstudio import student_opamp_verification as suite, student_testbench as benches
from icstudio.example_schematics import arrange


NGSPICE = os.environ.get('ICSTUDIO_TEST_NGSPICE', '')


class OpAmpVerificationTests(unittest.TestCase):
    @unittest.skipUnless(Path(NGSPICE).is_file(), 'Set ICSTUDIO_TEST_NGSPICE to run the native engines')
    def test_reference_and_faults_match_across_both_workflows(self):
        project = arrange(benches.create(suite.PROJECT))
        by_id = {cell['id']: cell for cell in project['cells']}
        with tempfile.TemporaryDirectory(prefix='opamp-suite-') as tmp:
            for lesson in (lesson for lesson in benches.lessons() if lesson['bench_project'] == suite.PROJECT):
                for step, key in lesson['bench_checkpoints'].items():
                    with self.subTest(checkpoint=key):
                        unit = benches.course()[key]
                        cid = benches.fixture(project, key)
                        with self.assertRaisesRegex(ValueError, 'Complete the fixture'):
                            benches.prepare(project, lesson, 'spice', {'ngspice':NGSPICE}, step)
                        suite.edit(by_id[cid], unit, solved=True)
                        project['testbenches'].append(benches.solution_bench(project, cid, unit) | {'name':key.replace('-', '_')})
                        project['student_bench']['programs'][key] = benches.program(unit)
                        measurements = []
                        for workflow in benches.WORKFLOWS:
                            folder = Path(tmp)/key/workflow
                            job = benches.prepare(project, lesson, workflow, {'ngspice':NGSPICE}, step)
                            result = benches.run(job, folder, lambda *_: None)
                            benches.validate_result(job, result, folder)
                            check = result['student_bench']['check']
                            figures = benches.waveform_figures(key, result, verify=True)
                            self.assertEqual(check['status'], 'passed', (workflow, check, figures))
                            measurements.append({'Primary':check['value'], **figures})
                        for name, value in measurements[0].items():
                            self.assertTrue(math.isclose(value, measurements[1][name], rel_tol=.01, abs_tol=1e-10),
                                            (key, name, measurements))


if __name__ == '__main__':
    unittest.main()
