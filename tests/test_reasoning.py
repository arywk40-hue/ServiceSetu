"""An adapter fallback must never masquerade as live ASI1 evidence."""
import asyncio
import json
import sys
import unittest
from types import SimpleNamespace
from unittest.mock import patch
from servicesetu.reasoning import Reasoner
from tests.test_proofs import Clock


class ReasoningSource(unittest.TestCase):
    def test_follow_up_budget_context_is_sent_in_rupees_not_paise(self):
        captured = {}
        class Client:
            def __init__(self,**kwargs): self.chat=SimpleNamespace(completions=self)
            async def create(self,**kwargs):
                captured.update(json.loads(kwargs["messages"][-1]["content"]))
                return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content='{"area":"Indiranagar"}'))])
            async def close(self): pass
        reasoner=Reasoner(); reasoner.key="synthetic-key"
        with patch.dict(sys.modules,{"openai":SimpleNamespace(AsyncOpenAI=Client)}):
            asyncio.run(reasoner.parse("Indiranagar",Clock()(),{"budget":100000}))
        self.assertEqual(captured["known_request"]["budget_rupees"],"1000")
        self.assertNotIn("budget",captured["known_request"])

    def test_invalid_model_output_is_identified_as_fallback(self):
        class Client:
            def __init__(self,**kwargs):self.chat=SimpleNamespace(completions=self)
            async def create(self,**kwargs):return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content='[]'))])
            async def close(self):pass
        reasoner=Reasoner();reasoner.key="synthetic-key"
        with patch.dict(sys.modules,{"openai":SimpleNamespace(AsyncOpenAI=Client)}):
            result=asyncio.run(reasoner.parse("AC service in Indiranagar Bengaluru tomorrow 10am under INR 1000",Clock()()))
        self.assertEqual(reasoner.last_source["parse"],"fallback")
        self.assertEqual(result["budget"],100000)

    def test_valid_model_output_records_api_source(self):
        response={"service":"ac","city":"bengaluru","area":"indiranagar","slot":"2026-10-14T10:00:00+05:30","budget_rupees":1000}
        class Client:
            def __init__(self,**kwargs):self.chat=SimpleNamespace(completions=self)
            async def create(self,**kwargs):return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=json.dumps(response)))])
            async def close(self):pass
        reasoner=Reasoner();reasoner.key="synthetic-key"
        with patch.dict(sys.modules,{"openai":SimpleNamespace(AsyncOpenAI=Client)}):
            result=asyncio.run(reasoner.parse("Synthetic input",Clock()()))
        self.assertEqual(reasoner.last_source["parse"],"asi1")
        self.assertEqual(result["budget"],100000)
