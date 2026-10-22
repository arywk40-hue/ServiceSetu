"""Readable provider facts and conversational wording do not grant authority."""
import asyncio
import json
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from servicesetu import cards
from servicesetu.core import Store
from servicesetu.conversation import Conversation
from servicesetu.reasoning import Reasoner
from servicesetu.service import Services, LocalBus
from tests.test_proofs import Clock


class CustomerLanguage(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.clock = Clock()
        self.store = Store(Path(self.tmp.name) / "language.db", self.clock)
        self.store.seed()
        self.slot = self.store.provider("p1")["slots"][0]
        self.reasoner = Reasoner()
        self.reasoner.key = None
        self.conversation = Conversation(self.store, self.reasoner)
        self.bus = LocalBus(Services(self.store, payment_mode="mock"))

    def send(self, text):
        return asyncio.run(self.conversation.handle("alice", text, self.bus))

    def quotes(self):
        return [self.store.quote("alice", p, self.slot) for p in ("p1", "p2")]

    def model_comparison(self, quotes, response):
        class Client:
            def __init__(self, **kwargs): self.chat = SimpleNamespace(completions=self)
            async def create(self, **kwargs):
                return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=json.dumps(response)))])
            async def close(self): pass
        self.reasoner.key = "synthetic-key"
        with patch.dict(sys.modules, {"openai":SimpleNamespace(AsyncOpenAI=Client)}):
            return asyncio.run(self.reasoner.explain(quotes, []))

    def test_shortlist_groups_facts_without_raw_identifiers(self):
        quotes = self.quotes()
        reply = cards.shortlist(quotes, [{"name":"Lapsed AC", "reason":"Credential expired"}])
        text = reply["text"]
        for expected in ("### 1. CoolCare AC", "**Appointment:**", "**Documents:**",
                         "**Includes:**", "**Not included:**", "### Other providers", "reply 'option 1'"):
            self.assertIn(expected, text)
        for raw in (quotes[0]["id"], "69900", "mock-registry://", self.slot):
            self.assertNotIn(raw, text)
        payload = json.loads(reply["metadata"]["card_payload"])
        self.assertEqual(payload["items"][0]["primary_cta"]["selection"]["quote_id"], quotes[0]["id"])

    def test_provider_supplied_and_mock_registry_labels_are_distinct(self):
        quotes = self.quotes()
        first = cards.shortlist([quotes[0]], [])["text"]
        second = cards.shortlist([quotes[1]], [])["text"]
        self.assertIn("fictional mock registry", first)
        self.assertNotIn("Provider-supplied", first)
        self.assertIn("Provider-supplied — not independently verified", second)
        self.assertNotIn("fictional mock registry", second)

    def test_model_cannot_assign_registry_status_to_supplied_documents(self):
        quotes = self.quotes()
        text = self.model_comparison(quotes, {"quote_id":quotes[1]["id"], "reason":"mock_registry"})
        self.assertEqual(self.reasoner.last_source["explain"], "fallback")
        self.assertIn("CoolCare AC", text)
        self.assertNotIn("Breeze AC", text)

    def test_valid_model_choice_renders_only_validated_facts(self):
        quotes = self.quotes()
        text = self.model_comparison(quotes, {"quote_id":quotes[0]["id"], "reason":"mock_registry",
                                             "explanation":"All providers are genuinely certified"})
        self.assertEqual(self.reasoner.last_source["explain"], "asi1")
        self.assertIn("INR 699.00", text)
        self.assertIn("fictional mock registry", text)
        self.assertNotIn("genuinely certified", text)

    def test_emotional_request_keeps_explicit_service_constraints(self):
        reply = self.send("I'm really frustrated, my AC is not cooling in Indiranagar Bengaluru. Tomorrow at 10 AM, under INR 1000.")
        self.assertIn("That sounds difficult", reply["text"])
        self.assertIn("Provider-confirmed demo quotes", reply["text"])
        job = self.store.session("alice")["job"]
        self.assertEqual(job["budget"], 100000)
        self.assertEqual(job["slot"], self.slot)

    def test_emotion_alone_does_not_invent_service_details(self):
        reply = self.send("I'm worried and overwhelmed")
        self.assertIn("which service you need", reply["text"])
        self.assertIn("your area and city", reply["text"])
        with self.store.connect() as db:
            self.assertEqual(db.execute("SELECT count(*) FROM bookings").fetchone()[0], 0)

    def test_numbered_provider_choice_opens_review_without_payment(self):
        self.send("AC service in Indiranagar Bengaluru tomorrow at 10 AM under INR 1000")
        reply = self.send("option 1")
        self.assertEqual(reply["metadata"]["card_kind"], "review")
        self.assertIn("fictional mock registry", reply["text"])
        self.assertIn("IST", reply["text"])
        self.send("I'm stressed, please just book it now")
        bid = self.store.session("alice")["booking"]
        self.assertEqual(self.store.booking(bid, "alice")["approved"], 0)
        with self.store.connect() as db:
            self.assertEqual(db.execute("SELECT count(*) FROM payments").fetchone()[0], 0)

    def test_negated_emotion_does_not_get_an_assumed_emotional_response(self):
        reply = cards.acknowledge({"text":"Details"}, "I am not stressed")
        self.assertEqual(reply["text"], "Details")
