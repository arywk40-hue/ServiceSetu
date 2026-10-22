"""Address collection, review binding and optional postal details."""
import asyncio
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from servicesetu.conversation import Conversation
from servicesetu.core import Store,Rejected
from servicesetu.coverage import covers,requires_pin
from servicesetu.reasoning import Reasoner
from servicesetu.service import Services,LocalBus
from tests.test_proofs import Clock


class ServiceAddresses(unittest.TestCase):
    def setUp(self):
        temp=tempfile.TemporaryDirectory();self.addCleanup(temp.cleanup)
        self.clock=Clock();self.store=Store(Path(temp.name)/'addresses.db',self.clock)
        self.store.seed(days=3,nationwide_demo=True)
        self.reasoner=Reasoner();self.reasoner.key=None
        self.conv=Conversation(self.store,self.reasoner);self.bus=LocalBus(Services(self.store,payment_mode='mock'))
        self.slot=self.store.provider('p1')['slots'][0]
        self.job=dict(action='search',service='ac',city='Mumbai',area='Powai',slot=self.slot,budget_rupees=1000)
        self.address='Flat 12, Demo House, Example Road'

    def send(self,text,owner='alice'):
        return asyncio.run(self.conv.handle(owner,text,self.bus))

    def payload(self,reply):return json.loads(reply.get('metadata',{}).get('card_payload','{}'))

    def start(self):
        self.send(json.dumps(self.job))
        qid=self.store.session('alice')['quotes'][0]
        reply=self.send('select '+qid)
        choice=next(item['selection'] for item in self.payload(reply)['ctas'] if item['selection']['action']=='open_quote_address')
        return self.send(json.dumps(choice))

    def review(self):
        self.start();return self.send(self.address)

    def approve(self,review):
        return self.send(json.dumps(self.payload(review)['approve_cta']['selection']))

    def count(self,table,where='1=1'):
        with self.store.connect() as db:return db.execute('SELECT count(*) FROM '+table+' WHERE '+where).fetchone()[0]

    def test_city_locality_can_find_providers_without_pin(self):
        reply=self.send(json.dumps(dict(self.job,pincode='')))
        self.assertEqual(reply['metadata']['card_kind'],'carousel')
        self.assertNotIn('pincode',self.store.session('alice')['job'])

    def test_unserved_city_does_not_require_pin(self):
        reply=self.send(json.dumps(dict(self.job,city='Jaipur',area='Vaishali Nagar')))
        self.assertIn('Your location was accepted',reply['text'])
        self.assertNotIn('Please give the six-digit',reply['text'])

    def test_pin_only_provider_can_request_postal_clarification(self):
        provider=dict(self.store.provider('p1'),coverage=[dict(city='mumbai',pincodes=['400076'])])
        job=dict(city='mumbai',area='powai')
        self.assertFalse(covers(provider,job));self.assertTrue(requires_pin(job,[provider]))
        self.assertTrue(covers(provider,dict(job,pincode='400076')))

    def test_selection_collects_address_without_hold_or_payment(self):
        reply=self.start()
        self.assertEqual(self.payload(reply)['submit_cta']['selection']['action'],'set_address')
        self.assertEqual(self.count('bookings',"state='held'"),0)
        self.assertEqual(self.count('payments'),0)
        self.assertNotIn('approve_cta',self.payload(reply))

    def test_address_is_reviewed_saved_and_in_confirmed_status(self):
        reply=self.review()
        self.assertEqual(reply['metadata']['card_kind'],'review')
        self.assertIn(self.address,reply['text']);self.assertIn('Powai, Mumbai',reply['text'])
        self.assertEqual(self.count('payments'),0)
        result=self.approve(reply)
        self.assertIn('confirmed',result['text']);self.assertIn(self.address,result['text'])
        bid=self.store.session('alice')['booking']
        self.assertEqual(self.store.booking(bid,'alice')['service_address']['address_line'],self.address)
        self.assertIn('Service address recorded',self.send('show what happened')['text'])

    def test_short_or_command_answers_do_not_create_hold(self):
        self.start()
        for text in ('yes','approve','approve this booking','12345'):
            self.send(text)
            self.assertEqual(self.count('bookings',"state='held'"),0)
            self.assertEqual(self.count('payments'),0)

    def test_stale_address_form_is_rejected(self):
        first=self.start();old=self.payload(first)['submit_cta']['selection']
        second=self.store.session('alice')['quotes'][1];self.send('select '+second)
        reply=self.send(json.dumps(dict(old,address_line=self.address)))
        self.assertIn('no longer current',reply['text']);self.assertEqual(self.count('bookings',"state='held'"),0)

    def test_expired_quote_does_not_accept_address_or_charge(self):
        self.start();self.clock.now+=301
        reply=self.send(self.address)
        self.assertIn('expired',reply['text'].lower());self.assertEqual(self.count('payments'),0)
        self.assertEqual(self.count('events',"kind='service_address_recorded'"),0)

    def test_address_edit_invalidates_old_approval(self):
        old=self.review();old_approval=self.payload(old)['approve_cta']['selection']
        self.send('change address')
        new=self.send('Flat 24, Another Demo House, Sample Street')
        rejected=self.send(json.dumps(old_approval))
        self.assertIn('Approval must match',rejected['text']);self.assertEqual(self.count('payments'),0)
        result=self.approve(new);self.assertIn('confirmed',result['text'])
        self.assertIn('Flat 24',result['text'])

    def test_confirmed_booking_cannot_silently_change_address(self):
        review=self.review();self.approve(review)
        reply=self.send('change address')
        self.assertIn('Start a new request',reply['text'])
        self.assertEqual(self.store.booking(self.store.session('alice')['booking'],'alice')['service_address']['address_line'],self.address)

    def test_replacement_reuses_exact_original_address(self):
        review=self.review();self.approve(review)
        bid=self.store.session('alice')['booking'];self.store.cancel('alice',bid,actor='provider:p1')
        self.send('recover');reply=self.send('option 1')
        self.assertEqual(reply['metadata']['card_kind'],'review')
        self.assertIn(self.address,reply['text'])
        self.approve(reply)
        self.assertEqual(self.store.booking(self.store.session('alice')['booking'],'alice')['service_address']['address_line'],self.address)

    def test_core_rejects_address_required_quote_without_address(self):
        job=dict(service='ac',city='mumbai',area='powai',slot=self.slot,budget=100000)
        q=self.store.quote('alice','p1',self.slot,job=job,address_required=True)
        with self.assertRaises(Rejected):self.store.hold('alice',q['id'])
        self.assertEqual(self.count('bookings',"state='held'"),0)

    def test_address_not_sent_to_reasoning_model(self):
        self.start()
        with patch.object(self.reasoner,'parse',side_effect=AssertionError('Address must not be model parsed')):
            reply=self.send(self.address)
        self.assertEqual(reply['metadata']['card_kind'],'review')
        with self.assertRaises(Rejected):self.store.booking(self.store.session('alice')['booking'],'someone-else')

    def test_cancel_address_and_new_service_invalidate_form(self):
        reply=self.start();old=self.payload(reply)['submit_cta']['selection']
        self.send('cancel address')
        result=self.send(json.dumps(dict(old,address_line=self.address)))
        self.assertIn('no longer current',result['text'])
        self.assertEqual(self.count('bookings',"state='held'"),0)
