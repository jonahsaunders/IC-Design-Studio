"""Numeric PDK choices survive unit conversion without admitting a new size."""
import math
import unittest
from icstudio.catalog import _check_parameter, parameter_values


class NumericChoiceTests(unittest.TestCase):
    def test_mos_units_normalize_to_exact_source_choice(self):
        binding = dict(parameter_scale={'w': 1e6, 'l': 1e6}, parameters={
            'w': {'default': '10', 'fixed': '10'},
            'l': {'default': '2', 'choices': {'short': .9, 'nominal': 2., 'long': 4.}},
        })
        for value in ('.9u', '900n', '9e-7'):
            with self.subTest(value=value):
                actual = parameter_values(binding, dict(kind='NMOS', params={'w': '10u', 'l': value}))
                self.assertEqual(actual['l'], .9)
        with self.assertRaisesRegex(ValueError, 'must be one of'):
            parameter_values(binding, dict(kind='NMOS', params={'w': '10u', 'l': '.900000001u'}))

    def test_exact_discrete_choices_and_aliases_are_preserved(self):
        rule = {'choices': {'off': 0, 'on': 1, 'enabled': 1, 'nearby': 1 + 1e-13}}
        for value in rule['choices'].values():
            self.assertEqual(_check_parameter('mode', value, rule), value)
        with self.assertRaisesRegex(ValueError, 'must be one of'):
            _check_parameter('mode', 1e-30, rule)

    def test_ambiguous_rounding_is_rejected(self):
        rule = {'choices': {'one': 1., 'two': 1. + 1.5e-12}}
        with self.assertRaisesRegex(ValueError, 'must be one of'):
            _check_parameter('size', 1. + .75e-12, rule)

    def test_choice_normalization_keeps_other_constraints(self):
        rule = {'choices': {'one': 1., 'two': 2.}, 'integer': True, 'positive': True}
        self.assertEqual(_check_parameter('count', math.nextafter(1., 0.), rule), 1.)
        for value in (0, -1, 1.5, 1. + 1e-10, math.inf, math.nan):
            with self.subTest(value=value), self.assertRaises(ValueError):
                _check_parameter('count', value, rule)
        with self.assertRaisesRegex(ValueError, 'PDK minimum'):
            _check_parameter('size', math.nextafter(1., 0.), dict(rule, minimum=2))


if __name__ == '__main__': unittest.main()
