"""Local Razorpay API doubles. No real test gateway transaction is claimed."""
import asyncio
import copy
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from servicesetu.core import Store,Rejected
from servicesetu.razorpay_payments import RazorpayAPI,RazorpayTest
from servicesetu.payments import Payments
from servicesetu.conversation import Conversation
from servicesetu.reasoning import Reasoner
from servicesetu.service import Services,LocalBus
from tests.test_proofs import Clock


class Gateway:
    def __init__(self):
        self.link=None;self.capture=None;self.refund=None;self.calls=[]
        self.lose_link=False;self.lose_refund=False;self.hide_links=False;self.refund_status='processed';self.cancel_status='cancelled'
    def request(self,method,path,data=None,idempotency=None):
        self.calls.append((method,path,copy.deepcopy(data),idempotency))
        if method=='GET' and path.startswith('/payment_links/?'):
            return {'payment_links':[] if self.hide_links or not self.link else [copy.deepcopy(self.link)]}
        if method=='POST' and path=='/payment_links/':
            self.link=dict(copy.deepcopy(data),id='plink_testfixture',short_url='https://rzp.io/i/synthetic',status='created',amount_paid=0,payments=[],order_id='order_fixture')
            if self.lose_link:self.lose_link=False;raise Rejected('synthetic lost create response')
            return copy.deepcopy(self.link)
        if method=='GET' and path=='/payment_links/plink_testfixture':return copy.deepcopy(self.link)
        if method=='POST' and path.endswith('/cancel'):
            self.link['status']=self.cancel_status;return copy.deepcopy(self.link)
        if method=='GET' and path=='/payments/pay_fixture':return copy.deepcopy(self.capture)
        if method=='GET' and path=='/payments/pay_fixture/refunds':return {'items':[copy.deepcopy(self.refund)] if self.refund else []}
        if method=='POST' and path=='/payments/pay_fixture/refund':
            self.refund=dict(copy.deepcopy(data),id='rfnd_fixture',payment_id='pay_fixture',currency='INR',status=self.refund_status)
            if self.lose_refund:self.lose_refund=False;raise Rejected('synthetic lost refund response')
            return copy.deepcopy(self.refund)
        if method=='GET' and path=='/refunds/rfnd_fixture':return copy.deepcopy(self.refund)
        raise AssertionError((method,path))
    def paid(self):
        self.link.update(status='paid',amount_paid=self.link['amount'],payments=[dict(payment_id='pay_fixture',status='captured',amount=self.link['amount'])])
        self.capture=dict(id='pay_fixture',amount=self.link['amount'],currency='INR',status='captured',order_id='order_fixture',amount_refunded=0)
    def posts(self,path):return [c for c in self.calls if c[0]=='POST' and c[1]==path]


