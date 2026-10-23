"""Razorpay TEST Payment Links. Server polling owns payment confirmation."""
import base64
import hashlib
import json
import os
import re
from urllib.error import HTTPError,URLError
from urllib.parse import urlencode,urlsplit
from urllib.request import Request,build_opener,HTTPRedirectHandler
from .core import Rejected


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self,*args,**kwargs):return None


class RazorpayAPI:
    def __init__(self):
        key=os.getenv('RAZORPAY_KEY_ID','');secret=os.getenv('RAZORPAY_KEY_SECRET','')
        if not key.startswith('rzp_test_') or not secret:raise Rejected('Configure Razorpay rzp_test_ credentials privately; live keys are refused')
        self.authorization='Basic '+base64.b64encode((key+':'+secret).encode()).decode()

    def request(self,method,path,data=None,idempotency=None):
        if not path.startswith('/') or '..' in path:raise Rejected('Invalid gateway path')
        headers={'Authorization':self.authorization,'Content-Type':'application/json','Accept':'application/json'}
        if idempotency:headers['X-Refund-Idempotency']=idempotency
        req=Request('https://api.razorpay.com/v1'+path,data=json.dumps(data).encode() if data is not None else None,headers=headers,method=method)
        try:
            with build_opener(NoRedirect()).open(req,timeout=12) as reply:return json.loads(reply.read(2_000_000))
        except (HTTPError,URLError,TimeoutError,ValueError,OSError):raise Rejected('Razorpay test request failed or its result is unknown; check payment status before retrying') from None


