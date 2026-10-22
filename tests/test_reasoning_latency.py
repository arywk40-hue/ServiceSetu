"""Slow model calls fall back without authorizing consequences."""
import asyncio
import sys
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from servicesetu.reasoning import Reasoner
from tests.test_proofs import Clock


class ReasoningLatency(unittest.TestCase):
    def run_slow(self, operation):
        closed = []
        class Client:
            def __init__(self, **kwargs):
                self.chat = SimpleNamespace(completions=self)
                if kwargs['max_retries'] != 0:
                    raise AssertionError('Slow reasoning must not retry')
            async def create(self, **kwargs):
                await asyncio.sleep(60)
            async def close(self):
                closed.append(True)
        reasoner = Reasoner()
        reasoner.key = 'synthetic-key'
        with patch.dict(sys.modules, {'openai': SimpleNamespace(AsyncOpenAI=Client)}), \
             patch('servicesetu.reasoning.PARSE_TIMEOUT_SECONDS', .01), \
             patch('servicesetu.reasoning.COMPARE_TIMEOUT_SECONDS', .01):
            result = asyncio.run(operation(reasoner))
        self.assertEqual(closed, [True])
        return reasoner, result

    def test_slow_parse_preserves_safe_request_fields(self):
        reasoner, result = self.run_slow(lambda r: r.parse(
            'AC service in Indiranagar Bengaluru tomorrow 10am under INR 1000', Clock()()))
        self.assertEqual(reasoner.last_source['parse'], 'fallback')
        self.assertEqual(result['budget'], 100000)
        self.assertEqual(result['service'], 'ac')
        self.assertNotIn('approval', result)

    def test_slow_comparison_returns_only_existing_quote_facts(self):
        quotes = [{'id': 'q_1', 'name': 'Checked provider', 'amount': 69900,
                   'trust': {'status': 'verified'}},
                  {'id': 'q_2', 'name': 'Other provider', 'amount': 74900,
                   'trust': {'status': 'provider_supplied'}}]
        reasoner, result = self.run_slow(lambda r: r.explain(quotes, []))
        self.assertEqual(reasoner.last_source['explain'], 'fallback')
        self.assertIn('Checked provider', result)
        self.assertIn('699.00', result)
