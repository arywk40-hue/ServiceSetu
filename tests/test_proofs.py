from tests.flows import with_address
import asyncio
import json
import sqlite3
import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from servicesetu.core import Store,Rejected,encode
from servicesetu.service import Services,LocalBus
from servicesetu.conversation import Conversation,selection
from servicesetu.reasoning import Reasoner
from servicesetu.payments import Payments


class Clock:
    def __init__(self): self.now=1791849600.0
    def __call__(self): return self.now


class Proofs(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.clock=Clock()
        self.s=Store(Path(self.temp.name)/"proof.db",self.clock)
        self.s.seed()
        self.slot=self.s.provider("p1")["slots"][0]
        self.job={"service":"ac","city":"bengaluru","area":"indiranagar","slot":self.slot,"budget":100000}

    def tearDown(self): self.temp.cleanup()

    def held(self,owner="alice",provider="p1"):
        q=self.s.quote(owner,provider,self.slot)
        b=self.s.hold(owner,q["id"])
        return q,b

    def paid(self,owner="alice",provider="p1"):
        q,b=self.held(owner,provider)
        self.s.approve(owner,b["id"],q["id"])
        self.s.begin_payment(owner,b["id"],"key:"+b["id"])
        return q,self.s.settle(owner,b["id"])

    def test_01_expired_hold_cannot_confirm(self):
        q,b=self.held()
        self.s.approve("alice",b["id"],q["id"])
        self.s.begin_payment("alice",b["id"],"stale")
        self.clock.now+=121
        result=self.s.settle("alice",b["id"])
        self.assertEqual(result["state"],"cancelled")
        self.assertEqual(result["payment_state"],"voided")

    def test_02_simultaneous_customers_one_winner(self):
        quotes=[self.s.quote(name,"p1",self.slot) for name in ("alice","bob")]
        def attempt(q):
            try:
                b=self.s.hold(q["owner"],q["id"])
                self.s.approve(q["owner"],b["id"],q["id"])
                self.s.begin_payment(q["owner"],b["id"],b["id"])
                return self.s.settle(q["owner"],b["id"])["state"]
            except Rejected: return "rejected"
        with ThreadPoolExecutor(2) as pool: outcomes=list(pool.map(attempt,quotes))
        self.assertCountEqual(outcomes,["confirmed","rejected"])

    def test_03_quote_change_requires_new_consent(self):
        q,b=self.held()
        self.s.approve("alice",b["id"],q["id"])
        p=self.s.provider("p1");p["amount"]+=10000
        with self.s.tx() as db: db.execute("UPDATE providers SET payload=? WHERE id='p1'",(encode(p),))
        new=self.s.quote("alice","p1",self.slot,previous=q["id"])
        self.assertEqual(new["version"],2)
        self.assertEqual(self.s.get_quote(q["id"],"alice")["amount"],69900)
        with self.assertRaises(Rejected): self.s.approve("alice",b["id"],new["id"])

    def test_04_no_payment_without_approval(self):
        _,b=self.held()
        with self.assertRaises(Rejected): self.s.begin_payment("alice",b["id"],"no-consent")
        with self.s.connect() as db: self.assertEqual(db.execute("SELECT COUNT(*) FROM payments").fetchone()[0],0)

    def test_05_duplicate_retry_single_payment(self):
        q,b=self.held();self.s.approve("alice",b["id"],q["id"])
        first=self.s.begin_payment("alice",b["id"],"same")
        self.s.settle("alice",b["id"])
        again=self.s.begin_payment("alice",b["id"],"same")
        self.assertEqual(first["id"],again["id"])
        self.s.settle("alice",b["id"])
        with self.s.connect() as db: self.assertEqual(db.execute("SELECT COUNT(*) FROM payments").fetchone()[0],1)
        self.assertEqual(sum(e["kind"]=="booking_confirmed" for e in self.s.timeline("alice",b["id"])),1)

    def test_06_payment_decline_releases_slot(self):
        q,b=self.held();self.s.approve("alice",b["id"],q["id"])
        self.s.begin_payment("alice",b["id"],"decline")
        result=self.s.settle("alice",b["id"],success=False)
        self.assertEqual(result["payment_state"],"declined")
        self.assertEqual(self.held("bob")[1]["state"],"held")

    def test_07_provider_decline_compensates(self):
        q,b=self.held();self.s.approve("alice",b["id"],q["id"])
        self.s.begin_payment("alice",b["id"],"provider-fail")
        result=self.s.settle("alice",b["id"],provider_confirm=False)
        self.assertEqual(result["payment_state"],"voided")
        self.assertEqual(self.held("bob")[1]["state"],"held")

    def test_08_honest_trust_labels(self):
        choices,excluded=self.s.match(self.job)
        self.assertEqual({p["trust"]["status"] for p in choices},{"verified","provider_supplied"})
        self.assertIn("p3",[p["provider"] for p in excluded])

    def test_09_expiry_checked_at_appointment(self):
        p=self.s.provider("p1");p["credential"]["expires"]="2026-10-13"
        with self.s.tx() as db: db.execute("UPDATE providers SET payload=? WHERE id='p1'",(encode(p),))
        choices,_=self.s.match(self.job)
        self.assertNotIn("p1",[p["id"] for p in choices])

    def test_10_recovery_within_limits_requires_review(self):
        _,b=self.paid()
        self.s.cancel("alice",b["id"],actor="provider:p1")
        job=dict(self.job,budget=70000)
        choices,_=self.s.recovery("alice",b["id"],job)
        self.assertEqual(choices,[])
        choices,_=self.s.recovery("alice",b["id"],self.job)
        self.assertEqual([p["id"] for p in choices],["p2"])
        new=self.s.quote("alice","p2",self.slot)
        replacement=self.s.hold("alice",new["id"],b["id"])
        with self.assertRaises(Rejected): self.s.begin_payment("alice",replacement["id"],"replacement")

    def test_11_audit_reconstructs_snapshot_and_consequences(self):
        q,b=self.paid()
        timeline=self.s.timeline("alice",b["id"])
        kinds=[e["kind"] for e in timeline]
        for kind in ("quote_created","slot_held","customer_approved","payment_started","booking_confirmed"):
            self.assertIn(kind,kinds)
        quote=next(e["payload"]["quote"] for e in timeline if e["kind"]=="quote_created")
        self.assertEqual(quote,q)
        with self.s.connect() as db:
            with self.assertRaises(sqlite3.IntegrityError): db.execute("UPDATE events SET kind='tampered'")
            with self.assertRaises(sqlite3.IntegrityError): db.execute("UPDATE quotes SET amount=1")

    def test_12_restricted_actions_route_to_review(self):
        service=Services(self.s)
        for action in ("refund","payout","verification_override"):
            with self.assertRaises(Rejected): service.execute("payment",action,"alice",{})

    def test_13_conversation_isolation(self):
        q,b=self.held()
        with self.assertRaises(Rejected): self.s.get_quote(q["id"],"bob")
        with self.assertRaises(Rejected): self.s.approve("bob",b["id"],q["id"])
        with self.assertRaises(Rejected): self.s.timeline("alice:new-session",b["id"])

    def test_14_late_gateway_success_needs_refund(self):
        q,b=self.held();self.s.approve("alice",b["id"],q["id"])
        self.s.begin_payment("alice",b["id"],"late")
        self.s.attach_checkout("alice",b["id"],"cs_test_bound")
        self.clock.now+=121
        result=self.s.settle("alice",b["id"],external="cs_test_bound")
        self.assertEqual(result["state"],"cancelled")
        self.assertEqual(result["payment_state"],"refund_required")

    def test_15_out_of_scope_and_budget(self):
        with self.assertRaises(Rejected): self.s.match(dict(self.job,service="surgery"))
        self.assertEqual(self.s.match(dict(self.job,area="mumbai"))[0],[])
        choices,_=self.s.match(dict(self.job,budget=10000))
        self.assertEqual(choices,[])

    def test_16_conversation_approval_and_recovery(self):
        async def scenario():
            reasoner=Reasoner();reasoner.key=None
            conv=Conversation(self.s,reasoner);bus=LocalBus(Services(self.s))
            reply=await with_address(conv,"alice:chat1",json.dumps(dict(self.job,action="search",budget_rupees=1000)),bus)
            self.assertEqual(reply["metadata"]["card_kind"],"carousel")
            state=self.s.session("alice:chat1")
            review=await with_address(conv,"alice:chat1","select "+state["quotes"][0],bus)
            self.assertEqual(review["metadata"]["card_kind"],"review")
            payload=json.loads(review["metadata"]["card_payload"])
            denied=await with_address(conv,"alice:chat1","please pay now",bus)
            self.assertNotIn("confirmed",denied["text"])
            approved=await with_address(conv,"alice:chat1",json.dumps(payload["approve_cta"]["selection"]),bus)
            self.assertIn("confirmed",approved["text"])
            state=self.s.session("alice:chat1")
            self.s.cancel("alice:chat1",state["booking"],actor="provider:p1")
            recovery=await with_address(conv,"alice:chat1","recover",bus)
            self.assertIn("replacement needs approval",recovery["text"])
            self.assertIn("provider:p2",[call["role"] for call in bus.calls])
        asyncio.run(scenario())

    def test_17_prose_approval_negation_is_rejected(self):
        text="approve b_"+"a"*16+" q_"+"b"*16+" at_"+"c"*32
        self.assertEqual(selection(text)["action"],"approve")
        self.assertEqual(selection("do not "+text),{})
        self.assertEqual(selection("if the user approved "+text),{})

    def test_18_live_payment_mode_refused(self):
        with self.assertRaises(Rejected): Payments(self.s,mode="stripe_live")

    def test_19_expired_quote_offers_fresh_alternatives(self):
        q,_=self.held();self.clock.now+=301
        with self.assertRaises(Rejected): self.s.hold("alice",q["id"])
        self.assertTrue(self.s.match(self.job)[0])

    def test_20_provider_reports_actual_slot_capacity(self):
        self.held()
        choices,excluded=self.s.match(self.job)
        self.assertNotIn("p1",[p["id"] for p in choices])
        self.assertIn("Slot already reserved",[p["reason"] for p in excluded])
        with self.assertRaises(Rejected): self.s.quote("bob","p1",self.slot)
        self.clock.now+=121
        choices,_=self.s.match(self.job)
        self.assertIn("p1",[p["id"] for p in choices])


if __name__=="__main__": unittest.main(verbosity=2)