class RazorpayTest:
    def __init__(self,store,api=None):self.store=store;self._api=api
    @property
    def api(self):
        if self._api is None:self._api=RazorpayAPI()
        return self._api

    def payment(self,owner,bid):
        self.store.booking(bid,owner)
        with self.store.connect() as db:row=db.execute('SELECT * FROM payments WHERE booking=?',(bid,)).fetchone()
        if not row or row['mode']!='razorpay_test':raise Rejected('Razorpay test payment unavailable in this conversation')
        return dict(row)

    def claim(self,bid,operation):
        with self.store.tx() as db:return bool(db.execute('INSERT OR IGNORE INTO gateway_operations(booking,operation) VALUES(?,?)',(bid,operation)).rowcount)

    def operation(self,bid,operation):
        with self.store.connect() as db:return db.execute('SELECT external FROM gateway_operations WHERE booking=? AND operation=?',(bid,operation)).fetchone()

    def bind_operation(self,bid,operation,external):
        with self.store.tx() as db:
            row=db.execute('SELECT external FROM gateway_operations WHERE booking=? AND operation=?',(bid,operation)).fetchone()
            if row and row['external'] and row['external']!=external:raise Rejected('Gateway operation binding conflict')
            db.execute('INSERT INTO gateway_operations VALUES(?,?,?) ON CONFLICT(booking,operation) DO UPDATE SET external=excluded.external',(bid,operation,external))
            if operation=='razorpay_capture' and not (row and row['external']):self.store.event(db,bid,'razorpay_test_capture_verified','payment',payment=external)

    def validate_link(self,link,owner,bid,payment):
        notes=link.get('notes') or {}
        if (not re.fullmatch(r'plink_[A-Za-z0-9]+',str(link.get('id',''))) or link.get('reference_id')!=bid
            or link.get('amount')!=payment['amount'] or link.get('currency')!='INR' or link.get('accept_partial') is not False
            or notes.get('booking_id')!=bid or notes.get('owner_hash')!=hashlib.sha256(owner.encode()).hexdigest()
            or notes.get('quote_id')!=self.store.booking(bid,owner)['quote']):raise Rejected('Razorpay checkout binding mismatch')
        if payment['external'] and link['id']!=payment['external']:raise Rejected('Razorpay checkout reference mismatch')

    def find_link(self,owner,bid,payment,create=False):
        if payment['external']:link=self.api.request('GET','/payment_links/'+payment['external'])
        else:
            result=self.api.request('GET','/payment_links/?'+urlencode({'reference_id':bid}))
            links=[x for x in result.get('payment_links',[]) if x.get('reference_id')==bid]
            if len(links)>1:raise Rejected('Multiple gateway references require operator review')
            link=links[0] if links else None
            if link is None:
                if not create:return None
                if not self.claim(bid,'razorpay_link_create'):raise Rejected('Checkout creation outcome is pending; check payment status or request operator review')
                b=self.store.booking(bid,owner)
                link=self.api.request('POST','/payment_links/',dict(amount=payment['amount'],currency='INR',accept_partial=False,
                    reference_id=bid,expire_by=int(b['hold_until']),description='ServiceSetu TEST booking only',
                    notify=dict(sms=False,email=False),reminder_enable=False,
                    notes=dict(booking_id=bid,quote_id=b['quote'],owner_hash=hashlib.sha256(owner.encode()).hexdigest())))
        self.validate_link(link,owner,bid,payment)
        if not payment['external']:
            self.store.attach_checkout(owner,bid,link['id'],mode='razorpay_test')
        return link

    def start(self,owner,bid):
        p=self.store.begin_payment(owner,bid,'payment:'+bid,mode='razorpay_test')
        if p['state']=='paid':return dict(mode='razorpay_test',booking=self.store.booking(bid,owner))
        if p['state']!='pending':raise Rejected('This payment is closed; review a fresh quote')
        link=self.find_link(owner,bid,p,create=True)
        b=self.poll(owner,bid,link=link)
        if b['state']!='held':return dict(mode='razorpay_test',booking=b)
        url=urlsplit(link.get('short_url',''))
        if url.scheme!='https' or url.hostname not in ('rzp.io','rzp.co','razorpay.com') or url.username or url.password:raise Rejected('Unexpected Razorpay checkout URL')
        return dict(mode='razorpay_test',booking=b,razorpay=dict(url=link['short_url'],id=link['id']))

    def captured_payment(self,link,p):
        captured=[x for x in link.get('payments',[]) if x.get('status')=='captured']
        if link.get('status')!='paid' or link.get('amount_paid')!=p['amount'] or len(captured)!=1 or captured[0].get('amount')!=p['amount']:raise Rejected('Razorpay test capture is not verified')
        pid=captured[0].get('payment_id','')
        if not re.fullmatch(r'pay_[A-Za-z0-9]+',pid):raise Rejected('Invalid captured payment reference')
        payment=self.api.request('GET','/payments/'+pid)
        if (payment.get('id')!=pid or payment.get('amount')!=p['amount'] or payment.get('currency')!='INR'
            or payment.get('status') not in ('captured','refunded') or not link.get('order_id') or payment.get('order_id')!=link['order_id']):raise Rejected('Razorpay captured payment binding mismatch')
        return payment

    def poll(self,owner,bid,link=None):
        p=self.payment(owner,bid);b=self.store.booking(bid,owner)
        if p['state']=='refund_required':return self.refund(owner,bid)
        if p['state']!='pending':return b
        link=link or self.find_link(owner,bid,p)
        if link is None:return b
        self.validate_link(link,owner,bid,p)
        if link['status']=='paid':
            captured=self.captured_payment(link,p)
            if captured.get('amount_refunded',0) or captured.get('status')!='captured':raise Rejected('Gateway payment already reversed; operator review required')
            self.bind_operation(bid,'razorpay_capture',captured['id'])
            b=self.store.settle(owner,bid,external=link['id'])
            if b['payment_state']=='refund_required':
                try:b=self.refund(owner,bid)
                except Exception:self.store.denied(bid,'Razorpay test refund required; not yet confirmed','payment')
        elif b['state']=='cancelled' or b['hold_until']<=self.store.clock() or link['status'] in ('cancelled','expired'):
            if link['status']=='created':
                cancelled=self.api.request('POST','/payment_links/'+link['id']+'/cancel',{})
                if cancelled.get('status')!='cancelled':raise Rejected('Checkout cancellation is not yet confirmed; reconciliation required')
            b=self.store.settle(owner,bid,success=False)
        return self.store.booking(bid,owner)

    def refund(self,owner,bid):
        p=self.payment(owner,bid);b=self.store.booking(bid,owner)
        if p['state']!='refund_required':return b
        link=self.find_link(owner,bid,p);captured=self.captured_payment(link,p)
        receipt='refund:'+bid;op=self.operation(bid,'razorpay_refund')
        if op and op['external']:
            refund=self.api.request('GET','/refunds/'+op['external'])
        else:
            existing=self.api.request('GET','/payments/'+captured['id']+'/refunds')
            matches=[x for x in existing.get('items',[]) if x.get('receipt')==receipt]
            if len(matches)>1:raise Rejected('Multiple refunds require operator review')
            refund=matches[0] if matches else None
            if refund is None:
                self.claim(bid,'razorpay_refund')
                refund=self.api.request('POST','/payments/'+captured['id']+'/refund',dict(amount=p['amount'],speed='normal',receipt=receipt),idempotency='refund_'+bid)
            self.bind_operation(bid,'razorpay_refund',refund['id'])
        if refund.get('payment_id')!=captured['id'] or refund.get('amount')!=p['amount'] or refund.get('currency')!='INR' or refund.get('receipt')!=receipt:raise Rejected('Refund binding mismatch')
        if refund.get('status')!='processed':raise Rejected('Razorpay test refund pending; not yet confirmed')
        self.store.refund_done(owner,bid,refund['id'],mode='razorpay_test')
        return self.store.booking(bid,owner)

    def reconcile(self):
        with self.store.connect() as db:
            rows=db.execute("SELECT b.id,b.owner FROM bookings b JOIN payments p ON p.booking=b.id WHERE p.mode='razorpay_test' AND p.state IN ('pending','refund_required')").fetchall()
        for row in rows:
            try:self.poll(row['owner'],row['id'])
            except Exception:self.store.denied(row['id'],'Razorpay test reconciliation pending; request operator review if it persists','payment')


def main():
    from dotenv import load_dotenv
    load_dotenv()
    try:RazorpayAPI().request('GET','/payment_links/?count=1')
    except Rejected as exc:print(str(exc));raise SystemExit(1) from None
    print('Razorpay TEST authentication passed. No payment created. Hosted checkout and capture/refund still need live verification.')


if __name__=='__main__':main()
