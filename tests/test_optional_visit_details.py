"""Optional visit details and button-first customer messaging."""
import asyncio
import json
import importlib.util
import tempfile
import unittest
from pathlib import Path
from servicesetu import cards
from servicesetu.core import Store,Rejected
from servicesetu.conversation import Conversation
from servicesetu.reasoning import Reasoner
from servicesetu.service import Services,LocalBus
from tests.test_proofs import Clock


class OptionalVisitDetails(unittest.TestCase):
    def setUp(self):
        tmp=tempfile.TemporaryDirectory();self.addCleanup(tmp.cleanup)
        self.clock=Clock();self.store=Store(Path(tmp.name)/'optional.db',self.clock);self.store.seed(days=3)
        self.reasoner=Reasoner();self.reasoner.key=None
        self.conv=Conversation(self.store,self.reasoner);self.bus=LocalBus(Services(self.store,payment_mode='mock'))
        self.job=dict(action='search',service='ac',city='bengaluru',area='indiranagar',slot=self.store.provider('p1')['slots'][0],budget_rupees=1000)
        self.line='Flat 12, Demo House, Example Road'

    def send(self,text,owner='alice'):return asyncio.run(self.conv.handle(owner,text,self.bus))
    def payload(self,reply):return json.loads(reply['metadata']['card_payload'])
    def click(self,reply,action,**fields):
        item=next(item['selection'] for item in self.payload(reply)['ctas'] if item['selection']['action']==action)
        return self.send(json.dumps(dict(item,**fields)))
    def start(self):self.send(json.dumps(self.job));return self.send('option 1')
    def skip_confirm(self):
        choice=self.start();review=self.click(choice,'skip_address')
        approved=self.send(json.dumps(self.payload(review)['approve_cta']['selection']))
        return approved

    def test_choice_offers_skip_and_confirmed_booking_needs_no_contact_or_messages(self):
        status=self.skip_confirm();b=self.store.booking(self.store.session('alice')['booking'],'alice')
        self.assertEqual(b['state'],'confirmed');self.assertEqual(b['payment_state'],'paid')
        self.assertNotIn('service_address',b);self.assertTrue(self.store.address_deferred(b['id']))
        self.assertNotIn('phone',self.store.session('alice'));self.assertNotIn('email',self.store.session('alice'))
        self.assertIn('add_address',[c['selection']['action'] for c in self.payload(status)['ctas']])
        with self.store.connect() as db:self.assertEqual(db.execute('select count(*) from payments').fetchone()[0],1)

    def test_plain_skip_and_empty_address_form_both_open_review(self):
        self.start();review=self.send("I don't know my address")
        self.assertEqual(review['metadata']['card_kind'],'review');self.assertIn('Not provided',review['text'])
        self.send('reject');choice=self.send('option 2');form=self.click(choice,'open_quote_address')
        picked=self.payload(form)['submit_cta']['selection']
        self.assertFalse(self.payload(form)['fields'][0]['required'])
        reply=self.send(json.dumps(dict(picked,address_line='')))
        self.assertEqual(reply['metadata']['card_kind'],'review')

    def test_add_after_confirmation_preserves_price_payment_and_shares_only_assigned(self):
        status=self.skip_confirm();bid=self.store.session('alice')['booking'];before=self.store.booking(bid,'alice')
        form=self.click(status,'add_address');picked=self.payload(form)['submit_cta']['selection']
        result=self.send(json.dumps(dict(picked,address_line=self.line)));after=self.store.booking(bid,'alice')
        for key in ('id','provider','quote','slot','payment_state','state'):self.assertEqual(before[key],after[key])
        self.assertEqual(after['service_address']['address_line'],self.line);self.assertIn(self.line,result['text'])
        from servicesetu.communications import Messaging
        inbox=Messaging(self.store)
        self.assertEqual(inbox.provider_bookings('p1')[0]['address']['address_line'],self.line)
        self.assertEqual(inbox.provider_bookings('p2'),[])
        with self.store.connect() as db:self.assertEqual(db.execute('select count(*) from payments').fetchone()[0],1)

    def test_skip_later_form_keeps_existing_booking(self):
        status=self.skip_confirm();bid=self.store.session('alice')['booking']
        self.click(status,'add_address');reply=self.send('skip')
        self.assertIn('confirmed',reply['text']);self.assertNotIn('service_address',self.store.booking(bid,'alice'))

    def test_late_address_rejects_foreign_owner_cancelled_and_stale_form(self):
        status=self.skip_confirm();bid=self.store.session('alice')['booking']
        form=self.click(status,'add_address');old=self.payload(form)['submit_cta']['selection']
        self.send('add address')
        denied=self.send(json.dumps(dict(old,address_line=self.line)))
        self.assertIn('latest address form',denied['text'])
        with self.assertRaises(Rejected):self.store.provide_address('mallory',bid,self.line)
        self.store.cancel('alice',bid)
        with self.assertRaises(Rejected):self.store.provide_address('alice',bid,self.line)

    def test_address_skipped_booking_can_recover_without_address(self):
        self.skip_confirm();bid=self.store.session('alice')['booking'];self.store.cancel('alice',bid,actor='provider:p1')
        self.send('recover');choice=self.send('option 1');review=self.click(choice,'skip_address')
        self.send(json.dumps(self.payload(review)['approve_cta']['selection']))
        current=self.store.booking(self.store.session('alice')['booking'],'alice')
        self.assertEqual(current['state'],'confirmed');self.assertNotIn('service_address',current)

    def test_legacy_required_quote_accepts_explicit_deferral(self):
        job=dict(service='ac',city='bengaluru',area='indiranagar',slot=self.job['slot'],budget=100000)
        q=self.store.quote('alice','p1',self.job['slot'],job=job,address_required=True)
        b=self.store.hold('alice',q['id'],defer_address=True);self.store.approve('alice',b['id'],q['id'])
        result=Services(self.store,payment_mode='mock').payments.start('alice',b['id'])
        self.assertEqual(result['booking']['state'],'confirmed')

    def test_notification_and_message_cards_hide_ids_and_supply_actions(self):
        bid='b_'+'1'*16
        for reply in (cards.message_notice(bid),cards.message_saved(bid),cards.message_thread(bid,{'messages':[],'has_more':True,'next_after':50})):
            self.assertNotIn(bid,reply['text']);self.assertNotIn('show messages',reply['text'])
            self.assertTrue(self.payload(reply)['ctas'])
        more=next(c for c in self.payload(reply)['ctas'] if c['label']=='More messages')
        self.assertEqual(more['selection']['after'],50)

    @unittest.skipUnless(importlib.util.find_spec('nacl'),'communications extras required')
    def test_view_and_reply_buttons_use_owned_booking_and_hide_message_reference(self):
        status=self.skip_confirm();self.send('message provider: Please use the gate.')
        result=self.click(status,'open_messages');self.assertIn('Please use the gate.',result['text'])
        form=self.click(result,'compose_message');picked=self.payload(form)['submit_cta']['selection']
        saved=self.send(json.dumps(dict(picked,message='Thank you.')))
        self.assertNotIn('Message reference:',saved['text']);self.assertNotIn(self.store.session('alice')['booking'],saved['text'])
        self.assertIn('open_messages',[c['selection']['action'] for c in self.payload(saved)['ctas']])

    def test_replacement_cannot_discard_previously_recorded_address(self):
        q=self.store.quote('alice','p1',self.job['slot']);b=self.store.hold('alice',q['id'],address=self.line)
        self.store.approve('alice',b['id'],q['id']);Services(self.store,payment_mode='mock').payments.start('alice',b['id']);self.store.cancel('alice',b['id'])
        other=self.store.quote('alice','p2',self.job['slot'])
        with self.assertRaises(Rejected):self.store.hold('alice',other['id'],recovery_of=b['id'],defer_address=True)
