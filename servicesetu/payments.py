"""Test-only rails. Gateway credentials never enter ASI1 context."""
import os
from .core import Rejected
from .fet_payments import (DENOM,NETWORK,PAYMENT_METHOD,fet_amount,deadline_seconds,mainnet_disabled,
                           native_address,verify_incoming,verify_refund,transaction_hash)


class Payments:
    def __init__(self,store,mode=None,fet_recipient=None):
        self.store=store
        self.mode=mode or os.getenv("PAYMENT_MODE","mock")
        if self.mode not in ("mock","stripe_test","razorpay_test","fet_testnet"): raise Rejected("Real money disabled: use mock, stripe_test, razorpay_test or fet_testnet")
        self.fet_recipient=fet_recipient
        if self.mode=='fet_testnet':
            mainnet_disabled();fet_amount();deadline_seconds()

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
        if self.mode=='fet_testnet':
            mainnet_disabled()
            if not native_address(self.fet_recipient):
                raise Rejected('Dorado FET payment requires the Concierge native fetch1 wallet recipient')
            payment=self.store.begin_fet_payment(owner,bid,"payment:"+bid,recipient=self.fet_recipient,
                deadline_seconds=deadline_seconds())
            invoice=payment['invoice']
            if payment['state']=='paid':return {"booking":self.store.booking(bid,owner),"mode":self.mode}
            if payment['state']!='pending':raise Rejected('This Dorado payment is closed; request a fresh quote')
            if invoice['deadline_at']<=self.store.clock():raise Rejected('FET payment request expired; request a fresh quote')
            return {"booking":self.store.booking(bid,owner),"mode":self.mode,"fet_invoice":invoice}
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

    def commit_fet(self,owner,bid,transaction,funds,recipient,metadata,reference):
        """Verify the commit against its persisted invoice and Dorado transfer."""
        if self.mode!='fet_testnet':raise Rejected('fet_direct commits require PAYMENT_MODE=fet_testnet')
        mainnet_disabled()
        b=self.store.booking(bid,owner)
        with self.store.connect() as db:
            p=db.execute('SELECT * FROM payments WHERE booking=?',(bid,)).fetchone()
        if not p or p['mode']!='fet_testnet' or not p['invoice']:
            raise Rejected('Stored Dorado invoice not found for this booking')
        invoice=__import__('json').loads(p['invoice'])
        if invoice['network']!=NETWORK or invoice['denom']!=DENOM or invoice['recipient']!=self.fet_recipient:
            raise Rejected('Stored invoice network or recipient is invalid')
        customer,session=owner.rsplit(':',1) if ':' in owner else (owner,'')
        if (invoice.get('booking_id')!=bid or invoice.get('customer')!=customer or invoice.get('session')!=session
                or b['quote']!=invoice['quote_id'] or not b['approved']):
            raise Rejected('FET invoice is not bound to the approved quote')
        if reference!=bid or funds.payment_method!=PAYMENT_METHOD or funds.currency!='FET':
            raise Rejected('CommitPayment reference, method or currency does not match the FET invoice')
        amount,atomic_amount=fet_amount(invoice['token_amount'])
        committed_amount,committed_atomic=fet_amount(funds.amount)
        if (amount!=invoice['token_amount'] or committed_amount!=amount or committed_atomic!=atomic_amount
                or str(atomic_amount)!=str(invoice['atomic_amount']) or recipient!=invoice['recipient']):
            raise Rejected('CommitPayment amount or recipient does not match the FET invoice')
        if isinstance(metadata,dict):
            if metadata.get('fet_network') not in (None,NETWORK) or metadata.get('mainnet') not in (None,'false','False'):
                raise Rejected('CommitPayment is not identified as Dorado testnet')
            payer=metadata.get('buyer_fet_wallet') or metadata.get('buyer_fet_address')
        else:payer=None
        if not native_address(payer):raise Rejected('CommitPayment must identify the customer native fetch1 wallet')
        tx_hash=transaction_hash(transaction)
        if p['external']:
            if p['external']==tx_hash and p['state'] in ('paid','refund_required','refunded'):
                return self.store.booking(bid,owner)
            raise Rejected('A different transaction is already bound to this booking')
        with self.store.connect() as db:
            used=db.execute('SELECT booking FROM verified_transfers WHERE tx_hash=?',(tx_hash,)).fetchone()
            if used and used['booking']!=bid:raise Rejected('This transaction was already used for another booking')
            if db.execute('SELECT 1 FROM payments WHERE external=? OR refund_external=?',(tx_hash,tx_hash)).fetchone():
                raise Rejected('This transaction was already used')
        transfer=verify_incoming(tx_hash,sender=payer,recipient=invoice['recipient'],amount_atomic=atomic_amount)
        return self.store.settle(owner,bid,external=tx_hash,payer_wallet=payer,transfer_sender=transfer['sender'],
            transfer_recipient=transfer['recipient'],transfer_amount=transfer['amount'],transfer_denom=transfer['denom'])

    def record_fet_refund(self,owner,bid,refund_transaction):
        """Mark a refund only after verifying a distinct Dorado transfer."""
        if self.mode!='fet_testnet':raise Rejected('FET refund verification requires PAYMENT_MODE=fet_testnet')
        b=self.store.booking(bid,owner)
        with self.store.connect() as db:p=db.execute('SELECT * FROM payments WHERE booking=?',(bid,)).fetchone()
        if not p or p['mode']!='fet_testnet' or not p['invoice'] or not p['payer_wallet']:
            raise Rejected('A verified FET payment and payer wallet are required before refund verification')
        if b['state']!='cancelled' or b['payment_state']!='refund_required':
            raise Rejected('Only a cancelled booking awaiting FET refund can be reconciled')
        invoice=__import__('json').loads(p['invoice'])
        tx_hash=transaction_hash(refund_transaction)
        with self.store.connect() as db:
            if db.execute('SELECT 1 FROM payments WHERE external=? OR refund_external=?',(tx_hash,tx_hash)).fetchone():
                raise Rejected('This transaction was already used')
        transfer=verify_refund(tx_hash,sender=invoice['recipient'],recipient=p['payer_wallet'],
                               amount_atomic=int(invoice['atomic_amount']))
        self.store.refund_done(owner,bid,tx_hash,mode='fet_testnet',transfer=transfer)
        return self.store.booking(bid,owner)

    def refund(self,owner,bid):
        b=self.store.booking(bid,owner)
        if b.get('payment_mode')=='fet_testnet':
            raise Rejected('FET refunds are separate on-chain Dorado transfers; verify the refund transaction with servicesetu.fet_refund')
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
        mode=self.store.booking(bid,owner).get('payment_mode')
        if b["payment_state"]=="refund_required" and mode!='fet_testnet':self._try_refund(owner,bid)
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
