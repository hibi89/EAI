"""CPU-owned comparison solver: independent correctness and privacy checks."""
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from eai.analysis import compare_numeric_observations
from eai.intent import IntentSpec, RuleIntentParser, QwenIntentParser
from eai.runner import EAIRunner
from eai.storage import Store


class AnalysisTests(unittest.TestCase):
    def test_rank_and_sequential_change(self):
        result = compare_numeric_observations('2023=100,2024=125,2025=110')
        self.assertEqual([row['name'] for row in result['ranked']], ['2024', '2025', '2023'])
        self.assertEqual(result['gap'], '25')
        self.assertEqual(result['changes'], [
            {'from': '2023', 'to': '2024', 'absolute': '25', 'percent': '25'},
            {'from': '2024', 'to': '2025', 'absolute': '-15', 'percent': '-12'},
        ])

    def test_exact_decimals_and_negative_values(self):
        data = compare_numeric_observations('A=0.1;B=0.2;C=-0.2')
        self.assertEqual(data['gap'], '0.4')
        self.assertEqual(data['changes'][0]['percent'], '100')
        self.assertEqual(data['changes'][1]['percent'], '-200')

    def test_zero_and_negative_baseline_do_not_imply_growth(self):
        data = compare_numeric_observations('loss=-5,zero=0,profit=5')
        self.assertTrue(all(c['percent'] is None for c in data['changes']))
        self.assertTrue(any('0 이하' in n for n in data['notes']))

    def test_ties_sorted_stably_and_gap_zero(self):
        data = compare_numeric_observations('A=12,B=12,C=12')
        self.assertEqual(data['gap'], '0')
        self.assertEqual([r['name'] for r in data['ranked']], ['A', 'B', 'C'])

    def test_reject_bad_inputs_and_resource_abuse(self):
        invalid = ['', 'A=1', 'A=1,B=', 'A=1,a=2', 'A=1,B=1e309',
                   'A=1,B=nan', 'A=1,B=3+4', 'A=1,B=1,000',
                   'A=1,B=1;C=2'*17, 'A=1,B=2\nC=3', 'A=1,B=__import__("os")',
                   'A=1,B='+ '2'*60, 'A=1,B=1=2']
        for payload in invalid:
            with self.subTest(payload=payload[:45]), self.assertRaises(ValueError):
                compare_numeric_observations(payload)

    def test_intent_schema_and_rules(self):
        rule = RuleIntentParser()
        intent = rule.parse('비교 2024=100,2025=120')
        self.assertEqual(intent.task, 'compare')
        self.assertEqual(intent.query, '2024=100,2025=120')
        self.assertEqual(rule.parse('compare A=1,B=3').task, 'compare')
        with self.assertRaises(ValueError):
            IntentSpec.validate({'version':1,'task':'compare','expression':'','query':'A'*501})

    def test_cpu_only_cli_runner_no_network(self):
        class SpySearch:
            def search(self,*args,**kwargs):
                raise AssertionError('unrelated online requests prohibited')
        with tempfile.TemporaryDirectory() as d:
            store=Store(Path(d)/'test.sqlite3')
            try:
                runner=EAIRunner(store,search_tool=SpySearch())
                response=runner.ask('비교 A=100,B=120,C=132',allow_online=True)
                self.assertEqual(response.result.status,'OK')
                self.assertIn('B → C: 12 (10%)',response.text)
                self.assertEqual(len(store.recent_turns()),2)
            finally:
                store.close()

    def test_unsupported_input_reports_error_not_hallucination(self):
        with tempfile.TemporaryDirectory() as d:
            store=Store(Path(d)/'test.sqlite3')
            try:
                out=EAIRunner(store).ask('비교 A=1,B=oops')
                self.assertEqual(out.result.status,'ERROR')
                self.assertNotIn('최댓값',out.text)
            finally:
                store.close()

    def test_explicit_compare_does_not_load_qwen(self):
        class ExplodingParser:
            def parse(self,question):
                raise AssertionError('explicit numeric commands must stay CPU-only')
        with tempfile.TemporaryDirectory() as d:
            store=Store(Path(d)/'test.sqlite3')
            try:
                out=EAIRunner(store,parser=ExplodingParser()).ask('비교 A=100,B=110')
                self.assertEqual(out.result.data['changes'][0]['percent'],'10')
            finally:
                store.close()

    def test_large_fixed_point_values_have_exact_gap(self):
        data=compare_numeric_observations(
            'A=123456789012345678901234.123456789012,B=123456789012345678901235.123456789012')
        self.assertEqual(data['gap'], '1')

    def test_qwen_is_only_parser_for_comparison(self):
        class ParseOnly:
            def parse(self,question):
                return IntentSpec(task='compare',query='A=100,B=110')
        with tempfile.TemporaryDirectory() as d:
            store=Store(Path(d)/'test.sqlite3')
            try:
                out=EAIRunner(store,parser=ParseOnly()).ask('숫자 비교해 줘')
                self.assertEqual(out.result.data['changes'][0]['percent'],'10')
                self.assertIn('10%',out.text)
            finally:
                store.close()


if __name__ == '__main__':
    unittest.main()
