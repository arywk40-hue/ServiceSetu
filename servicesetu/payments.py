"""Test-only rails. Gateway credentials never enter ASI1 context."""
import os
from .core import Rejected


class Payments:
    def __init__(self,store,mode=None):
        self.store=store
        self.mode=mode or os.getenv("PAYMENT_MODE","mock")
        if self.mode not in ("mock","stripe_test","razorpay_test"): raise Rejected("Real money disabled: use mock, stripe_test or razorpay_test")

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
        if self.mode=='razorpay_test':
            from .razorpay_payments import RazorpayTest
            return RazorpayTest(self.store).start(owner,bid)
        payment=self.store.begin_payment(owner,bid,"payment:"+bid,mode=self.mode)
        if self.mode=="mock":
            b=self.store.settle(owner,bid,success=not decline)
            return {"booking":b,"mode":"mock","description":"Simulated payment, no gateway charge"}
        if payment["state"]=="paid":
            return {"booking":self.store.booking(bid,owner),"mode":self.mode}
        if payment["state"] != "pending": raise Rejected("This payment is closed; obtain a fresh quote")
        stripe=self.stripe()
        session=(stripe.checkout.Session.retrieve(payment['external']) if payment['external'] else self._create_checkout(stripe,owner,bid,payment))
        self.store.attach_checkout(owner,bid,session.id)
        if session.livemode:raise Rejected('Live checkout refused')
        if getattr(session,'status',None)=='expired':raise Rejected('Stripe test checkout expired; request a fresh quote')
        return {"mode":self.mode,"booking":self.store.booking(bid,owner),"stripe":{
            "client_secret":session.client_secret,"id":session.id,"checkout_session_id":session.id,
            "publishable_key":os.getenv("STRIPE_PUBLISHABLE_KEY"),"currency":"inr","amount_cents":str(payment["amount"]),"ui_mode":"embedded"}}

    def _create_checkout(self,stripe,owner,bid,payment):
        # Stable idempotency persists across retries and process restarts.
        return stripe.checkout.Session.create(mode="payment",ui_mode="embedded",redirect_on_completion="never",
            payment_method_types=["card"],line_items=[{"price_data":{"currency":"inr","unit_amount":payment["amount"],
                "product_data":{"name":"ServiceSetu fictional service · TEST ONLY"}},"quantity":1}],
            metadata={"booking_id":bid,"owner":owner},client_reference_id=bid,idempotency_key=payment["idem"])

    def commit(self,owner,bid,transaction,currency,amount,recipient,expected_recipient):
        if self.mode!="stripe_test": raise Rejected("Payment Protocol commits require Stripe test mode")
        b=self.store.booking(bid,owner)
        with self.store.connect() as db:
            p=db.execute("SELECT * FROM payments WHERE booking=?",(bid,)).fetchone()
        if not p or p['mode']!='stripe_test' or transaction!=p["external"]: raise Rejected("Checkout is not bound to this booking")
        if currency.upper()!="INR" or amount!=f"{p['amount']/100:.2f}" or recipient!=expected_recipient:
            raise Rejected("Payment Protocol amount, currency or recipient mismatch")
        stripe=self.stripe()
        session=stripe.checkout.Session.retrieve(transaction)
        if (session.livemode or session.payment_status!="paid" or session.amount_total!=p["amount"]
            or session.currency.lower()!="inr" or session.metadata.get("booking_id")!=bid
            or session.metadata.get("owner")!=owner or session.client_reference_id!=bid):
            raise Rejected("Stripe test payment has not passed server-side verification")
        b=self.store.settle(owner,bid,external=transaction)
        if b["payment_state"]=="refund_required": self._try_refund(owner,bid)
        return self.store.booking(bid,owner)

    def refund(self,owner,bid):
        b=self.store.booking(bid,owner)
        if b.get('payment_mode')=='razorpay_test':
            from .razorpay_payments import RazorpayTest
            return RazorpayTest(self.store).refund(owner,bid)
        if b["payment_state"]!="refund_required": return b
        stripe=self.stripe()
        with self.store.connect() as db:
            p=db.execute("SELECT * FROM payments WHERE booking=?",(bid,)).fetchone()
        if not p or p['mode']!='stripe_test' or not p['external']:raise Rejected('A bound Stripe test payment is required for a refund')
        session=stripe.checkout.Session.retrieve(p["external"])
        if session.livemode or session.metadata.get('booking_id')!=bid or session.metadata.get('owner')!=owner or session.amount_total!=p['amount'] or session.currency.lower()!='inr' or session.payment_status!='paid':
            raise Rejected('Refund checkout binding mismatch')
        refund=stripe.Refund.create(payment_intent=session.payment_intent,idempotency_key="refund:"+bid)
        if refund.status!="succeeded": raise Rejected("Test refund pending; human review required")
        self.store.refund_done(owner,bid,refund.id)
        return self.store.booking(bid,owner)

    def _try_refund(self,owner,bid):
        try:self.refund(owner,bid)
        except Exception:self.store.denied(bid,'Test gateway refund requires reconciliation; refund not confirmed','payment')

    def cancel(self,owner,bid,actor="customer"):
        b=self.store.cancel(owner,bid,actor)
        if b["payment_state"]=="refund_required":self._try_refund(owner,bid)
        return self.store.booking(bid,owner)

    def reconcile(self):
        """Recover lost commits and session-create responses using persisted intent."""
        if self.mode=='razorpay_test':
            from .razorpay_payments import RazorpayTest
            return RazorpayTest(self.store).reconcile()
        if self.mode!='stripe_test':return
        s=self.store
        with s.connect() as db:
            rows=db.execute("SELECT b.owner,b.id,b.hold_until,p.* FROM bookings b JOIN payments p ON p.booking=b.id WHERE p.mode='stripe_test' AND p.state IN ('pending','refund_required')").fetchall()
        for row in rows:
            bid=row['booking'];owner=row['owner']
            try:
                if row['state']=='refund_required':self.refund(owner,bid);continue
                stripe=self.stripe()
                if row['external']:
                    session=stripe.checkout.Session.retrieve(row['external'])
                else:
                    # Stripe retains idempotency keys for at least 24 hours.
                    # Beyond that window an unknown result requires operator review.
                    if s.clock()-row['hold_until']>23*3600:raise Rejected('Unknown checkout creation outcome requires human review')
                    session=self._create_checkout(stripe,owner,bid,row)
                    s.attach_checkout(owner,bid,session.id)
                if session.payment_status=='paid':
                    self.commit(owner,bid,session.id,'INR',f"{row['amount']/100:.2f}",'reconciliation','reconciliation')
                else:
                    b=s.booking(bid,owner)
                    if b['hold_until']<=s.clock() or b['state']=='cancelled':
                        if session.status=='open':stripe.checkout.Session.expire(session.id)
                        s.settle(owner,bid,success=False)
            except Exception:s.denied(bid,'Gateway reconciliation retry required; no successful refund assumed','payment')

    def refresh(self,owner,bid):
        b=self.store.booking(bid,owner)
        if b.get('payment_mode')=='razorpay_test':
            from .razorpay_payments import RazorpayTest
            return RazorpayTest(self.store).poll(owner,bid)
        return b
