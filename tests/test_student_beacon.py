"""Replay each cumulative Beacon Run lesson through Icarus and the Hub grader."""

from contextlib import redirect_stdout
from io import StringIO
import json
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

from icstudio import student_beacon as beacon
from icstudio.digital_vga import preview_inputs
from icstudio.model import atomic_write
from icstudio.student_hub import curriculum, evaluate, prepare_lesson
from icstudio.student_learning import solution_html, study_guide
from icstudio.student_projects import create


IVERILOG = shutil.which('iverilog')
VVP = shutil.which('vvp')


def apply_solution(project, key):
    files = {item['path']:item for item in project['cells'][0]['digital']['files']}
    timing, game, display = (files[name] for name in beacon.FILE_NAMES[:3])
    if key=='timing':
        timing['text'] = timing['text'].replace('x < 735', 'x < 752')
        display['text'] = display['text'].replace("if (upper_left) rgb = 6'b11_00_00;",beacon.COLORS)
    elif key=='board':
        display['text'] = display['text'].replace("if (upper_left) rgb = 6'b11_00_00;",beacon.BOARD)
    elif key=='movement':
        game['text'] = game['text'].replace('next_y = rover_y;', 'next_y = rover_y;\n'+beacon.MOVE)
    elif key=='collect':
        logic, display_logic = beacon.stage(key)[-1].split('\n\n')
        game['text'] = game['text'].replace('collected <= collected;',logic)
        home = "else if (home) rgb = 6'b00_10_00;"
        display['text'] = display['text'].replace(home, home+'\n'+display_logic.split('\n')[-1])
    elif key=='finish':
        game_logic, display_logic = beacon.FINISH.split('\n\n')
        game['text'] = game['text'].split('end else if (frame_tick) begin')[0]+'\n'.join(game_logic.split('\n')[1:])+'\n  end\nendmodule\n'
        display['text'] = display['text'].replace("if (rover) rgb = 6'b00_11_11;", '\n'.join(display_logic.split('\n')[1:]))


class BeaconRunTests(unittest.TestCase):
    def test_hub_progression_and_vga_source_exchange(self):
        data = curriculum()
        lessons = [item for item in data['lessons'] if item.get('vga_lesson')]
        material = study_guide(data)
        self.assertEqual(len(lessons),5)
        self.assertEqual({item['workspace'] for item in lessons},{'beacon-run'})
        for earlier, later in zip(lessons,lessons[1:]):
            self.assertEqual(later['requires'],[earlier['id']])
        for lesson in lessons:
            key = lesson['id']
            rendered = solution_html(lesson['steps'][1],material['practice'][key],material['lessons'][key])
            self.assertIn('<pre>',rendered)
        preview = preview_inputs(beacon.config())
        self.assertEqual(preview['topModule'],beacon.STARTER)
        self.assertEqual(set(preview['sources']),set(beacon.FILE_NAMES[:3]))

    @unittest.skipUnless(IVERILOG and VVP,'Icarus Verilog is required')
    def test_each_solution_unlocks_only_its_next_checkpoint(self):
        project = create(beacon.STARTER)
        stages = [stage[0] for stage in beacon.STAGES]
        with tempfile.TemporaryDirectory(prefix='beacon-rtl-') as temp:
            root = Path(temp)
            for count in range(len(stages)+1):
                if count:
                    apply_solution(project,stages[count-1])
                for item in project['cells'][0]['digital']['files']:
                    (root/item['path']).write_text(item['text'],encoding='utf-8')
                subprocess.run([IVERILOG,'-g2012','-s','beacon_tb','-o','beacon.vvp',*beacon.FILE_NAMES],
                               cwd=root,check=True,capture_output=True,text=True,input='')
                test = subprocess.run([VVP,'beacon.vvp'],cwd=root,check=True,capture_output=True,text=True,input='')
                passed = [line.split()[-1] for line in test.stdout.splitlines()
                          if line.startswith('STUDENT_CHECKS PASS beacon_run ')]
                self.assertEqual(passed,stages[:count],test.stdout)

    @unittest.skipUnless(IVERILOG and VVP,'Icarus Verilog is required')
    def test_normal_worker_and_grader(self):
        from icstudio.worker import main

        project = create(beacon.STARTER)
        lessons = beacon.lessons()
        for stage in beacon.STAGES:
            apply_solution(project,stage[0])
        lesson = lessons[-1]
        with tempfile.TemporaryDirectory(prefix='beacon-worker-') as temp:
            tools = dict(iverilog=IVERILOG,vvp=VVP)
            job = prepare_lesson(project,tools,toolchain='custom')
            root = Path(temp)
            inp, out = root/'input.json', root/'result.json'
            atomic_write(inp,json.dumps(job))
            with redirect_stdout(StringIO()) as stdout:
                status = main(inp,out)
            self.assertEqual(status,0,stdout.getvalue())
            row = dict(job=job,result=json.loads(out.read_text(encoding='utf-8')),state='Complete',path=root)
            result = evaluate(lesson['steps'][1],lesson,project,[row])
            self.assertTrue(result['result_sha256'])


if __name__=='__main__':
    unittest.main()
