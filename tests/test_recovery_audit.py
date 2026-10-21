"""Replacement history explains its origins without crossing customers."""
import tempfile
import unittest
from pathlib import Path

from servicesetu.core import Store, Rejected
from tests.test_proofs import Clock


class RecoveryAudit(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.store = Store(Path(self.tmp.name) / "audit.db", Clock())
        self.store.seed()
        self.slot = self.store.provider("p1")["slots"][0]

    def confirm(self, provider, recovery_of=None, owner="alice"):
        quote = self.store.quote(owner, provider, self.slot)
        booking = self.store.hold(owner, quote["id"], recovery_of=recovery_of)
        self.store.approve(owner, booking["id"], quote["id"])
        self.store.begin_payment(owner, booking["id"], "payment:" + booking["id"])
        return self.store.settle(owner, booking["id"])

    def replacement(self):
        original = self.confirm("p1")
        self.store.cancel("alice", original["id"], actor="provider:p1")
        self.store.recovery("alice", original["id"], {
            "service": "ac", "city": "bengaluru", "area": "indiranagar",
            "slot": self.slot, "budget": 100000,
        })
        return original, self.confirm("p2", original["id"])

    def test_replacement_includes_original_cancellation_and_both_quotes(self):
        original, replacement = self.replacement()
        events = self.store.timeline("alice", replacement["id"])
        kinds = [e["kind"] for e in events]
        self.assertIn("provider_cancelled", kinds)
        self.assertIn("recovery_proposed", kinds)
        self.assertEqual(kinds.count("customer_approved"), 2)
        self.assertEqual(kinds.count("booking_confirmed"), 2)
        self.assertEqual({e["entity"] for e in events if e["kind"] == "quote_created"},
                         {original["quote"], replacement["quote"]})
        cancellation = next(e["seq"] for e in events if e["kind"] == "provider_cancelled")
        approval = next(e["seq"] for e in events
                        if e["kind"] == "customer_approved" and e["entity"] == replacement["id"])
        self.assertLess(cancellation, approval)

    def test_multiple_replacements_are_ordered_without_duplicate_events(self):
        original, second = self.replacement()
        self.store.cancel("alice", second["id"], actor="provider:p2")
        third = self.confirm("p1", second["id"])
        events = self.store.timeline("alice", third["id"])
        self.assertEqual([e["entity"] for e in events if e["kind"] == "booking_confirmed"],
                         [original["id"], second["id"], third["id"]])
        sequence = [e["seq"] for e in events]
        self.assertEqual(sequence, sorted(set(sequence)))

    def test_foreign_predecessor_is_never_exposed(self):
        _, replacement = self.replacement()
        foreign = self.confirm("p1", owner="bob")
        # An inconsistent database link must not expose another owner.
        with self.store.tx() as db:
            db.execute("UPDATE bookings SET recovery_of=? WHERE id=?",
                       (foreign["id"], replacement["id"]))
        events = self.store.timeline("alice", replacement["id"])
        self.assertNotIn(foreign["id"], {e["entity"] for e in events})
        self.assertNotIn(foreign["quote"], {e["entity"] for e in events})
        with self.assertRaises(Rejected):
            self.store.timeline("bob", replacement["id"])
