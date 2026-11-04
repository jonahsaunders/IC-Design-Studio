import math
import unittest
from scripts.ihp_transformer_capacitance import build, contract, apply


class IHPTransformerTests(unittest.TestCase):
    def model(self):
        weights = {'A': {'a0': .25, 'a1': .75}, 'B': {'b0': .4, 'b1': .6}, 'g': {'g': 1.}}
        return build(weights, {'A': 7., 'B': 10., 'g': 0.}, {('A','B'): 19./3},
                     {'A': 15., 'B': 23., 'g': 30.}, 'g')

    def test_every_physical_matrix_column_matches_expand_then_schur(self):
        nodes = ('a0','a1','b0','b1','g')
        weights = {'A': {'a0': .25, 'a1': .75}, 'B': {'b0': .4, 'b1': .6}, 'F': {'f': 1.}, 'g': {'g': 1.}}
        matrix = {(a,b): 0. for a in (*nodes,'f') for b in (*nodes,'f')}
        for a,b,c in [('A','F',10.),('B','F',20.),('F','g',30.),('A','g',2.),('A','B',3.)]:
            for x,wx in weights[a].items():
                for y,wy in weights[b].items():
                    value=c*wx*wy
                    matrix[x,x]+=value;matrix[y,y]+=value
                    matrix[x,y]-=value;matrix[y,x]-=value
        stamps=contract(self.model()['text'],nodes)
        for column in nodes:
            actual=apply(stamps,{n:float(n==column) for n in nodes})
            for row in nodes:
                expected=matrix[row,column]-matrix[row,'f']*matrix['f',column]/matrix['f','f']
                self.assertAlmostEqual(actual[row],expected,places=12)

    def test_common_mode_has_zero_charge_and_energy_is_nonnegative(self):
        nodes=('a0','a1','b0','b1','g');stamps=contract(self.model()['text'],nodes)
        result=apply(stamps,dict.fromkeys(nodes,1.2))
        self.assertLess(max(map(abs,result.values())),1e-12)
        values=dict(zip(nodes,(.12,-.35,.99,2.,-.17)))
        current=apply(stamps,values)
        self.assertGreaterEqual(math.fsum(values[n]*current[n] for n in nodes),0)
        self.assertAlmostEqual(math.fsum(current.values()),0.,places=12)

    def test_missing_or_wrong_current_return_is_rejected(self):
        text=self.model()['text'];lines=text.splitlines()
        index=next(i for i,v in enumerate(lines) if v.startswith('FIHP_RETURN_'))
        bad=['\n'.join(lines[:index]+lines[index+1:])]
        changed=lines.copy();changed[index]=changed[index].rsplit(' ',1)[0]+' 0.1';bad.append('\n'.join(changed))
        for value in bad:
            with self.assertRaisesRegex(ValueError,'reciprocal'):
                contract(value,('a0','a1','b0','b1','g'))

    def test_shunt_and_physical_voltage_drive_are_rejected(self):
        text=self.model()['text'];physical=('a0','a1','b0','b1','g')
        for bad in (text+'Rleak a0 g 1e12\n',text.replace('IHP_CPORT_0','a0')):
            with self.assertRaises(ValueError):contract(bad,physical)

    def test_bad_weights_and_nonpassive_diagonal_are_rejected(self):
        with self.assertRaises(ValueError):
            build({'A':{'a0':.5,'a1':.4},'g':{'g':1}}, {'A':2,'g':0},{},{'A':2},'g')
        with self.assertRaises(ValueError):
            build({'A':{'a0':.5,'a1':.5},'g':{'g':1}}, {'A':2,'g':0},{},{'A':1},'g')
