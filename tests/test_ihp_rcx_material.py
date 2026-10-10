from copy import deepcopy
import unittest
from scripts.ihp_rcx_material import LAYERS, SOURCE_SHA256, apply, nominal_sheets


class Layer:
    def __init__(self): self.resistance = 99.
    def getResistance(self): return self.resistance
    def setResistance(self, value): self.resistance = value


class Technology:
    def __init__(self): self.layers = {name: Layer() for name in LAYERS}
    def findLayer(self, name): return self.layers.get(name)


class IHPRCXMaterialTests(unittest.TestCase):
    def setUp(self):
        self.source = 'variants (),(lvs)\n' + '\n'.join(
            f' resist (allm{i})/metal{i} {v}' for i,v in enumerate((110,88,88,88,88,18,11),1))
        self.material = dict(schema=1,source_sha256=SOURCE_SHA256,
            extraction_style='ngspice()',sheet_ohms=nominal_sheets(self.source))

    def test_corner_values_cannot_overwrite_nominal(self):
        text = self.source+'\nvariants (hrhc),(hrlc)\n resist (allm1)/metal1 135\n'
        self.assertEqual(nominal_sheets(text)['Metal1'], .110)

    def test_missing_ambiguous_and_malformed_material_fail(self):
        for text in (self.source.replace('metal7 11','metal7 None'),
                     self.source+'\n resist (allm1)/metal1 110',
                     self.source.replace('allm1)/metal1','allm1)/metal2'),
                     self.source.replace('variants (),(lvs)','variants (hrhc),(hrlc)')):
            with self.subTest(text=text), self.assertRaises(ValueError): nominal_sheets(text)

    def test_explicit_material_replaces_routing_overrides(self):
        tech=Technology();result=apply(tech,self.material)
        self.assertEqual(set(result['previous_sheet_ohms'].values()), {99.})
        self.assertEqual([tech.layers[n].resistance for n in LAYERS], [.110,.088,.088,.088,.088,.018,.011])
        self.assertEqual(result['required_extraction_option'],'-lef_res')

    def test_wrong_revision_corner_or_values_fail_before_mutation(self):
        for key,value in [('source_sha256','0'*64),('extraction_style','ngspice(hrhc)'),
                          ('sheet_ohms',{**self.material['sheet_ohms'],'Metal1':.135})]:
            tech=Technology();material=deepcopy(self.material);material[key]=value
            with self.subTest(key=key), self.assertRaises(ValueError):apply(tech,material)
            self.assertEqual({layer.resistance for layer in tech.layers.values()},{99.})

    def test_missing_layer_fails_before_any_material_change(self):
        tech=Technology();del tech.layers['TopMetal2']
        with self.assertRaisesRegex(ValueError,'Missing'):apply(tech,self.material)
        self.assertEqual({layer.resistance for layer in tech.layers.values()},{99.})
