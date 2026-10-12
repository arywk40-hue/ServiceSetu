"""Gateway boundary proofs use an SDK double, not a real Stripe transaction."""
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from servicesetu.core import Store,Rejected
from servicesetu.payments import Payments
from tests.test_proofs import Clock


class GatewayBoundary(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.clock=Clock();self.store=Store(Path(self.tmp.name)/"payments.db",self.clock);self.store.seed()
        self.owner="customer:session"
        q=self.store.quote(self.owner,"p1",self.store.provider("p1")["slots"][0])
        self.q=q;self.b=self.store.hold(self.owner,q["id"])
        self.adapter=Payments(self.store,mode="stripe_test")
        self.session=SimpleNamespace(id="cs_test_bound",client_secret="synthetic_secret",livemode=False,payment_status="paid",
            amount_total=q["amount"],currency="inr",metadata={"booking_id":self.b["id"],"owner":self.owner},
            client_reference_id=self.b["id"],payment_intent="pi_test",status="complete")
        self.gateway=SimpleNamespace(checkout=SimpleNamespace(Session=SimpleNamespace()),Refund=SimpleNamespace())
        from unittest.mock import Mock
        self.gateway.checkout.Session.create=Mock(return_value=self.session)
        self.gateway.checkout.Session.retrieve=Mock(return_value=self.session)
        self.gateway.Refund.create=Mock(return_value=SimpleNamespace(id="re_test",status="succeeded"))
        self.mock=patch.object(self.adapter,"stripe",return_value=self.gateway);self.mock.start()

    def tearDown(self): self.mock.stop();self.tmp.cleanup()

    def start(self):
        self.store.approve(self.owner,self.b["id"],self.q["id"])
        return self.adapter.start(self.owner,self.b["id"])

    def commit(self,**changes):
        args={"owner":self.owner,"bid":self.b["id"],"transaction":"cs_test_bound","currency":"INR",
              "amount":"699.00","recipient":"concierge","expected_recipient":"concierge"}
        args.update(changes)
        return self.adapter.commit(**args)

    def test_gateway_not_called_before_consent(self):
        with self.assertRaises(Rejected): self.adapter.start(self.owner,self.b["id"])
        self.gateway.checkout.Session.create.assert_not_called()

    def test_embedded_test_checkout_binds_booking(self):
        result=self.start()
        kwargs=self.gateway.checkout.Session.create.call_args.kwargs
        self.assertEqual(kwargs["ui_mode"],"embedded")
        self.assertEqual(kwargs["idempotency_key"],"payment:"+self.b["id"])
        self.assertEqual(kwargs["metadata"],{"booking_id":self.b["id"],"owner":self.owner})
        self.assertEqual(result["stripe"]["checkout_session_id"],"cs_test_bound")
        self.assertEqual(self.commit()["state"],"confirmed")

    def test_foreign_transaction_or_protocol_terms_rejected(self):
        self.start()
        for change in ({"transaction":"cs_test_foreign"},{"currency":"USD"},{"amount":"1.00"},{"recipient":"attacker"}):
            with self.subTest(change=change),self.assertRaises(Rejected): self.commit(**change)
        self.assertEqual(self.store.booking(self.b["id"],self.owner)["state"],"held")

    def test_gateway_identity_amount_and_mode_revalidated(self):
        self.start()
        for key,value in (("livemode",True),("amount_total",1),("currency","usd"),("payment_status","unpaid"),("client_reference_id","another_booking")):
            old=getattr(self.session,key);setattr(self.session,key,value)
            with self.subTest(key=key),self.assertRaises(Rejected): self.commit()
            setattr(self.session,key,old)
        self.session.metadata={"owner":"another_customer","booking_id":self.b["id"]}
        with self.assertRaises(Rejected): self.commit()

    def test_late_gateway_payment_refunded_once(self):
        self.start();self.clock.now+=121
        result=self.commit()
        self.assertEqual(result["state"],"cancelled")
        self.assertEqual(result["payment_state"],"refunded")
        self.commit()
        self.gateway.Refund.create.assert_called_once()
        self.assertEqual(self.gateway.Refund.create.call_args.kwargs["idempotency_key"],"refund:"+self.b["id"])

    def test_gateway_error_preserves_pending_intent(self):
        self.gateway.checkout.Session.create.side_effect=RuntimeError("synthetic gateway unavailable")
        with self.assertRaises(RuntimeError): self.start()
        self.assertEqual(self.store.booking(self.b["id"],self.owner)["payment_state"],"pending")
        self.gateway.checkout.Session.create.side_effect=None
        self.adapter.start(self.owner,self.b["id"])
        with self.store.connect() as db: self.assertEqual(db.execute("SELECT COUNT(*) FROM payments").fetchone()[0],1)

    def test_live_secret_key_is_refused(self):
        self.mock.stop()
        with patch.dict("os.environ",{"STRIPE_SECRET_KEY":"sk_live_synthetic","STRIPE_PUBLISHABLE_KEY":"pk_live_synthetic"}):
            with self.assertRaises(Rejected): self.adapter.stripe()
        self.mock.start()
