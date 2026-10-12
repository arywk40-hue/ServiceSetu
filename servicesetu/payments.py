"""Test-only rails. Gateway credentials never enter ASI1 context."""
import os
from .core import Rejected


class Payments:
    def __init__(self,store,mode=None):
        self.store=store
        self.mode=mode or os.getenv("PAYMENT_MODE","mock")
        if self.mode not in ("mock","stripe_test"): raise Rejected("Real money disabled: use mock or stripe_test")

    def stripe(self):
        secret=os.getenv("STRIPE_SECRET_KEY","")
        public=os.getenv("STRIPE_PUBLISHABLE_KEY","")
        if not secret.startswith("sk_test_") or not public.startswith("pk_test_"):
            raise Rejected("Stripe requires sk_test_ and pk_test_ keys; live keys are refused")
        import stripe
        stripe.api_key=secret
        stripe.max_network_retries=2
        return stripe

    def start(self,owner,bid,decline=False):
        payment=self.store.begin_payment(owner,bid,"payment:"+bid)
        if self.mode=="mock":
            b=self.store.settle(owner,bid,success=not decline)
            return {"booking":b,"mode":"mock","description":"Simulated payment, no gateway charge"}
        if payment["state"]=="paid":
            return {"booking":self.store.booking(bid,owner),"mode":self.mode}
        if payment["state"] != "pending": raise Rejected("This payment is closed; obtain a fresh quote")
        stripe=self.stripe()
        # Stable idempotency persists across retries and process restarts.
        session=stripe.checkout.Session.create(mode="payment",ui_mode="embedded",redirect_on_completion="if_required",
            return_url=os.getenv("STRIPE_RETURN_URL","https://asi1.ai")+"?session_id={CHECKOUT_SESSION_ID}",
            payment_method_types=["card"],line_items=[{"price_data":{"currency":"inr","unit_amount":payment["amount"],
                "product_data":{"name":"ServiceSetu fictional service · TEST ONLY"}},"quantity":1}],
            metadata={"booking_id":bid,"owner":owner},client_reference_id=bid,idempotency_key=payment["idem"])
        self.store.attach_checkout(owner,bid,session.id)
        return {"mode":self.mode,"booking":self.store.booking(bid,owner),"stripe":{
            "client_secret":session.client_secret,"id":session.id,"checkout_session_id":session.id,
            "publishable_key":os.getenv("STRIPE_PUBLISHABLE_KEY"),"currency":"inr","amount_cents":str(payment["amount"]),"ui_mode":"embedded"}}

    def commit(self,owner,bid,transaction,currency,amount,recipient,expected_recipient):
        if self.mode!="stripe_test": raise Rejected("Payment Protocol commits require Stripe test mode")
        b=self.store.booking(bid,owner)
        with self.store.connect() as db:
            p=db.execute("SELECT * FROM payments WHERE booking=?",(bid,)).fetchone()
        if not p or transaction!=p["external"]: raise Rejected("Checkout is not bound to this booking")
        if currency.upper()!="INR" or amount!=f"{p['amount']/100:.2f}" or recipient!=expected_recipient:
            raise Rejected("Payment Protocol amount, currency or recipient mismatch")
        stripe=self.stripe()
        session=stripe.checkout.Session.retrieve(transaction)
        if (session.livemode or session.payment_status!="paid" or session.amount_total!=p["amount"]
            or session.currency.lower()!="inr" or session.metadata.get("booking_id")!=bid
            or session.metadata.get("owner")!=owner or session.client_reference_id!=bid):
            raise Rejected("Stripe test payment has not passed server-side verification")
        b=self.store.settle(owner,bid,external=transaction)
        if b["payment_state"]=="refund_required": self.refund(owner,bid)
        return self.store.booking(bid,owner)

    def refund(self,owner,bid):
        b=self.store.booking(bid,owner)
        if b["payment_state"]!="refund_required": return b
        stripe=self.stripe()
        with self.store.connect() as db:
            p=db.execute("SELECT * FROM payments WHERE booking=?",(bid,)).fetchone()
        session=stripe.checkout.Session.retrieve(p["external"])
        refund=stripe.Refund.create(payment_intent=session.payment_intent,idempotency_key="refund:"+bid)
        if refund.status!="succeeded": raise Rejected("Test refund pending; human review required")
        self.store.refund_done(owner,bid,refund.id)
        return self.store.booking(bid,owner)

    def cancel(self,owner,bid,actor="customer"):
        b=self.store.cancel(owner,bid,actor,stripe=self.mode=="stripe_test")
        if self.mode=="stripe_test" and b["payment_state"]=="refund_required": b=self.refund(owner,bid)
        return b
