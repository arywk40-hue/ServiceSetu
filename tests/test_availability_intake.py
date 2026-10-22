from tests.flows import with_address
"""Normal language intake and explicit, request-bound appointment choices."""
import asyncio
import json
import tempfile
import unittest
from datetime import datetime
from pathlib import Path

from servicesetu.core import Store
from servicesetu.conversation import Conversation
from servicesetu.reasoning import Reasoner, offline_parse
from servicesetu.service import LocalBus, Services
from tests.test_proofs import Clock


class AvailabilityIntake(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.clock = Clock()
        self.store = Store(Path(self.tmp.name) / "availability.db", self.clock)
        self.store.seed()
        self.slot = self.store.provider("p1")["slots"][0]
        self.job = {"service":"ac", "city":"bengaluru", "area":"indiranagar",
                    "slot":self.slot, "budget":100000}
        reasoner = Reasoner()
        reasoner.key = None
        self.conversation = Conversation(self.store, reasoner)
        self.bus = LocalBus(Services(self.store, payment_mode="mock"))

    def send(self, text, owner="alice"):
        return asyncio.run(with_address(self.conversation,owner,text,self.bus))

    def unavailable_request(self, budget=1000):
        date = datetime.fromisoformat(self.slot).timestamp() + 86400
        slot = datetime.fromtimestamp(date, datetime.fromisoformat(self.slot).tzinfo).isoformat()
        return json.dumps(dict(self.job, action="search", slot=slot, budget_rupees=budget))

    def test_midnight_mismatch_offers_real_dates_without_changing_request(self):
        self.clock.now = datetime.fromisoformat(self.slot).timestamp() - 9 * 3600
        reply = self.send("AC service in Indiranagar Bengaluru tomorrow at 10am under INR 1000")
        self.assertEqual(reply["metadata"]["card_kind"], "carousel")
        state = self.store.session("alice")
        self.assertNotEqual(state["job"]["slot"], self.slot)
        self.assertEqual(state["availability_options"][0]["slot"], self.slot)
        self.assertIn("Nothing has been reserved or paid", reply["text"])
        with self.store.connect() as db:
            self.assertEqual(db.execute("SELECT count(*) FROM quotes").fetchone()[0], 0)
            self.assertEqual(db.execute("SELECT count(*) FROM bookings WHERE state='held'").fetchone()[0], 0)
            self.assertEqual(db.execute("SELECT count(*) FROM payments").fetchone()[0], 0)
        selection = json.loads(reply["metadata"]["card_payload"])["items"][0]["primary_cta"]["selection"]
        providers = self.send(json.dumps(selection))
        self.assertIn("Provider-confirmed demo quotes", providers["text"])
        state = self.store.session("alice")
        self.assertEqual(state["job"]["slot"], self.slot)
        self.assertEqual(state["job"]["budget"], 100000)

    def test_simple_numbered_reply_selects_the_current_option(self):
        self.send(self.unavailable_request())
        reply = self.send("option 1")
        self.assertIn("Provider-confirmed demo quotes", reply["text"])
        self.assertEqual(self.store.session("alice")["job"]["slot"], self.slot)

    def test_follow_up_only_asks_for_missing_details(self):
        reply = self.send("My AC is not cooling in Indiranagar Bengaluru tomorrow")
        self.assertIn("preferred time", reply["text"])
        self.assertIn("maximum budget", reply["text"])
        self.assertNotIn("- your area", reply["text"])
        reply = self.send("10 AM")
        self.assertIn("- your maximum budget", reply["text"])
        self.assertNotIn("- your preferred day", reply["text"])
        reply = self.send("under INR 1000")
        self.assertIn("Provider-confirmed demo quotes", reply["text"])

    def test_vague_time_is_not_assumed_and_today_is_supported(self):
        vague = offline_parse("AC tomorrow morning", self.clock())
        self.assertIsNone(vague["slot"])
        self.clock.now = datetime.fromisoformat(self.slot).timestamp() - 9 * 3600
        precise = offline_parse("today at 10 AM", self.clock())
        self.assertEqual(precise["slot"], self.slot)

    def test_common_budget_formatting_is_understood(self):
        parsed = offline_parse("AC tomorrow at 10 AM, my budget is INR 1,000", self.clock())
        self.assertEqual(parsed["budget"], 100000)

    def test_suggestions_exclude_over_budget_and_past_slots(self):
        self.assertEqual(self.store.available_slots(dict(self.job, budget=10000)), [])
        self.clock.now = datetime.fromisoformat(self.slot).timestamp() + 3600
        requested = dict(self.job, slot=self.store.provider("p1")["slots"][1])
        self.assertEqual(self.store.available_slots(requested), [])

    def test_stale_cards_are_rejected_after_a_new_request(self):
        reply = self.send(self.unavailable_request())
        stale = json.loads(reply["metadata"]["card_payload"])["items"][0]["primary_cta"]["selection"]
        self.send(self.unavailable_request(budget=900))
        denied = self.send(json.dumps(stale))
        self.assertIn("no longer current", denied["text"])
        self.assertEqual(self.store.session("alice")["job"]["budget"], 90000)

    def test_options_cannot_cross_conversations(self):
        reply = self.send(self.unavailable_request())
        choice = json.loads(reply["metadata"]["card_payload"])["items"][0]["primary_cta"]["selection"]
        denied = self.send(json.dumps(choice), owner="bob")
        self.assertIn("no longer current", denied["text"])

    def test_changed_availability_is_rechecked_before_quotes(self):
        self.send(self.unavailable_request())
        for provider in ("p1", "p2"):
            q = self.store.quote("other", provider, self.slot)
            self.store.hold("other", q["id"])
        reply = self.send("option 1")
        self.assertNotIn("Provider-confirmed demo quotes", reply["text"])
        self.assertTrue(self.store.session("alice")["availability_options"])
        self.assertEqual(self.store.session("alice")["quotes"], [])

    def test_recovery_does_not_offer_a_different_appointment(self):
        job = dict(self.job, budget=70000)
        self.send(json.dumps(dict(job, action="search", budget_rupees=700)))
        qid = self.store.session("alice")["quotes"][0]
        review = self.send("select " + qid)
        approval = json.loads(review["metadata"]["card_payload"])["approve_cta"]["selection"]
        self.send(json.dumps(approval))
        bid = self.store.session("alice")["booking"]
        self.store.cancel("alice", bid, actor="provider:p1")
        reply = self.send("recover")
        self.assertIn("original appointment and budget", reply["text"])
        self.assertNotIn("metadata", reply)
        self.assertNotIn("availability_options", self.store.session("alice"))

    def test_partial_new_request_invalidates_old_appointment_options(self):
        reply = self.send(self.unavailable_request())
        stale = json.loads(reply["metadata"]["card_payload"])["items"][0]["primary_cta"]["selection"]
        self.send("I need plumbing")
        denied = self.send(json.dumps(stale))
        self.assertIn("no longer current", denied["text"])

    def test_form_accepts_normal_day_and_time_without_iso_timestamp(self):
        reply = self.send(json.dumps({"action":"search", "service":"ac", "city":"Bengaluru", "area":"Indiranagar",
                                     "slot":"tomorrow at 10 AM", "budget_rupees":1000}))
        self.assertIn("Provider-confirmed demo quotes", reply["text"])
        self.assertEqual(self.store.session("alice")["job"]["slot"], self.slot)
        self.assertNotIn(self.slot, reply["text"])

    def test_vague_form_time_keeps_known_fields_for_follow_up(self):
        reply = self.send(json.dumps({"action":"search", "service":"ac", "city":"Bengaluru", "area":"Indiranagar",
                                     "slot":"tomorrow morning", "budget_rupees":1000}))
        self.assertIn("preferred time", reply["text"])
        self.assertNotIn("- your maximum budget", reply["text"])
        reply = self.send("10 AM")
        self.assertIn("Provider-confirmed demo quotes", reply["text"])
