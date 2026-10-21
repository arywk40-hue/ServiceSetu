"""Customer history reflects persisted facts and retains detailed audit access."""
import asyncio
import json
import tempfile
import unittest
from datetime import datetime
from pathlib import Path

from servicesetu.cards import booking_history
from servicesetu.conversation import Conversation
from servicesetu.core import Store
from servicesetu.service import LocalBus, Services
from tests.test_proofs import Clock


class HistoryDisplay(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.store = Store(Path(self.tmp.name) / "history.db", Clock())
        self.store.seed()
        self.slot = self.store.provider("p1")["slots"][0]

    def confirm(self, provider, predecessor=None):
        q = self.store.quote("alice", provider, self.slot)
        b = self.store.hold("alice", q["id"], recovery_of=predecessor)
        self.store.approve("alice", b["id"], q["id"])
        self.store.begin_payment("alice", b["id"], "payment:" + b["id"])
        return self.store.settle("alice", b["id"])

    def test_recovery_displays_names_prices_approval_and_refund(self):
        original = self.confirm("p1")
        self.store.cancel("alice", original["id"], actor="provider:p1")
        replacement = self.confirm("p2", original["id"])
        events = self.store.timeline("alice", replacement["id"])
        before = json.dumps(events, sort_keys=True)
        text = booking_history(events)["text"]
        for expected in ("Booking confirmed with CoolCare AC: INR 699.00",
                         "Provider cancelled the booking with CoolCare AC",
                         "Test payment reversed.", "You approved the exact quote from Breeze AC",
                         "Replacement booking confirmed with Breeze AC: INR 749.00", "IST"):
            self.assertIn(expected, text)
        self.assertLess(text.index("Provider cancelled"), text.index("Replacement booking confirmed"))
        for private_detail in ("digest", "mock-registry://", "payment_started", original["quote"]):
            self.assertNotIn(private_detail, text)
        self.assertEqual(json.dumps(events, sort_keys=True), before)

    def test_pending_refund_is_not_described_as_completed(self):
        original = self.confirm("p1")
        self.store.cancel("alice", original["id"], actor="provider:p1", stripe=True)
        text = booking_history(self.store.timeline("alice", original["id"]))["text"]
        self.assertIn("Refund required; not yet confirmed.", text)
        self.assertNotIn("Test payment reversed.", text)

    def test_unpaid_cancellation_does_not_claim_a_refund(self):
        q = self.store.quote("alice", "p1", self.slot)
        b = self.store.hold("alice", q["id"])
        self.store.cancel("alice", b["id"])
        text = booking_history(self.store.timeline("alice", b["id"]))["text"]
        self.assertIn("You cancelled the booking", text)
        self.assertNotIn("Test payment reversed.", text)

    def test_empty_history_has_clear_message(self):
        self.assertIn("No booking events recorded yet.", booking_history([])["text"])

    def test_current_summary_uses_saved_state_and_separate_appointment(self):
        b = self.confirm("p1")
        cancelled = self.store.cancel("alice", b["id"], actor="provider:p1", stripe=True)
        text = booking_history(self.store.timeline("alice", b["id"]), cancelled)["text"]
        summary = text.split("### Full history")[0]
        self.assertIn("**Status:** Cancelled", summary)
        self.assertIn("**Provider:** CoolCare AC", summary)
        self.assertIn("**Total:** INR 699.00", summary)
        self.assertIn("10:00 AM IST", summary)
        self.assertIn("Refund required; not yet confirmed", summary)

    def test_every_event_gets_a_number_including_unrecognised_events(self):
        b = self.confirm("p1")
        with self.store.tx() as db:
            self.store.event(db, b["id"], "manual_review_requested", reason="Example")
        events = self.store.timeline("alice", b["id"])
        text = booking_history(events, self.store.booking(b["id"], "alice"))["text"]
        for number in range(1, len(events) + 1):
            self.assertEqual(text.count(f"**{number}. "), 1)
        self.assertIn("Manual review requested", text)
        self.assertIn("Hold expires:", text)

    def test_date_groups_and_am_pm_times_keep_event_order(self):
        events = [
            {"entity": "b", "kind": "slot_released", "payload": {},
             "at": datetime.fromisoformat("2026-10-21T23:59:00+05:30").timestamp()},
            {"entity": "b", "kind": "service_completed", "payload": {},
             "at": datetime.fromisoformat("2026-10-22T00:01:00+05:30").timestamp()},
        ]
        text = booking_history(events)["text"]
        self.assertIn("#### 21 October 2026", text)
        self.assertIn("#### 22 October 2026", text)
        self.assertIn("**1. 11:59:00 PM**", text)
        self.assertIn("**2. 12:01:00 AM**", text)

    def test_conversation_keeps_original_audit_as_explicit_option(self):
        b = self.confirm("p1")
        self.store.save_session("alice", {"booking": b["id"]})
        conversation = Conversation(self.store)
        bus = LocalBus(Services(self.store, payment_mode="mock"))
        before = self.store.timeline("alice", b["id"])
        for command in ("show what happened", "audit", "timeline"):
            reply = asyncio.run(conversation.handle("alice", command, bus))
            self.assertTrue(reply["text"].startswith("Booking history"))
            self.assertNotIn('"digest"', reply["text"])
        raw = asyncio.run(conversation.handle("alice", "audit details", bus))
        self.assertTrue(raw["text"].startswith("Immutable timeline"))
        self.assertIn('"digest"', raw["text"])
        self.assertEqual(self.store.timeline("alice", b["id"]), before)
