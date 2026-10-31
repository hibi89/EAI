"""P7 independent CPU decision engine: correctness, limits, explainability and safety."""
from copy import deepcopy
from decimal import Decimal
import unittest
from unittest.mock import patch

from eai.decision_engine import (DECISION_VERSION, validate_choice_goal,
                                  execute_choice_goal, render_decision)


class DecisionEngineTests(unittest.TestCase):
    def setUp(self):
        self.raw = {
            'version': 1, 'kind': 'choose_options', 'goal': 'Select safe workstation',
            'criteria': [
                {'id': 'price', 'unit': 'USD', 'direction': 'min', 'weight': '6',
                 'score_min': '0', 'score_max': '1000', 'hard_max': '700'},
                {'id': 'ram', 'unit': 'GB', 'direction': 'max', 'weight': '2',
                 'score_min': '8', 'score_max': '64', 'hard_min': '16'},
            ],
            'options': [
                {'id': 'A', 'values': {'price': '500', 'ram': '16'}},
                {'id': 'B', 'values': {'price': '600', 'ram': '32'}},
                {'id': 'C', 'values': {'price': '800', 'ram': '64'}},
                {'id': 'D', 'values': {'price': '400'}},
            ],
        }

    def solve(self, data=None):
        return execute_choice_goal(validate_choice_goal(self.raw if data is None else data))

    def test_valid_selection_tracks_only_feasible(self):
        report = self.solve()
        self.assertEqual(report['plan_version'], DECISION_VERSION)
        self.assertEqual(report['status'], 'DECIDED')
        self.assertEqual(report['ranking'], ['A', 'B'])
        self.assertEqual(report['winners'], ['A'])
        self.assertEqual(report['pareto_frontier'], ['A', 'B'])
        self.assertEqual([o['status'] for o in report['options']],
                         ['FEASIBLE', 'FEASIBLE', 'EXCLUDED', 'UNAVAILABLE'])
        self.assertEqual(report['options'][2]['constraint_breaches'][0]['criterion'], 'price')
        self.assertEqual(report['options'][3]['missing'], ['ram'])
        self.assertIn('Pareto', render_decision(report))

    def test_normalization_uses_explicit_stable_ranges(self):
        report = self.solve()
        self.assertEqual(report['options'][0]['score'], '41.07')
        self.assertEqual(report['options'][1]['score'], '40.71')
        # Scoring does not depend on current number or extrema of candidates.
        initial = report['options'][0]['score']
        revised = deepcopy(self.raw)
        revised['options'].append({'id': 'E', 'values': {'price': '695', 'ram': '16'}})
        self.assertEqual(self.solve(revised)['options'][0]['score'], initial)

    def test_dominated_option_is_not_on_pareto_frontier(self):
        raw = deepcopy(self.raw)
        raw['options'].append({'id': 'E', 'values': {'price': '600', 'ram': '16'}})
        result = self.solve(raw)
        row = next(o for o in result['options'] if o['id'] == 'E')
        self.assertEqual(row['dominated_by'], ['A', 'B'])
        self.assertNotIn('E', result['pareto_frontier'])

    def test_hard_limits_and_missing_data_fail_closed(self):
        raw = deepcopy(self.raw)
        raw['options'] = raw['options'][2:]
        report = self.solve(raw)
        self.assertEqual(report['status'], 'UNAVAILABLE')
        self.assertEqual(report['winners'], [])
        self.assertEqual(report['pareto_frontier'], [])
        self.assertIn('explain_infeasibility', [x['step'] for x in report['steps']])

    def test_exact_ties_not_arbitrary_break(self):
        raw = deepcopy(self.raw)
        raw['options'] = [raw['options'][0], {'id': 'T', 'values': {'price': '500', 'ram': '16'}}]
        report = self.solve(raw)
        self.assertEqual(report['status'], 'TIE')
        self.assertEqual(report['winners'], ['A', 'T'])
        self.assertEqual(report['pareto_frontier'], ['A', 'T'])

    def test_rounded_display_tie_does_not_force_raw_tie(self):
        raw = deepcopy(self.raw)
        raw['criteria'] = [{'id': 'price','unit': 'USD','direction': 'min','weight': '1',
                            'score_min': '0','score_max': '1000000'}]
        raw['options'] = [{'id':'A','values':{'price':'100'}},
                          {'id':'B','values':{'price':'100.000001'}}]
        report = self.solve(raw)
        self.assertEqual(report['options'][0]['score'], report['options'][1]['score'])
        self.assertEqual(report['status'], 'DECIDED')
        self.assertEqual(report['winners'], ['A'])

    def test_clamps_out_of_scoring_range_with_disclosure(self):
        raw = deepcopy(self.raw)
        raw['criteria'][0].pop('hard_max')
        raw['options'][0]['values']['price'] = '-100'
        raw['options'][1]['values']['price'] = '2000'
        result = self.solve(raw)
        a, b = result['options'][:2]
        self.assertEqual(a['per_criterion'][0]['normalized'], '100')
        self.assertTrue(a['per_criterion'][0]['outside_score_bounds'])
        self.assertEqual(b['per_criterion'][0]['normalized'], '0')
        self.assertTrue(b['per_criterion'][0]['outside_score_bounds'])

    def test_criterion_direction_controls_pareto(self):
        raw = deepcopy(self.raw)
        raw['options'] = [
            {'id':'A','values':{'price':'500','ram':'32'}},
            {'id':'B','values':{'price':'500','ram':'16'}},
        ]
        self.assertEqual(self.solve(raw)['options'][1]['dominated_by'], ['A'])

    def test_weights_change_selection_but_not_pareto(self):
        raw = deepcopy(self.raw)
        before = self.solve(raw)
        raw['criteria'][1]['weight'] = '10'
        after = self.solve(raw)
        self.assertEqual(before['pareto_frontier'], after['pareto_frontier'])
        self.assertEqual(before['winners'], ['A'])
        self.assertEqual(after['winners'], ['B'])

    def test_missing_must_not_be_invented_or_scored_zero(self):
        report = self.solve()
        o = report['options'][3]
        self.assertIsNone(o['score'])
        self.assertEqual(o['per_criterion'], [])

    def test_exact_decimal_not_floats(self):
        raw = deepcopy(self.raw)
        raw['criteria'] = [{'id':'x','unit':'units','direction':'max','weight':'1',
                            'score_min':'0','score_max':'1'}]
        raw['options'] = [{'id':'A','values':{'x':'0.1'}},
                          {'id':'B','values':{'x':'0.3'}}]
        report = self.solve(raw)
        self.assertEqual(report['options'][0]['score'], '10')
        self.assertEqual(report['options'][1]['score'], '30')
        self.assertEqual(report['winners'], ['B'])

    def test_input_structure_and_version_rejections(self):
        for replace_key, bad in [('version', True), ('version', 2), ('kind', 'arbitrary.execute'),
                                 ('criteria', []), ('options', []), ('goal', '')]:
            raw = deepcopy(self.raw)
            raw[replace_key] = bad
            with self.subTest(replace_key=replace_key, bad=bad), self.assertRaises(ValueError):
                validate_choice_goal(raw)
        for bad in [None, [], 'hello', {'kind':'choose_options'}]:
            with self.assertRaises(ValueError):
                validate_choice_goal(bad)

    def test_no_unknown_fields_or_hidden_metrics(self):
        raw = deepcopy(self.raw)
        raw['exec'] = 'rm -rf /'
        with self.assertRaises(ValueError):
            self.solve(raw)
        raw = deepcopy(self.raw)
        raw['criteria'][0]['command'] = 'delete'
        with self.assertRaises(ValueError):
            self.solve(raw)
        raw = deepcopy(self.raw)
        raw['options'][0]['values']['secret'] = '123'
        with self.assertRaises(ValueError):
            self.solve(raw)

    def test_numeric_types_and_limits_validation(self):
        for val in ['NaN', 'Infinity', '1e5', '1_000', '9999999999999999999999999',
                    2, 1.2, True]:
            raw = deepcopy(self.raw)
            raw['options'][0]['values']['price'] = val
            with self.subTest(val=val), self.assertRaises(ValueError):
                self.solve(raw)

    def test_duplicate_ids_and_invalid_ids_rejected(self):
        raw = deepcopy(self.raw)
        raw['options'][1]['id'] = 'A'
        with self.assertRaises(ValueError):
            self.solve(raw)
        raw = deepcopy(self.raw)
        raw['criteria'][1]['id'] = 'price'
        with self.assertRaises(ValueError):
            self.solve(raw)
        raw = deepcopy(self.raw)
        raw['options'][1]['id'] = '../private'
        with self.assertRaises(ValueError):
            self.solve(raw)

    def test_invalid_ranges_and_limits_rejected(self):
        for changes in [dict(score_min='20', score_max='20'),
                        dict(weight='0'), dict(weight='-1'),
                        dict(hard_min='900', hard_max='700'),
                        dict(direction='up')]:
            raw = deepcopy(self.raw)
            raw['criteria'][0].update(changes)
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                self.solve(raw)

    def test_limits_criteria_options_and_units(self):
        raw = deepcopy(self.raw)
        raw['criteria'] = raw['criteria'] * 5
        with self.assertRaises(ValueError):
            self.solve(raw)
        raw = deepcopy(self.raw)
        raw['options'] *= 7
        with self.assertRaises(ValueError):
            self.solve(raw)
        raw = deepcopy(self.raw)
        raw['criteria'][0]['unit'] = '💲'
        with self.assertRaises(ValueError):
            self.solve(raw)

    def test_no_network_model_gpu_for_decisions(self):
        with patch('eai.network.fetch_json', side_effect=AssertionError('network!')):
            report = self.solve()
        self.assertEqual(report['status'], 'DECIDED')


if __name__ == '__main__':
    unittest.main()
