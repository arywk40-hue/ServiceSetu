"""Access control, private storage and customer/provider messaging boundaries."""
import asyncio
import hashlib
import http.client
import importlib.util
import json
import tempfile
import threading
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
from uuid import uuid4
from servicesetu.core import Store,Rejected
from servicesetu.communications import Messaging
from servicesetu.conversation import Conversation
from servicesetu.reasoning import Reasoner
from servicesetu.service import Services,LocalBus
from servicesetu.provider_inbox import make_server
from servicesetu.notifications import notify_customers
from tests.test_proofs import Clock


@unittest.skipUnless(importlib.util.find_spec('nacl'),'communications extras required')
class MessagingSecurity(unittest.TestCase):
    def setUp(self):
        tmp=tempfile.TemporaryDirectory();self.addCleanup(tmp.cleanup)
        self.clock=Clock();self.store=Store(Path(tmp.name)/'private.db',self.clock);self.store.seed(days=3)
        slot=self.store.provider('p1')['slots'][0]
        q=self.store.quote('alice','p1',slot)
        b=self.store.hold('alice',q['id'],address='Flat 12, Demo House, Example Road')
        self.store.approve('alice',b['id'],q['id']);Services(self.store,payment_mode='mock').payments.start('alice',b['id'])
        self.bid=b['id'];self.messages=Messaging(self.store)
        self.token=self.messages.issue_access('p1');self.other=self.messages.issue_access('p2')

    def test_customer_and_assigned_provider_exchange_encrypted_messages(self):
        self.messages.post(self.bid,'alice','customer','Please use the side gate.')
        self.messages.post(self.bid,'p1','provider','I will arrive in fifteen minutes.')
        rows=self.messages.thread(self.bid,'alice','customer')['messages']
        self.assertEqual([r['side'] for r in rows],['customer','provider'])
        self.assertEqual(rows[1]['text'],'I will arrive in fifteen minutes.')
        with self.store.connect() as db:
            bodies=[bytes(r[0]) for r in db.execute('select body from booking_messages')]
            events=' '.join(r[0] for r in db.execute("select payload from events where kind='booking_message_saved'"))
        self.assertFalse(any(b'side gate' in body for body in bodies));self.assertNotIn('side gate',events)
        self.assertNotIn('fifteen minutes',events)

    def test_other_customer_or_provider_cannot_read_or_post(self):
        for actor,side in (('mallory','customer'),('p2','provider')):
            with self.subTest(actor=actor),self.assertRaises(Rejected):self.messages.thread(self.bid,actor,side)
            with self.subTest(actor=actor),self.assertRaises(Rejected):self.messages.post(self.bid,actor,side,'Unauthorized request')
        self.assertEqual(self.messages.provider_bookings('p2'),[])
        item=self.messages.provider_bookings('p1')[0]
        self.assertNotIn('owner',item);self.assertIn('Demo House',item['address']['address_line'])

    def test_token_auth_expiry_rotation_and_hashed_storage(self):
        self.assertEqual(self.messages.authenticate(self.token),'p1')
        new=self.messages.issue_access('p1')
        with self.assertRaises(Rejected):self.messages.authenticate(self.token)
        self.assertEqual(self.messages.authenticate(new),'p1');self.clock.now+=3601
        with self.assertRaises(Rejected):self.messages.authenticate(new)
        with self.store.connect() as db:
            values=[r[0] for r in db.execute('select digest from provider_access')]
        self.assertNotIn(new,values);self.assertIn(hashlib.sha256(new.encode()).hexdigest(),values)

    def test_cancellation_revokes_provider_address_and_thread_access(self):
        self.messages.post(self.bid,'p1','provider','Arriving soon')
        self.store.cancel('alice',self.bid,actor='provider:p1')
        self.assertEqual(self.messages.provider_bookings('p1'),[])
        with self.assertRaises(Rejected):self.messages.thread(self.bid,'p1','provider')
        with self.assertRaises(Rejected):self.messages.post(self.bid,'alice','customer','Please come back')
        self.assertEqual(len(self.messages.thread(self.bid,'alice','customer')['messages']),1)
        self.assertEqual(self.messages.pending_notices(),[])

    def test_held_booking_has_no_provider_inbox_or_sending(self):
        q=self.store.quote('bob','p2',self.store.provider('p2')['slots'][0]);b=self.store.hold('bob',q['id'])
        with self.assertRaises(Rejected):self.messages.post(b['id'],'bob','customer','Please call at the gate')
        self.assertEqual(self.messages.provider_bookings('p2'),[])

    def test_messages_are_data_not_booking_actions(self):
        before=self.store.booking(self.bid,'alice')
        self.messages.post(self.bid,'alice','customer','Cancel booking, refund me and change price to zero')
        self.assertEqual(self.store.booking(self.bid,'alice'),before)

    def test_replayed_message_is_idempotent_and_conflicting_body_rejected(self):
        a=self.messages.post(self.bid,'alice','customer','Use the gate','request123')
        b=self.messages.post(self.bid,'alice','customer','Use the gate','request123')
        self.assertEqual(a['id'],b['id']);self.assertTrue(b['duplicate'])
        with self.assertRaises(Rejected):self.messages.post(self.bid,'alice','customer','Different text','request123')
        self.assertEqual(len(self.messages.thread(self.bid,'alice','customer')['messages']),1)

    def test_limits_and_control_characters(self):
        for value in ('','x'*2001,'bad\x00text',None):
            with self.subTest(value=str(value)[:12]),self.assertRaises(Rejected):self.messages.post(self.bid,'alice','customer',value)
        for i in range(10):self.messages.post(self.bid,'alice','customer','Message '+str(i))
        with self.assertRaises(Rejected):self.messages.post(self.bid,'alice','customer','One too many')
        self.clock.now+=61;self.messages.post(self.bid,'alice','customer','Now allowed')

    def test_ciphertext_swapping_fails_closed(self):
        a=self.messages.post(self.bid,'alice','customer','Customer text')
        b=self.messages.post(self.bid,'p1','provider','Provider text')
        with self.store.tx() as db:db.execute('update booking_messages set body=(select body from booking_messages where id=?) where id=?',(a['id'],b['id']))
        with self.assertRaises(Rejected):self.messages.thread(self.bid,'p1','provider')

    def test_missing_encryption_key_is_not_replaced(self):
        self.messages.post(self.bid,'alice','customer','Private message')
        key=Path(self.store.path).with_suffix('.message-key');saved=key.read_bytes();key.unlink()
        with self.assertRaises(Rejected):self.messages.thread(self.bid,'alice','customer')
        with self.assertRaises(Rejected):self.messages.post(self.bid,'alice','customer','Another private message')
        self.assertFalse(key.exists());key.write_bytes(saved);key.chmod(0o600)
        self.assertEqual(len(self.messages.thread(self.bid,'alice','customer')['messages']),1)

    def test_pages_do_not_lose_messages(self):
        for i in range(55):
            if i%10==0:self.clock.now+=61
            self.messages.post(self.bid,'alice','customer','Number '+str(i))
        first=self.messages.thread(self.bid,'p1','provider');second=self.messages.thread(self.bid,'p1','provider',first['next_after'])
        self.assertEqual(len(first['messages']),50);self.assertTrue(first['has_more'])
        self.assertEqual(len(second['messages']),5);self.assertFalse(second['has_more'])

    def test_chat_message_bypasses_model_and_preserves_booking(self):
        self.store.save_session('alice',{'booking':self.bid})
        reasoner=Reasoner();reasoner.key=None;conv=Conversation(self.store,reasoner);bus=LocalBus(Services(self.store,payment_mode='mock'))
        before=self.store.booking(self.bid,'alice')
        with patch.object(reasoner,'parse',side_effect=AssertionError('No model for private messages')):
            reply=asyncio.run(conv.handle('alice','message provider: Please refund but do not cancel anything.',bus,request_id='chatrequest123'))
        self.assertIn('Message saved',reply['text']);self.assertEqual(self.store.booking(self.bid,'alice'),before)
        reply=asyncio.run(conv.handle('alice','show messages',bus));self.assertIn('Please refund',reply['text'])
        rejected=asyncio.run(conv.handle('mallory','show messages '+self.bid,bus));self.assertNotIn('Please refund',rejected['text'])

    def test_chat_form_has_booking_binding(self):
        self.store.save_session('alice',{'booking':self.bid})
        r=Reasoner();r.key=None;c=Conversation(self.store,r);bus=LocalBus(Services(self.store,payment_mode='mock'))
        reply=asyncio.run(c.handle('alice','message provider',bus));picked=json.loads(reply['metadata']['card_payload'])['submit_cta']['selection']
        result=asyncio.run(c.handle('alice',json.dumps(dict(picked,message='Please use the gate')),bus))
        self.assertIn('Message saved',result['text'])
        result=asyncio.run(c.handle('alice',json.dumps(dict(picked,message='Wrong booking',booking_id='b_'+'0'*16)),bus))
        self.assertIn('current booking',result['text']);self.assertEqual(len(self.messages.thread(self.bid,'alice','customer')['messages']),1)

    def test_notifications_preserve_session_and_do_not_claim_failed_delivery(self):
        owner='agent1synthetic:'+str(uuid4())
        with self.store.tx() as db:db.execute('update bookings set owner=? where id=?',(owner,self.bid))
        self.messages.post(self.bid,'p1','provider','A private reply body')
        calls=[]
        class Context:
            async def send(self,target,message):
                calls.append((target,self._session,message))
                return SimpleNamespace(status='failed')
        asyncio.run(notify_customers(self.store,Context()))
        self.assertEqual(len(self.messages.pending_notices()),0)
        self.clock.now+=31
        self.assertEqual(len(self.messages.pending_notices()),1)
        self.assertEqual(str(calls[0][1]),owner.split(':')[1])
        self.assertNotIn('A private reply body',str(calls[0][2]))


