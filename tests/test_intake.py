"""Customer lifecycle and card interaction proofs independent of live accounts."""
import asyncio
import json
import tempfile
import sqlite3
from contextlib import closing
import unittest
from datetime import datetime,timezone
from pathlib import Path
from servicesetu.core import Store,Rejected,SCHEMA,encode
from servicesetu.conversation import Conversation,selection,strip_recipient
from servicesetu.service import Services,LocalBus
from servicesetu.reasoning import Reasoner
from tests.test_proofs import Clock


class Intake(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.clock=Clock()
        self.store=Store(Path(self.tmp.name)/"intake.db",self.clock);self.store.seed()
        self.slot=self.store.provider("p1")["slots"][0]
        self.job={"service":"ac","city":"bengaluru","area":"indiranagar","slot":self.slot,"budget":100000}

    def tearDown(self): self.tmp.cleanup()

    def test_requested_held_confirmed_completed_lifecycle(self):
        intent=self.store.request("alice",self.job)
        self.assertEqual(intent["state"],"requested")
        self.assertTrue(self.store.slot_free("p1",self.slot))
        with self.assertRaises(Rejected): self.store.begin_payment("alice",intent["id"],"premature")
        q=self.store.quote("alice","p1",self.slot)
        held=self.store.hold("alice",q["id"],request_id=intent["id"])
        self.assertEqual(held["id"],intent["id"])
        self.store.approve("alice",held["id"],q["id"])
        self.store.begin_payment("alice",held["id"],"payment")
        self.assertEqual(self.store.settle("alice",held["id"])["state"],"confirmed")
        self.store.complete("alice",held["id"])
        self.assertEqual(self.store.booking(held["id"],"alice")["state"],"completed")
        history=self.store.timeline("alice",held["id"])
        self.assertEqual(next(e for e in history if e["kind"]=="booking_requested")["payload"]["job"],self.job)

    def test_equivalent_timezone_slots_normalize(self):
        utc=datetime.fromisoformat(self.slot).astimezone(timezone.utc).isoformat()
        choices,_=self.store.match(dict(self.job,slot=utc))
        self.assertTrue(choices)
        self.assertEqual(self.store.normalize_job(dict(self.job,slot=utc))["slot"],self.slot)

    def test_malformed_model_fields_are_rejected(self):
        for change in ({"city":None},{"area":[]},{"budget":1.5},{"budget":True},{"slot":"invalid"}):
            with self.subTest(change=change),self.assertRaises(Rejected): self.store.normalize_job(dict(self.job,**change))

    def test_planner_form_selection(self):
        text=f"The user submitted action search with service ac, area Indiranagar, slot {self.slot}, budget_rupees 1000."
        self.assertEqual(selection(text),{"action":"search","service":"ac","area":"indiranagar","slot":self.slot,"budget_rupees":"1000"})

    def test_direct_card_routing_preserves_approval_binding(self):
        async def scenario():
            reasoner=Reasoner();reasoner.key=None
            conv=Conversation(self.store,reasoner);bus=LocalBus(Services(self.store,payment_mode="mock"))
            owner="alice:direct-chat";address="agent1demo_concierge"
            search=json.dumps(dict(self.job,action="search",budget_rupees=1000))
            await conv.handle(owner,"@servicesetu "+search,bus)
            qid=self.store.session(owner)["quotes"][0]
            routed="@"+address+" "+json.dumps({"selection":{"action":"select","quote_id":qid}})
            review=await conv.handle(owner,strip_recipient(routed,address),bus)
            self.assertEqual(review["metadata"]["card_kind"],"review")
            approval=json.loads(review["metadata"]["card_payload"])["approve_cta"]["selection"]
            wrong=dict(approval,approval_token="at_"+"0"*32)
            denied=await conv.handle(owner,"@servicesetu "+json.dumps({"selection":wrong}),bus)
            self.assertIn("Approval must match",denied["text"])
            self.assertEqual(self.store.booking(approval["booking_id"],owner)["state"],"held")
            result=await conv.handle(owner,"@servicesetu "+json.dumps({"selection":approval}),bus)
            self.assertIn(": confirmed.",result["text"])
            with self.store.connect() as db:
                self.assertEqual(db.execute("SELECT count(*) FROM payments").fetchone()[0],1)
        asyncio.run(scenario())

    def test_only_concierge_recipient_is_removed(self):
        raw='@someone_else {"action":"approve"}'
        self.assertEqual(strip_recipient(raw,"agent1demo"),raw)
        self.assertEqual(selection('@servicesetu do not approve b_'+'1'*16+' q_'+'2'*16+' at_'+'3'*32),{})

    def test_old_reject_card_cannot_cancel_current_hold(self):
        async def scenario():
            reasoner=Reasoner();reasoner.key=None
            conv=Conversation(self.store,reasoner);bus=LocalBus(Services(self.store,payment_mode="mock"))
            owner="alice:chat"
            await conv.handle(owner,json.dumps(dict(self.job,action="search",budget_rupees=1000)),bus)
            quotes=self.store.session(owner)["quotes"]
            old=await conv.handle(owner,"select "+quotes[0],bus)
            old_reject=json.loads(old["metadata"]["card_payload"])["reject_cta"]["selection"]
            current=await conv.handle(owner,"select "+quotes[1],bus)
            bid=self.store.session(owner)["booking"]
            reply=await conv.handle(owner,json.dumps(old_reject),bus)
            self.assertIn("old card cannot cancel",reply["text"])
            self.assertEqual(self.store.booking(bid,owner)["state"],"held")
            approve=json.loads(current["metadata"]["card_payload"])["approve_cta"]["selection"]
            await conv.handle(owner,json.dumps(approve),bus)
            await conv.handle(owner,"reject",bus)
            self.assertEqual(self.store.booking(bid,owner)["state"],"confirmed")
        asyncio.run(scenario())

    def test_unknown_request_does_not_reuse_old_job(self):
        async def scenario():
            reasoner=Reasoner();reasoner.key=None
            conv=Conversation(self.store,reasoner);bus=LocalBus(Services(self.store,payment_mode="mock"))
            await conv.handle("alice:chat","AC service in Indiranagar Bengaluru tomorrow 10am under INR 1000",bus)
            intent=self.store.session("alice:chat")["intent"]
            reply=await conv.handle("alice:chat","I need surgery in Mumbai",bus)
            self.assertIn("supports AC servicing and plumbing only",reply["text"])
            self.assertEqual(self.store.session("alice:chat")["intent"],intent)
        asyncio.run(scenario())

    def test_existing_booking_database_migrates_without_losing_evidence(self):
        path=Path(self.tmp.name)/"legacy.db"
        old=SCHEMA.replace("'requested',","").replace("quote TEXT REFERENCES","quote TEXT NOT NULL REFERENCES").replace("provider TEXT, slot TEXT","provider TEXT NOT NULL, slot TEXT NOT NULL")
        with closing(sqlite3.connect(path)) as db, db:
            db.executescript(old)
            db.execute("INSERT INTO quotes VALUES(?,?,?,?,?,?,?,?,?,?)",("q_legacy","p1",self.slot,"alice",1,69900,self.clock()+300,encode({"snapshot":"legacy accepted scope"}),"legacy-digest",None))
            db.execute("INSERT INTO bookings(id,owner,quote,provider,slot,state,hold_until,approved,payment_state) VALUES(?,?,?,?,?,'confirmed',?,1,'paid')",("b_legacy","alice","q_legacy","p1",self.slot,self.clock()+120))
            db.execute("INSERT INTO payments VALUES(?,?,?,?,?,?)",("pay_legacy","b_legacy","idem_legacy",69900,"paid","cs_test_legacy"))
            db.execute("INSERT INTO events(at,entity,kind,actor,payload) VALUES(?,?,?,?,?)",(self.clock(),"b_legacy","booking_confirmed","alice","{}"))
        migrated=Store(path,self.clock);migrated.seed()
        self.assertEqual(migrated.booking("b_legacy","alice")["payment_state"],"paid")
        self.assertEqual(migrated.get_quote("q_legacy","alice"),{"snapshot":"legacy accepted scope"})
        with migrated.connect() as db:
            self.assertEqual(db.execute("SELECT external FROM payments").fetchone()[0],"cs_test_legacy")
            self.assertEqual(db.execute("PRAGMA foreign_key_check").fetchall(),[])
        self.assertEqual(migrated.request("bob",self.job)["state"],"requested")
