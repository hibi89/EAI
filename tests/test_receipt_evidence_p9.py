"""P9: verify genuine P7/P8 receipts and reject forged displayed evidence."""
from copy import deepcopy
import unittest

from eai.decision_engine import execute_choice_goal, validate_choice_goal
from eai.receipt_guard import verify_goal_receipt


def fixture():
    return {
        'version': 1, 'kind': 'choose_options', 'goal': 'Local hardware options',
        'criteria': [
            {'id': 'price', 'direction': 'min', 'unit': 'KRW', 'weight': '2',
             'score_min': '0', 'score_max': '1000', 'hard_max': '900'},
            {'id': 'ram', 'direction': 'max', 'unit': 'GB', 'weight': '1',
             'score_min': '0', 'score_max': '64', 'hard_min': '16'},
        ],
        'options': [
            {'id': 'fast', 'values': {'price': '750', 'ram': '32'}},
            {'id': 'cheap', 'values': {'price': '500', 'ram': '16'}},
            {'id': 'expensive', 'values': {'price': '1200', 'ram': '64'}},
            {'id': 'unknown', 'values': {'price': '600'}},
        ],
    }


class ReceiptDisplayEvidenceTests(unittest.TestCase):
    def setUp(self):
        self.goal = validate_choice_goal(fixture())
        self.original = execute_choice_goal(self.goal)

    def assert_rejected(self, mutate, detail):
        report = deepcopy(self.original)
        mutate(report)
        with self.assertRaisesRegex(ValueError, detail):
            verify_goal_receipt('choose_options', self.goal, report)

    def test_untampered_receipt_passes(self):
        receipt = verify_goal_receipt('choose_options', self.goal, self.original)
        self.assertIn('detail_evidence', receipt['checks'])
        self.assertEqual(receipt['status'], 'PASS')

    def test_forged_public_criteria_rejected(self):
        self.assert_rejected(lambda r: r['criteria'][0].__setitem__('weight', '999'),
                             '평가 기준')

    def test_forged_visible_actual_rejected(self):
        self.assert_rejected(lambda r: r['options'][0]['per_criterion'][0].__setitem__('actual', '0'),
                             '표시 증거')

    def test_forged_visible_normalized_rejected(self):
        self.assert_rejected(lambda r: r['options'][0]['per_criterion'][0].__setitem__('normalized', '100'),
                             '표시 증거')

    def test_forged_outside_score_bound_flag_rejected(self):
        self.assert_rejected(lambda r: r['options'][0]['per_criterion'][0].__setitem__('outside_score_bounds', True),
                             '표시 증거')

    def test_forged_dominating_option_rejected(self):
        self.assert_rejected(lambda r: r['options'][0].__setitem__('dominated_by', ['expensive']),
                             '지배 근거')

    def test_forged_breach_amount_rejected(self):
        self.assert_rejected(lambda r: r['options'][2]['constraint_breaches'][0].__setitem__('required', '901'),
                             '제약 표시')

    def test_forged_solver_trace_rejected(self):
        self.assert_rejected(lambda r: r['steps'][1].__setitem__('skill', 'shell.execute.v1'),
                             '실행 단계')

    def test_forged_plan_version_rejected(self):
        self.assert_rejected(lambda r: r.__setitem__('plan_version', 'obsolete'),
                             '계획 버전')

    def test_tie_and_no_feasible_keep_legal_traces(self):
        raw = fixture()
        raw['options'][1]['values'] = dict(raw['options'][0]['values'])
        tied_goal = validate_choice_goal(raw)
        self.assertEqual(verify_goal_receipt(
            'choose_options', tied_goal, execute_choice_goal(tied_goal))['status'], 'PASS')
        raw = fixture()
        raw['criteria'][0]['hard_max'] = '1'
        blocked_goal = validate_choice_goal(raw)
        blocked_report = execute_choice_goal(blocked_goal)
        self.assertEqual(blocked_report['status'], 'UNAVAILABLE')
        self.assertEqual(verify_goal_receipt(
            'choose_options', blocked_goal, blocked_report)['status'], 'PASS')


if __name__ == '__main__':
    unittest.main()
