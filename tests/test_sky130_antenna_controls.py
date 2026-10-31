import copy
import io
import json
from pathlib import Path
import unittest
import xml.etree.ElementTree as ET

from scripts.check_sky130_antenna_controls import check

EVIDENCE=Path(__file__).resolve().parents[1]/'docs/validation/sky130-antenna-2026-10-11'


class NativeAntennaControlsTests(unittest.TestCase):
    def setUp(self):
        self.oracle=json.loads((EVIDENCE/'control-expectations.json').read_text())
        self.metrics=json.loads((EVIDENCE/'control-metrics.json').read_text())
        self.report=ET.parse(EVIDENCE/'control-report.lyrdb')

    def audit(self):
        return check(self.oracle,io.BytesIO(ET.tostring(self.report.getroot())),self.metrics)

    def test_all_retained_native_controls(self):
        result=self.audit()
        self.assertEqual((result['coupons'],result['expected_faults'],result['accepted_controls']),(178,90,88))
        self.assertFalse(result['qualified'])

    def test_rejects_omitted_stage(self):
        self.metrics['stages'].pop()
        with self.assertRaisesRegex(ValueError,'stage execution'):self.audit()

    def test_rejects_missing_fault_even_if_count_is_edited(self):
        items=self.report.find('./items'); items.remove(items[0])
        self.metrics['stages'][0]['markers']-=1
        with self.assertRaisesRegex(ValueError,'fault was missed'):self.audit()

    def test_rejects_duplicate_marker(self):
        items=self.report.find('./items');items.append(copy.deepcopy(items[0]))
        with self.assertRaisesRegex(ValueError,'duplicate marker'):self.audit()

    def test_rejects_marker_on_wrong_gate(self):
        value=self.report.find('./items/item/values/value')
        value.text=value.text.replace(',0;',',0.005;',1)
        # Alter the entire lower edge so the reported gate box is different.
        value.text=value.text.replace(',0)',',0.005)',1)
        with self.assertRaisesRegex(ValueError,'declared gate'):self.audit()

    def test_rejects_changed_measured_gate_area(self):
        value=next(v for v in self.report.findall('./items/item/values/value') if '[#gate_area]' in v.text)
        value.text='[#gate_area] float: 0.253'
        with self.assertRaisesRegex(ValueError,'rectangular oracle'):self.audit()

    def test_rejects_changed_diode_credit_ratio(self):
        value=next(v for v in self.report.findall('./items/item/values/value') if '[#EGAR]' in v.text)
        value.text='[#EGAR] float: 49'
        with self.assertRaisesRegex(ValueError,'rectangular oracle'):self.audit()

    def test_rejects_missing_numerical_properties(self):
        values=self.report.find('./items/item/values');values.remove(values[-1])
        with self.assertRaisesRegex(ValueError,'numerical evidence'):self.audit()

    def test_rejects_edited_oracle_classification(self):
        row=next(r for r in self.oracle['rows'] if r['expected_violation'])
        row['expected_violation']=False
        with self.assertRaisesRegex(ValueError,'rational oracle'):self.audit()

    def test_rejects_incomplete_fixture_set(self):
        self.oracle['rows'].pop()
        with self.assertRaisesRegex(ValueError,'control inventory'):self.audit()

    def test_rejects_counts_that_disagree_with_raw_markers(self):
        self.metrics['stages'][0]['markers']=0
        with self.assertRaisesRegex(ValueError,'metrics differ'):self.audit()


if __name__=='__main__':unittest.main()