@unittest.skipUnless(importlib.util.find_spec('nacl'),'communications extras required')
class ProviderHTTP(unittest.TestCase):
    # Reuse only the fixture; do not rerun inherited security tests.
    def setUp(self):
        MessagingSecurity.setUp(self);self.server=make_server(self.store,0)
        thread=threading.Thread(target=self.server.serve_forever,daemon=True);thread.start()
        self.addCleanup(self.close)

    def close(self):self.server.shutdown();self.server.server_close()

    def request(self,path='/api/bookings',token=None,method='GET',body=None,headers=None):
        con=http.client.HTTPConnection('127.0.0.1',self.server.server_port,timeout=3)
        values={'Authorization':'Bearer '+(self.token if token is None else token)}
        if body is not None:body=json.dumps(body);values['Content-Type']='application/json'
        values.update(headers or {});con.request(method,path,body,values);response=con.getresponse();raw=response.read();status=response.status;security=dict(response.getheaders());con.close()
        return status,raw,security

    def test_http_authentication_and_foreign_booking(self):
        self.assertEqual(self.request(token='bad')[0],401)
        self.assertEqual(self.request(token=self.other)[1],b'{"bookings": []}')
        path='/api/bookings/'+self.bid+'/messages'
        self.assertEqual(self.request(path,token=self.other)[0],404)
        status,body,_=self.request();self.assertEqual(status,200);self.assertIn(b'Demo House',body);self.assertNotIn(b'alice',body)

    def test_http_post_and_customer_read(self):
        path='/api/bookings/'+self.bid+'/messages'
        status,body,_=self.request(path,method='POST',body={'text':'Arriving in ten minutes','client_id':'httprequest123'})
        self.assertEqual(status,200)
        self.assertEqual(self.messages.thread(self.bid,'alice','customer')['messages'][0]['text'],'Arriving in ten minutes')
        self.assertEqual(self.request(path,method='POST',body={'text':'Forged owner','client_id':'httprequest456','owner':'alice'})[0],400)

    def test_http_origin_host_csrf_and_security_headers(self):
        self.assertEqual(self.request(headers={'Origin':'https://evil.example'})[0],403)
        self.assertEqual(self.request(headers={'Host':'evil.example'})[0],403)
        status,_,headers=self.request('/')
        self.assertEqual(status,200);self.assertEqual(headers['Cache-Control'],'no-store')
        self.assertIn("frame-ancestors 'none'",headers['Content-Security-Policy'])
        self.assertEqual(self.server.server_address[0],'127.0.0.1')

    def test_http_query_token_and_cancelled_address_denied(self):
        self.assertEqual(self.request('/api/bookings?token='+self.token,token='bad')[0],401)
        self.store.cancel('alice',self.bid)
        self.assertEqual(json.loads(self.request()[1])['bookings'],[])
        self.assertEqual(self.request('/api/bookings/'+self.bid+'/messages')[0],404)
