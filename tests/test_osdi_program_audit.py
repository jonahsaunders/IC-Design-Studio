"""Imported programs must load only the explicitly verified model runtime."""
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from icstudio.model import example
from icstudio.osdi import configure
from icstudio.spice_program import run_program


class OSDIProgramAuditTests(unittest.TestCase):
    def test_verified_models_are_loaded_after_program_validation(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td);library=root/'model with spaces.osdi'
            library.write_bytes(b'Unit fixture; never passed to a simulator')
            p=example();p['pdk']['simulation']={'requires_osdi':True}
            p['simulation_runtime']={'osdi':configure([library])}
            deck='* program\nV1 out 0 1\n.control\nop\n.endc\n.end\n'
            def run(text,destination):
                destination.mkdir()
                return run_program(p,p['top'],{'probes':'v(out)'},'ngspice',destination,
                                   lambda *_:None,lambda *_:text,'test',{},'analysis_cases')
            with patch('icstudio.engines.execute',side_effect=RuntimeError('engine boundary')) as execute:
                with self.assertRaisesRegex(RuntimeError,'engine boundary'):run(deck,root/'good')
                self.assertIn('pre_osdi runtime-osdi/model-0.osdi',(root/'good/input.cir').read_text())
                self.assertEqual((root/'good/runtime-osdi/model-0.osdi').read_bytes(),library.read_bytes())
                execute.reset_mock()
                with self.assertRaisesRegex(ValueError,'pre_osdi'):
                    run(deck.replace('op\n','pre_osdi untrusted.osdi\nop\n'),root/'untrusted')
                execute.assert_not_called()
                library.write_bytes(b'changed')
                with self.assertRaisesRegex(ValueError,'missing or changed'):run(deck,root/'changed')
                execute.assert_not_called()

    def test_backend_preserves_program_execution_and_waveform_inventory(self):
        from icstudio.physical_backend import native_run
        from icstudio.model import file_digest
        for kind,module in [('program','icstudio.native_spice.run'),('xschem','icstudio.xschem_runtime.run'),('op','icstudio.engines.run_ngspice')]:
            with self.subTest(kind=kind),tempfile.TemporaryDirectory() as td:
                root=Path(td);p=example()
                job={'project':p,'cell':p['top'],'settings':{'type':kind,'managed_osdi':'ihp-sg13g2'},'executable':'included-ngspice'}
                (root/'native-input.json').write_text(json.dumps(job))
                def simulate(project,cid,settings,executable,output,progress):
                    (output/'waveforms').mkdir();(output/'waveforms/case1.raw').write_bytes(b'fixture')
                    return {'program_status':'Complete','case_directory':str(output)}
                with patch(module,side_effect=simulate) as engine:native_run(root)
                engine.assert_called_once()
                inventory=json.loads((root/'output/physical-artifacts.json').read_text())
                self.assertEqual(inventory['waveforms/case1.raw'],file_digest(root/'output/waveforms/case1.raw'))
                self.assertIn('physical-backend-result.json',inventory)


if __name__=='__main__':unittest.main()
