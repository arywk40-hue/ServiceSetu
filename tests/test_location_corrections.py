from tests.flows import with_address
"""Location corrections replace stale values without inventing consent."""
import asyncio
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import AsyncMock

from servicesetu.conversation import Conversation
from servicesetu.core import Store
from servicesetu.locations import canonical, suggestion
from servicesetu.reasoning import Reasoner
from servicesetu.service import Services, LocalBus
from tests.test_proofs import Clock


class LocationCorrections(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.clock = Clock()
        self.store = Store(Path(self.tmp.name) / "location.db", self.clock)
        self.store.seed()
        self.slot = self.store.provider("p1")["slots"][0]
        self.job = {"service":"ac", "area":"indiranagar", "city":"bengaluru",
                    "slot":self.slot, "budget":100000}
        self.reasoner = Reasoner()
        self.reasoner.key = None
        self.conversation = Conversation(self.store, self.reasoner)
        self.bus = LocalBus(Services(self.store, payment_mode="mock"))

    def send(self, text):
        return asyncio.run(with_address(self.conversation,"alice",text,self.bus))

    def seed_partial(self, **changes):
        self.store.save_session("alice", {"partial_job":dict(self.job, **changes)})

    def test_unserved_city_is_retained_until_explicitly_corrected(self):
        self.seed_partial(city="Gandhinagar")
        self.reasoner.parse = AsyncMock(return_value={"area":"Indiranagar", "city":None})
        reply = self.send("Indiranagar")
        self.reasoner.parse.assert_not_called()
        self.assertIn("Your location was accepted", reply["text"])
        self.assertEqual(self.store.session("alice")["partial_job"]["city"],'gandhinagar')
        reply = self.send("city: Bengaluru; area: Indiranagar")
        self.assertIn("Provider-confirmed demo quotes", reply["text"])
        state = self.store.session("alice")
        self.assertEqual(state["job"]["city"], "bengaluru")
        self.assertEqual(state["job"]["budget"], 100000)
        self.assertEqual(state["job"]["slot"], self.slot)

    def test_explicit_city_correction_replaces_stale_city(self):
        self.seed_partial(city="Gandhinagar")
        reply = self.send("Actually BANGALORE")
        self.assertIn('your area',reply['text'])
        reply=self.send('area: Indiranagar')
        self.assertIn("Provider-confirmed demo quotes", reply["text"])
        self.assertEqual(self.store.session("alice")["job"]["city"], "bengaluru")

    def test_case_and_spacing_are_normalized_without_typo_confirmation(self):
        reply = self.send(json.dumps(dict(self.job, action="search", service="AC", city=" BANGALORE ",
                                         area=" INDIRA   NAGAR ", budget_rupees=1000)))
        self.assertIn("Provider-confirmed demo quotes", reply["text"])
        normalized = self.store.normalize_job(dict(self.job, city=" BANGALORE ", area="INDIRA NAGAR"))
        self.assertEqual(normalized["city"], "bengaluru")

    def test_raw_typo_still_requires_confirmation_if_model_corrects_it(self):
        self.reasoner.parse = AsyncMock(return_value=self.job)
        reply = self.send("AC in Indranagar, Bangaluru tomorrow 10 AM under INR 1000")
        self.assertIn("Did you mean Indiranagar, Bengaluru", reply["text"])
        with self.store.connect() as db:
            self.assertEqual(db.execute("SELECT count(*) FROM bookings").fetchone()[0], 0)
        reply = self.send("yes")
        self.assertIn("Provider-confirmed demo quotes", reply["text"])
        with self.store.connect() as db:
            self.assertEqual(db.execute("SELECT count(*) FROM payments").fetchone()[0], 0)

    def test_unserved_city_gets_coverage_message_and_can_be_corrected(self):
        self.reasoner.parse = AsyncMock(return_value=dict(self.job, city="Gandhinagar"))
        reply = self.send("AC service in Gandhinagar")
        self.assertIn("Your location was accepted", reply["text"])
        self.assertEqual(self.store.session("alice")["partial_job"]["city"],'gandhinagar')
        reply=self.send('382007')
        self.assertIn('Your location was accepted',reply['text'])
        self.reasoner.parse = AsyncMock(return_value={"city":"Bengaluru"})
        reply = self.send("Bengaluru Indiranagar")
        self.assertIn("Provider-confirmed demo quotes", reply["text"])

    def test_rejecting_suggestion_preserves_other_request_details(self):
        self.seed_partial(city=None)
        self.send("Indranagar")
        reply = self.send("no")
        self.assertIn("correct locality and city", reply["text"])
        state = self.store.session("alice")
        self.assertNotIn("pending_location", state)
        self.assertEqual(state["partial_job"]["budget"], 100000)
        self.assertIsNone(suggestion("Gandhinagar", "area"))
        self.assertIsNone(suggestion("Mangaluru", "city"))

    def test_location_confirmation_does_not_approve_existing_hold(self):
        q = self.store.quote("alice", "p1", self.slot)
        b = self.store.hold("alice", q["id"])
        self.store.save_session("alice", {"booking":b["id"], "partial_job":{"service":"ac"},
                                          "pending_location":{"area":"indiranagar", "city":"bengaluru"}})
        self.send("yes")
        booking = self.store.booking(b["id"], "alice")
        self.assertEqual(booking["state"], "held")
        self.assertEqual(booking["approved"], 0)

    def test_typo_in_form_preserves_natural_time_until_confirmation(self):
        reply = self.send(json.dumps({"action":"search", "service":"AC", "area":"Indranagar",
                                     "slot":"tomorrow at 10 AM", "budget_rupees":1000}))
        self.assertIn("Did you mean", reply["text"])
        reply = self.send("yes")
        self.assertIn("Provider-confirmed demo quotes", reply["text"])
        self.assertEqual(self.store.session("alice")["job"]["slot"], self.slot)

    def test_bare_yes_without_location_question_does_not_supply_location(self):
        self.send("yes")
        self.assertNotIn("pending_location", self.store.session("alice"))
        self.assertEqual(canonical("Gandhinagar", "city"),'gandhinagar')

    def test_negated_supported_area_is_not_an_explicit_location_mention(self):
        from servicesetu.locations import mentions
        self.assertNotIn("area", mentions("not in Indiranagar"))

    def test_area_only_typo_confirms_supported_city_in_the_same_question(self):
        self.seed_partial(city=None)
        reply = self.send("Indranagar")
        self.assertIn("Did you mean Indiranagar, Bengaluru", reply["text"])
        reply = self.send("yes")
        self.assertIn("Provider-confirmed demo quotes", reply["text"])

    def test_location_only_correction_cannot_change_budget_or_appointment(self):
        self.seed_partial(city="Gandhinagar")
        self.reasoner.parse = AsyncMock(return_value=dict(self.job, budget=10000000, slot="2030-01-01T10:00:00+05:30"))
        self.send("Actually Indranagar")
        partial = self.store.session("alice")["partial_job"]
        self.assertEqual(partial["budget"], 100000)
        self.assertEqual(partial["slot"], self.slot)
