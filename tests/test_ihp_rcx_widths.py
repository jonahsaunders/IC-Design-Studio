import unittest
from scripts.check_ihp_rcx_widths import coverage, tables, LAYERS, KINDS


class IHPWidthCoverageTests(unittest.TestCase):
    def rules(self, widths='0.2 1 3.5 5'):
        text = 'DensityModel 0\n'
        for n, layer in enumerate(LAYERS, 1):
            for kind in KINDS:
                if n in (1, 7) and kind == 'OVERUNDER':
                    continue
                values = '' if n == 7 and kind in ('UNDER', 'DIAGUNDER', 'OVERUNDER') else widths
                text += f'Metal {n} {kind}\nWIDTH Table {len(values.split())} entries: {values}\n'
        return text

    def fill(self):
        return [dict(layer=layer, box_nm=[0, 0, 3500 if n < 5 else 5000, 6000])
                for n, layer in enumerate(LAYERS)]

    def test_complete_points_are_only_coverage_not_qualification(self):
        result = coverage(self.rules(), self.fill())
        self.assertTrue(result['passed'])
        self.assertFalse(result['qualified'])

    def test_single_width_model_is_rejected_on_all_layers(self):
        result = coverage(self.rules('0.2'), self.fill())
        self.assertFalse(result['passed'])
        self.assertEqual({r['layer'] for r in result['missing']}, set(LAYERS))

    def test_interpolated_and_rounded_points_are_not_exact_coverage(self):
        for values in ('0.2 6', '0.2 3.499999 5'):
            self.assertFalse(coverage(self.rules(values), self.fill())['passed'])

    def test_malformed_counts_nonfinite_duplicate_and_order_fail(self):
        invalid = [self.rules().replace('WIDTH Table 4', 'WIDTH Table 5', 1)]
        invalid += [self.rules(v) for v in ('0.2 NaN', '0.2 Infinity', '0.2 -1', '0.2 0.2', '1 0.2')]
        for text in invalid:
            with self.subTest(text=text[:100]), self.assertRaises(ValueError):
                tables(text)

    def test_missing_repeated_empty_and_multiple_models_fail(self):
        bad = [self.rules().replace('Metal 2 OVER\nWIDTH Table 4 entries: 0.2 1 3.5 5\n', ''),
               self.rules()+'Metal 1 OVER\nWIDTH Table 1 entries: 1\n',
               self.rules().replace('WIDTH Table 4 entries: 0.2 1 3.5 5', 'WIDTH Table 0 entries: ', 1),
               self.rules()+'DensityModel 1\n']
        for text in bad:
            with self.subTest(text=text[:100]), self.assertRaises(ValueError):
                tables(text)

    def test_missing_layers_and_invalid_rectangles_fail(self):
        with self.assertRaises(ValueError):
            coverage(self.rules(), self.fill()[:-1])
        for box in ([0, 0, 0, 5], [0, 0, -1, 5], [0, 0, 3.5, 5], [0, 0, True, 5]):
            fill = self.fill(); fill[0]['box_nm'] = box
            with self.subTest(box=box), self.assertRaises(ValueError):
                coverage(self.rules(), fill)
