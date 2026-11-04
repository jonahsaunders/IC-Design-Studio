"""Missing frame identifiers must not manufacture an enclosure exemption."""
from collections import Counter
from copy import deepcopy
import json
from pathlib import Path
import tempfile
import unittest
import zipfile

import klayout.db as k
from icstudio import digital_sky130_frame_scope as scope
from icstudio.digital_sky130_rules import evaluate
from scripts.sky130_block_applicability import audit
from scripts.sky130_rule_inventory import manual_rows
from scripts.prepare_sky130_rule_checks import payload
from tests.test_sky130_application_rules import fixture

ROOT = Path(__file__).resolve().parents[1]


class FrameScopeTests(unittest.TestCase):
    def baseline(self):
        return json.loads((ROOT/'docs/validation/sky130-filled-replay-2026-10-14.json').read_bytes())['cases'][0]['execution']

    def test_only_two_enclosure_rows_change_and_measurements_are_preserved(self):
        before = self.baseline(); saved = deepcopy(before); after = scope.correct(before)
        targets = {item['id'] for item in scope.CORRECTIONS}
        self.assertEqual(before, saved)
        for old, new in zip(before['rows'], after['rows']):
            if old['id'] in targets:
                self.assertEqual(new['disposition'], 'execution-review-required')
                self.assertEqual({key:value for key,value in old.items() if key not in ('disposition','reason')},
                                 {key:value for key,value in new.items() if key not in ('disposition','reason')})
            else:
                self.assertEqual(old, new)
        self.assertEqual(after['counts']['absent-operand'], before['counts']['absent-operand']-2)
        self.assertEqual(after['counts']['execution-review-required'], before['counts']['execution-review-required']+2)
        self.assertEqual(scope.correct(after), after)

    def test_exact_public_enclosure_rows_are_bound(self):
        with zipfile.ZipFile(ROOT/'tests/fixtures/sky130-filled-references-v1.zip') as archive:
            source = scope.CORRECTIONS[0]['source']
            rows = {r['id']:r for r in manual_rows(archive.read('sources/'+source), source)}
        for item in scope.CORRECTIONS:
            row = rows[item['id']]
            for key in ('source','source_sha256','record','rule'):
                self.assertEqual(row[key], item[key])
            self.assertEqual(row['flags'], ['F'])
            self.assertIn('Enclosure', row['description'])
        # Preserve the two explicit upstream N/A entries and binary spacing.
        for index in (23,24,25):
            self.assertNotIn(source+'#'+str(index), {x['id'] for x in scope.CORRECTIONS})

    def test_real_unmarked_geometry_does_not_disappear_from_applicability(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            for name, data in payload().items():
                if name.startswith('sources/'):
                    path = root/name; path.parent.mkdir(parents=True, exist_ok=True); path.write_bytes(data)
            layout = k.Layout(); layout.dbu = .001; top = layout.create_cell('unmarked_block')
            top.shapes(layout.layer(64,20)).insert(k.Box(0,0,10000,10000))
            top.shapes(layout.layer(68,20)).insert(k.Box(1000,1000,9000,9000))
            gds = root/'control.gds'; layout.write(str(gds))
            for markers in (False, True):
                if markers:
                    top.shapes(layout.layer(81,12)).insert(k.Box(-10000,-10000,20000,20000))
                    layout.write(str(gds))
                original = audit(gds, root/'sources'); corrected = scope.correct(original)
                self.assertEqual(corrected['gds_sha256'], original['gds_sha256'])
                self.assertEqual(corrected['operand_counts'], original['operand_counts'])
                for item in scope.CORRECTIONS:
                    row = next(r for r in corrected['rows'] if r['id'] == item['id'])
                    self.assertEqual(row['disposition'], 'execution-review-required')
                self.assertFalse(corrected['qualified'])

    def test_changed_missing_duplicate_and_promoted_sources_are_rejected(self):
        for fault in ('missing','duplicate','source','rule','executed','advisory','counts'):
            bad = self.baseline(); row = next(r for r in bad['rows'] if r['id'] == scope.CORRECTIONS[0]['id'])
            if fault == 'missing': bad['rows'].remove(row)
            elif fault == 'duplicate': bad['rows'].append(deepcopy(row))
            elif fault == 'source': row['source_sha256'] = 'a'*64
            elif fault == 'rule': row['rule'] = 'x.other'
            elif fault == 'executed': row.update(disposition='executed-reviewed', execution={})
            elif fault == 'advisory': row['disposition'] = 'advisory'
            if fault != 'counts': bad['counts'] = dict(Counter(r['disposition'] for r in bad['rows']))
            else: bad['counts']['absent-operand'] += 1
            with self.subTest(fault=fault), self.assertRaises(ValueError): scope.correct(bad)

    def test_application_rejects_removed_review_and_restored_false_absence(self):
        with tempfile.TemporaryDirectory() as td:
            _, _, good = fixture(Path(td))
            for fault in ('missing-review','changed-review','restored-absence','changed-reason','execution'):
                bad = deepcopy(good); ledger = bad['ledger']
                row = next(r for r in ledger['rows'] if r['id'] == scope.CORRECTIONS[1]['id'])
                if fault == 'missing-review': ledger.pop('frame_scope_review')
                elif fault == 'changed-review': ledger['frame_scope_review']['qualified'] = True
                elif fault == 'restored-absence': row['disposition'] = 'absent-operand'
                elif fault == 'changed-reason': row['reason'] = 'No markers means inside die'
                else: row['execution'] = {}
                ledger['counts'] = dict(Counter(r['disposition'] for r in ledger['rows']))
                bad['coverage']['counts'] = ledger['counts']
                with self.subTest(fault=fault), self.assertRaises(ValueError):
                    evaluate(bad, good['gds_sha256'], good['checkpoint_sha256'], good['top'], good['platform_fingerprint'], good['policy'])


if __name__ == '__main__': unittest.main()