class RazorpayBoundaries(unittest.TestCase):
    def setUp(self):
        tmp=tempfile.TemporaryDirectory();self.addCleanup(tmp.cleanup)
        self.clock=Clock();self.store=Store(Path(tmp.name)/'razorpay.db',self.clock);self.store.seed()
        self.owner='alice';self.slot=self.store.provider('p1')['slots'][0]
        self.q=self.store.quote(self.owner,'p1',self.slot);self.b=self.store.hold(self.owner,self.q['id'])
        self.api=Gateway();self.adapter=RazorpayTest(self.store,self.api)
        patcher=patch('servicesetu.razorpay_payments.RazorpayAPI',return_value=self.api);patcher.start();self.addCleanup(patcher.stop)
    def start(self):
        self.store.approve(self.owner,self.b['id'],self.q['id'])
        return self.adapter.start(self.owner,self.b['id'])

    def test_no_link_before_exact_quote_approval(self):
        with self.assertRaises(Rejected):self.adapter.start(self.owner,self.b['id'])
        self.assertEqual(self.api.calls,[])
        with self.assertRaises(Rejected):self.store.approve(self.owner,self.b['id'],'q_wrong')

    def test_same_link_retry_no_customer_notifications_and_verified_capture(self):
        result=self.start();self.adapter.start(self.owner,self.b['id'])
        self.assertEqual(result['booking']['state'],'held');self.assertEqual(result['mode'],'razorpay_test')
        self.assertEqual(len(self.api.posts('/payment_links/')),1)
        body=self.api.posts('/payment_links/')[0][2]
        self.assertEqual(body['notify'],{'sms':False,'email':False});self.assertFalse(body['accept_partial']);self.assertNotIn('customer',body)
        self.assertNotIn(self.owner,json.dumps(body))
        self.api.paid();self.assertEqual(self.adapter.poll(self.owner,self.b['id'])['state'],'confirmed')
        self.adapter.poll(self.owner,self.b['id'])
        with self.store.connect() as db:self.assertEqual(db.execute('SELECT count(*) FROM payments').fetchone()[0],1)
        self.assertEqual(sum(e['kind']=='booking_confirmed' for e in self.store.timeline(self.owner,self.b['id'])),1)

    def test_other_customer_cannot_poll_or_resume(self):
        self.start();before=len(self.api.calls)
        with self.assertRaises(Rejected):self.adapter.poll('mallory',self.b['id'])
        with self.assertRaises(Rejected):self.adapter.start('mallory',self.b['id'])
        self.assertEqual(len(self.api.calls),before)

    def test_link_binding_mismatch_never_confirms(self):
        self.start();self.api.paid()
        for field,value in (('reference_id','b_foreign'),('amount',1),('currency','USD'),('accept_partial',True)):
            old=self.api.link[field];self.api.link[field]=value
            with self.subTest(field=field),self.assertRaises(Rejected):self.adapter.poll(self.owner,self.b['id'])
            self.api.link[field]=old
        self.assertEqual(self.store.booking(self.b['id'],self.owner)['state'],'held')

    def test_payment_amount_currency_order_and_capture_are_checked(self):
        self.start();self.api.paid()
        for field,value in (('amount',1),('currency','USD'),('order_id','order_other'),('status','authorized'),('amount_refunded',1)):
            old=self.api.capture[field];self.api.capture[field]=value
            with self.subTest(field=field),self.assertRaises(Rejected):self.adapter.poll(self.owner,self.b['id'])
            self.api.capture[field]=old

    def test_late_capture_refunds_and_never_confirms(self):
        self.start();self.api.paid();self.clock.now+=121
        result=self.adapter.poll(self.owner,self.b['id'])
        self.assertEqual((result['state'],result['payment_state']),('cancelled','refunded'))
        self.assertEqual(self.api.posts('/payments/pay_fixture/refund')[0][3],'refund_'+self.b['id'])

    def test_pending_refund_remains_required_until_processed(self):
        self.start();self.api.paid();self.adapter.poll(self.owner,self.b['id']);self.api.refund_status='pending'
        result=Payments(self.store,'razorpay_test').cancel(self.owner,self.b['id'],'provider:p1')
        self.assertEqual(result['payment_state'],'refund_required')
        self.api.refund['status']='processed';self.adapter.reconcile()
        self.assertEqual(self.store.booking(self.b['id'],self.owner)['payment_state'],'refunded')
        self.assertEqual(len(self.api.posts('/payments/pay_fixture/refund')),1)

    def test_lost_link_response_is_recovered_without_another_create(self):
        self.api.lose_link=True
        with self.assertRaises(Rejected):self.start()
        self.adapter.start(self.owner,self.b['id'])
        self.assertEqual(len(self.api.posts('/payment_links/')),1)

    def test_unknown_create_is_not_reissued_while_gateway_list_lags(self):
        self.api.lose_link=True
        with self.assertRaises(Rejected):self.start()
        self.api.hide_links=True
        with self.assertRaisesRegex(Rejected,'outcome is pending'):self.adapter.start(self.owner,self.b['id'])
        self.assertEqual(len(self.api.posts('/payment_links/')),1)

    def test_lost_refund_response_recovers_existing_gateway_refund(self):
        self.start();self.api.paid();self.adapter.poll(self.owner,self.b['id']);self.api.lose_refund=True
        Payments(self.store,'razorpay_test').cancel(self.owner,self.b['id'],'provider:p1')
        self.adapter.reconcile()
        self.assertEqual(self.store.booking(self.b['id'],self.owner)['payment_state'],'refunded')
        self.assertEqual(len(self.api.posts('/payments/pay_fixture/refund')),1)

    def test_unpaid_checkout_cancellation_must_be_confirmed(self):
        self.start();Payments(self.store,'razorpay_test').cancel(self.owner,self.b['id'])
        self.api.cancel_status='created'
        with self.assertRaises(Rejected):self.adapter.poll(self.owner,self.b['id'])
        self.assertEqual(self.store.booking(self.b['id'],self.owner)['payment_state'],'pending')
        self.api.cancel_status='cancelled';self.adapter.poll(self.owner,self.b['id'])
        self.assertEqual(self.store.booking(self.b['id'],self.owner)['payment_state'],'declined')

    def test_expired_retry_and_replacement_cannot_reuse_payment_consent(self):
        self.start();self.clock.now+=121
        with self.assertRaises(Rejected):self.adapter.start(self.owner,self.b['id'])
        self.store.cancel(self.owner,self.b['id']);q=self.store.quote(self.owner,'p2',self.slot)
        b=self.store.hold(self.owner,q['id'],recovery_of=self.b['id'])
        with self.assertRaises(Rejected):self.adapter.start(self.owner,b['id'])
        self.assertEqual(len(self.api.posts('/payment_links/')),1)

    def test_hosted_checkout_and_check_payment_stay_bound_to_chat_booking(self):
        reasoner=Reasoner();reasoner.key=None;conv=Conversation(self.store,reasoner);bus=LocalBus(Services(self.store,'razorpay_test'))
        self.store.approve(self.owner,self.b['id'],self.q['id']);self.store.save_session(self.owner,dict(booking=self.b['id'],quote=self.q['id']))
        reply=asyncio.run(conv.handle(self.owner,'resume checkout',bus))
        self.assertIn('hosted page',reply['text']);self.assertIn('https://rzp.io/',reply['text'])
        self.assertNotIn('payment',reply)  # Never send a fictitious native ACP Razorpay checkout.
        self.api.paid();reply=asyncio.run(conv.handle(self.owner,'check payment',bus))
        self.assertIn('Booking status: confirmed',reply['text']);self.assertIn('Razorpay TEST transaction',reply['text'])


class RazorpayCredentials(unittest.TestCase):
    def test_live_and_missing_keys_are_refused_without_exposing_secret(self):
        for key in ('','rzp_live_synthetic'):
            with patch.dict('os.environ',{'RAZORPAY_KEY_ID':key,'RAZORPAY_KEY_SECRET':'private-synthetic-secret'}):
                with self.assertRaises(Rejected) as result:RazorpayAPI()
                self.assertNotIn('private-synthetic-secret',str(result.exception))
