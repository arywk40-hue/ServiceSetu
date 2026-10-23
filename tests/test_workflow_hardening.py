"""Synthetic local acceptance; Stripe SDK doubles are not live checkout proof."""
import asyncio
import json
import os
import tempfile
import importlib.util
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock,patch
from uuid import UUID

from servicesetu.core import Store,Rejected,encode
from servicesetu.payments import Payments
from servicesetu.service import Services,LocalBus
from servicesetu.conversation import Conversation
from servicesetu.reasoning import Reasoner
from servicesetu.problems import Problems
from servicesetu.operator import import_pilot,accept,write_private
from servicesetu.notifications import notify_bookings
from servicesetu import cards
from tests.test_proofs import Clock


class Fixture(unittest.TestCase):
    def setUp(self):
        tmp=tempfile.TemporaryDirectory();self.addCleanup(tmp.cleanup)
        self.clock=Clock();self.store=Store(Path(tmp.name)/'workflow.db',self.clock);self.store.seed()
        self.owner='agent_customer:11111111-1111-1111-1111-111111111111'
        self.slot=self.store.provider('p1')['slots'][0]
        self.q=self.store.quote(self.owner,'p1',self.slot);self.b=self.store.hold(self.owner,self.q['id'])

    def mock_paid(self):
        self.store.approve(self.owner,self.b['id'],self.q['id'])
        return Payments(self.store,'mock').start(self.owner,self.b['id'])['booking']


class CheckoutHardening(Fixture):
    def setUp(self):
        super().setUp()
        self.adapter=Payments(self.store,'stripe_test')
        self.session=SimpleNamespace(id='cs_test_workflow',client_secret='synthetic',livemode=False,payment_status='paid',amount_total=self.q['amount'],currency='inr',metadata={'booking_id':self.b['id'],'owner':self.owner},client_reference_id=self.b['id'],payment_intent='pi_test',status='complete')
        self.gateway=SimpleNamespace(checkout=SimpleNamespace(Session=SimpleNamespace(create=Mock(return_value=self.session),retrieve=Mock(return_value=self.session),expire=Mock())),Refund=SimpleNamespace(create=Mock(return_value=SimpleNamespace(id='re_test',status='succeeded'))))
        self.patch=patch.object(self.adapter,'stripe',return_value=self.gateway);self.patch.start();self.addCleanup(self.patch.stop)
        self.store.approve(self.owner,self.b['id'],self.q['id'])

    def start(self):return self.adapter.start(self.owner,self.b['id'])
    def commit(self):return self.adapter.commit(self.owner,self.b['id'],self.session.id,'INR','699.00','concierge','concierge')

    def test_retry_reuses_checkout_and_duplicate_commit_keeps_one_payment(self):
        self.start();self.start();self.commit();self.commit();self.start()
        self.gateway.checkout.Session.create.assert_called_once()
        with self.store.connect() as db:self.assertEqual(db.execute('SELECT count(*) FROM payments').fetchone()[0],1)
        self.assertEqual(sum(e['kind']=='booking_confirmed' for e in self.store.timeline(self.owner,self.b['id'])),1)

    def test_expired_pending_retry_cannot_create_another_checkout(self):
        self.start();self.clock.now+=121
        with self.assertRaises(Rejected):self.start()
        self.gateway.checkout.Session.create.assert_called_once()
        self.assertEqual(self.commit()['payment_state'],'refunded')

    def test_payment_rail_cannot_change_on_restart(self):
        self.start()
        with self.assertRaises(Rejected):Payments(self.store,'mock').start(self.owner,self.b['id'])
        self.assertEqual(self.store.booking(self.b['id'],self.owner)['payment_mode'],'stripe_test')

    def test_refund_failure_does_not_block_provider_cancellation(self):
        self.start();self.commit();self.gateway.Refund.create.side_effect=RuntimeError('synthetic unavailable')
        result=self.adapter.cancel(self.owner,self.b['id'],'provider:p1')
        self.assertEqual((result['state'],result['payment_state']),('cancelled','refund_required'))
        self.assertTrue(any(e['kind']=='provider_cancelled' for e in self.store.timeline(self.owner,self.b['id'])))
        self.gateway.Refund.create.side_effect=None;self.adapter.reconcile()
        self.assertEqual(self.store.booking(self.b['id'],self.owner)['payment_state'],'refunded')

    def test_cancelled_pending_checkout_paid_later_is_refunded(self):
        self.start();self.adapter.cancel(self.owner,self.b['id'])
        self.assertEqual(self.commit()['payment_state'],'refunded')
        self.assertEqual(self.store.booking(self.b['id'],self.owner)['state'],'cancelled')

    def test_provider_coverage_removed_after_payment_refunds_instead_of_confirming(self):
        self.start();p=self.store.provider('p1');p['coverage']=[]
        with self.store.tx() as db:db.execute('UPDATE providers SET payload=? WHERE id=?',(encode(p),'p1'))
        self.assertEqual(self.commit()['payment_state'],'refunded')

    def test_lost_commit_reconciles_and_queues_customer_result(self):
        self.start();self.adapter.reconcile()
        self.assertEqual(self.store.booking(self.b['id'],self.owner)['state'],'confirmed')
        with self.store.connect() as db:self.assertEqual(db.execute('SELECT count(*) FROM booking_notices WHERE sent=0').fetchone()[0],1)

    def test_unknown_session_creation_response_is_recovered_with_same_idempotency(self):
        self.gateway.checkout.Session.create.side_effect=RuntimeError('synthetic timeout after gateway create')
        with self.assertRaises(RuntimeError):self.start()
        self.gateway.checkout.Session.create.side_effect=None;self.adapter.reconcile()
        calls=self.gateway.checkout.Session.create.call_args_list
        self.assertEqual(calls[0].kwargs,calls[1].kwargs)
        self.assertEqual(self.store.booking(self.b['id'],self.owner)['state'],'confirmed')

    def test_unpaid_cancelled_session_is_expired_by_reconciliation(self):
        self.session.payment_status='unpaid';self.session.status='open'
        self.start();self.adapter.cancel(self.owner,self.b['id']);self.adapter.reconcile()
        self.gateway.checkout.Session.expire.assert_called_once_with(self.session.id)
        self.assertEqual(self.store.booking(self.b['id'],self.owner)['payment_state'],'declined')

    def test_refund_binding_checked_again_before_gateway_refund(self):
        self.start();self.commit();self.session.livemode=True
        self.assertEqual(self.adapter.cancel(self.owner,self.b['id'])['payment_state'],'refund_required')
        self.gateway.Refund.create.assert_not_called()

    def test_embedded_checkout_never_redirects_out_of_conversation(self):
        self.start();args=self.gateway.checkout.Session.create.call_args.kwargs
        self.assertEqual(args['redirect_on_completion'],'never');self.assertNotIn('return_url',args)

    def test_resume_checkout_reuses_recorded_consent_and_refuses_other_customer(self):
        self.start();reasoner=Reasoner();reasoner.key=None;conv=Conversation(self.store,reasoner)
        self.store.save_session(self.owner,dict(booking=self.b['id'],quote=self.q['id']))
        bus=LocalBus(Services(self.store,'stripe_test'));bus.services.payments=self.adapter
        reply=asyncio.run(conv.handle(self.owner,'resume checkout',bus))
        self.assertEqual(reply['payment']['stripe']['id'],self.session.id)
        reply=asyncio.run(conv.handle('mallory',json.dumps(dict(action='resume_checkout',booking_id=self.b['id'])),bus))
        self.assertNotIn('payment',reply);self.gateway.checkout.Session.create.assert_called_once()


@unittest.skipUnless(importlib.util.find_spec('nacl'),'communications extras required')
class LifecycleAccess(Fixture):
    def setUp(self):
        super().setUp();self.mock_paid()
        reasoner=Reasoner();reasoner.key=None;self.conv=Conversation(self.store,reasoner);self.bus=LocalBus(Services(self.store,'mock'))
        self.store.save_session(self.owner,dict(booking=self.b['id'],quote=self.q['id']))

    def send(self,text,owner=None):return asyncio.run(self.conv.handle(owner or self.owner,text,self.bus))

    def test_problem_is_encrypted_booking_linked_and_idempotent(self):
        p=Problems(self.store);first=p.report(self.owner,self.b['id'],'Synthetic visit problem','same-request')
        self.assertTrue(p.report(self.owner,self.b['id'],'Synthetic visit problem','same-request')['duplicate'])
        with self.assertRaises(Rejected):p.report(self.owner,self.b['id'],'different text','same-request')
        with self.store.connect() as db:
            self.assertNotIn(b'Synthetic visit problem',bytes(db.execute('SELECT body FROM booking_problems').fetchone()[0]))
        self.assertNotIn('Synthetic visit problem',json.dumps(self.store.timeline(self.owner,self.b['id'])))
        self.assertEqual(p.queue()[0]['text'],'Synthetic visit problem');p.acknowledge(first['id'],'Test operator')
        self.assertIn('Operator acknowledged',self.send('show what happened')['text'])

    def test_other_customer_and_provider_cannot_report_or_view_queue_via_bus(self):
        p=Problems(self.store)
        for owner in ('mallory','provider:p1'):
            with self.assertRaises(Rejected):p.report(owner,self.b['id'],'problem')
        for role in ('booking','provider:p1'):
            with self.assertRaises(Rejected):self.bus.services.execute(role,'problem_queue',self.owner,{})

    def test_problem_form_binding_rejects_foreign_and_stale_selections(self):
        form=self.send('report a problem');selection=json.loads(form['metadata']['card_payload'])['submit_cta']['selection']
        self.assertIn('No new booking',self.send(json.dumps(dict(selection,problem='test')),owner='mallory')['text'])
        self.send('report a problem')
        self.assertIn('latest problem form',self.send(json.dumps(dict(selection,problem='test')))['text'])
        self.assertIn('recorded',self.send('report a problem: Synthetic issue')['text'])

    def test_problem_remains_possible_after_completion(self):
        self.send('complete service');self.assertIn('recorded',self.send('report a problem: Synthetic issue')['text'])
        self.assertIn('Problem report recorded',self.send('show what happened')['text'])

    def test_missing_report_key_fails_closed(self):
        p=Problems(self.store);p.report(self.owner,self.b['id'],'test')
        Path(self.store.path).with_suffix('.message-key').unlink()
        with self.assertRaises(Rejected):p.report(self.owner,self.b['id'],'another')

    def test_completion_is_explicit_owned_and_retry_safe(self):
        review=self.send(json.dumps(dict(action='completion_review',booking_id=self.b['id'])))
        selection=json.loads(review['metadata']['card_payload'])['approve_cta']['selection']
        self.assertEqual(self.store.booking(self.b['id'],self.owner)['state'],'confirmed')
        self.send(json.dumps(selection),owner='mallory')
        self.assertEqual(self.store.booking(self.b['id'],self.owner)['state'],'confirmed')
        self.send(json.dumps(selection));self.send(json.dumps(selection))
        self.assertEqual(sum(e['kind']=='service_completed' for e in self.store.timeline(self.owner,self.b['id'])),1)

    def test_cancel_actor_cannot_impersonate_another_provider(self):
        with self.assertRaises(Rejected):Payments(self.store,'mock').cancel(self.owner,self.b['id'],'provider:p2')
        self.assertEqual(self.store.booking(self.b['id'],self.owner)['state'],'confirmed')

    def test_status_actions_and_payment_labels(self):
        status=self.send('status');payload=json.loads(status['metadata']['card_payload'])
        self.assertIn('Simulated payment',status['text'])
        self.assertTrue({'completion_review','problem_form','compose_message'}<={x['selection']['action'] for x in payload['ctas']})
        self.send('complete service');payload=json.loads(self.send('status')['metadata']['card_payload'])
        self.assertTrue({'booking_history','problem_form'}<={x['selection']['action'] for x in payload['ctas']})

    def test_durable_notifications_keep_original_session_and_retry_failed_delivery(self):
        class Context:
            _session=UUID(int=0)
            sent=[]
            ok=False
            async def send(self,customer,message):
                self.sent.append((customer,self._session,message))
                return SimpleNamespace(status='delivered' if self.ok else 'failed')
        ctx=Context();asyncio.run(notify_bookings(self.store,ctx))
        self.assertEqual(ctx.sent[0][:2],('agent_customer',UUID(self.owner.rsplit(':',1)[1])))
        with self.store.connect() as db:self.assertEqual(db.execute('SELECT sent FROM booking_notices').fetchone()[0],0)
        self.clock.now+=31;ctx.ok=True;asyncio.run(notify_bookings(self.store,ctx))
        with self.store.connect() as db:self.assertEqual(db.execute('SELECT sent FROM booking_notices').fetchone()[0],1)
        asyncio.run(notify_bookings(self.store,ctx));self.assertEqual(len(ctx.sent),2)


class PilotBoundaries(unittest.TestCase):
    def setUp(self):
        tmp=tempfile.TemporaryDirectory();self.addCleanup(tmp.cleanup)
        self.clock=Clock();self.store=Store(Path(tmp.name)/'pilot.db',self.clock);self.store.seed()
        self.config=dict(provider_id='p4',service='plumbing',name='Synthetic pilot fixture',scope='One standard tap repair visit, labour only',exclusions='No parts or additional work',operator='Test operator',agreement_reference='SYNTHETIC TEST ONLY',permission_obtained=True,availability_confirmed=True,amount_paise=65000,city='bengaluru',area='indiranagar',pincodes=['560038'],slots=self.store.provider('p4')['slots'],checked_items=['Synthetic consent record','Synthetic price and scope agreement','Synthetic availability confirmation'],review_valid_until='2027-01-01')

    def configure(self):return import_pilot(self.store,self.config)
    def held(self):
        self.configure();self.job=dict(service='plumbing',city='bengaluru',area='indiranagar',slot=self.config['slots'][0],budget=80000)
        self.q=self.store.quote('alice','p4',self.job['slot'],job=self.job);self.b=self.store.hold('alice',self.q['id'])
        return self.b

    def test_import_requires_real_agreement_and_exact_checks(self):
        for changes in (dict(permission_obtained=False),dict(availability_confirmed=False),dict(checked_items=[]),dict(provider_id='p5'),dict(amount_paise=True),dict(slots=['2020-01-01T10:00:00+05:30'])):
            with self.subTest(changes=changes),self.assertRaises(Rejected):import_pilot(self.store,dict(self.config,**changes))

    def test_pilot_is_labelled_without_mock_badges_and_demo_capacity_disabled(self):
        self.held();choices,_=self.store.match(dict(self.job,slot=self.config['slots'][1]))
        self.assertEqual([p['id'] for p in choices],['p4'])
        self.assertEqual(self.q['scope'],self.config['scope']);self.assertEqual(self.q['amount'],65000)
        text=cards.shortlist([self.q],[])['text']
        self.assertIn('Real pilot business',text);self.assertIn('Manual review only',text);self.assertNotIn('mock registry',text)
        self.store.seed();self.assertEqual(self.store.provider('p4')['record_kind'],'pilot')
        self.assertFalse(self.store.provider('p5')['available'])

    def test_operator_acceptance_and_customer_approval_are_both_required(self):
        self.held();payment=Payments(self.store,'mock')
        with self.assertRaises(Rejected):payment.start('alice',self.b['id'])
        self.store.approve('alice',self.b['id'],self.q['id'])
        with self.assertRaisesRegex(Rejected,'Awaiting operator'):payment.start('alice',self.b['id'])
        accept(self.store,self.b['id'],'Test operator');accept(self.store,self.b['id'],'Test operator')
        self.assertEqual(payment.start('alice',self.b['id'])['booking']['state'],'confirmed')
        with self.assertRaises(Rejected):import_pilot(self.store,self.config)

    def test_acceptance_cannot_confirm_expired_hold_or_replace_consent(self):
        self.held();accept(self.store,self.b['id'],'Test operator')
        with self.assertRaises(Rejected):Payments(self.store,'mock').start('alice',self.b['id'])
        self.clock.now+=121
        with self.assertRaises(Rejected):accept(self.store,self.b['id'],'Test operator')

    def test_one_business_pilot_recovery_never_uses_fictional_alternatives(self):
        self.held();self.store.cancel('alice',self.b['id'],'provider:p4')
        choices,_=self.store.recovery('alice',self.b['id'],self.job)
        self.assertEqual(choices,[])

    def test_private_operator_export_is_exclusive_and_owner_only(self):
        path=Path(self.store.path).parent/'data'/'reports.json';write_private(path,[])
        if os.name!='nt':self.assertEqual(path.stat().st_mode&0o077,0)
        with self.assertRaises(FileExistsError):write_private(path,[])
        with self.assertRaises(Rejected):write_private(path.parent.parent/'public.json',[])


@unittest.skipUnless(importlib.util.find_spec('uagents'),'fetch extras required')
class PaymentProtocolAccess(Fixture):
    def setUp(self):
        super().setUp();self.mock_paid()
        from servicesetu.mesh import create_mesh
        reasoner=Reasoner();reasoner.key=None
        loop=asyncio.new_event_loop();asyncio.set_event_loop(loop);self.addCleanup(loop.close)
        with patch('servicesetu.mesh.seed_phrase',return_value='public-isolated-protocol-test'):
            self.bureau,self.agents,_=create_mesh(self.store,offline=True,reasoner=reasoner,payment_mode='mock')
        self.ctx=SimpleNamespace(session=UUID(self.owner.rsplit(':',1)[1]),send=__import__('unittest.mock',fromlist=['AsyncMock']).AsyncMock())

    def test_unbound_checkout_rejection_cannot_cancel_a_confirmed_booking(self):
        from uagents_core.contrib.protocols.payment import RejectPayment
        self.store.save_session(self.owner,dict(booking=self.b['id']))
        handler=self.agents['concierge']._signed_message_handlers[RejectPayment.build_schema_digest(RejectPayment)]
        asyncio.run(handler(self.ctx,'agent_customer',RejectPayment(reason='delayed old rejection')))
        self.assertEqual(self.store.booking(self.b['id'],self.owner)['state'],'confirmed')

    def test_commit_is_bound_to_customer_and_original_conversation(self):
        from uagents_core.contrib.protocols.payment import CommitPayment,Funds,CancelPayment
        msg=CommitPayment(reference=self.b['id'],funds=Funds(currency='INR',amount='699.00',payment_method='stripe'),recipient=self.agents['concierge'].address,transaction_id='cs_test_forged')
        handler=self.agents['concierge']._signed_message_handlers[CommitPayment.build_schema_digest(CommitPayment)]
        for sender,session in (('another_customer',self.ctx.session),('agent_customer',UUID(int=0))):
            self.ctx.session=session;asyncio.run(handler(self.ctx,sender,msg))
            self.assertIsInstance(self.ctx.send.call_args.args[1],CancelPayment)
        self.assertEqual(self.store.booking(self.b['id'],self.owner)['state'],'confirmed')

    def test_internal_workers_reject_a_customer_even_with_known_owner_and_booking(self):
        from servicesetu.mesh import Work,Result
        for role in ('booking','payment','provider:p1'):
            handler=self.agents[role]._signed_message_handlers[Work.build_schema_digest(Work)]
            asyncio.run(handler(self.ctx,'agent_customer',Work(action='cancel',owner=self.owner,data={'booking':self.b['id']})))
            result=self.ctx.send.call_args.args[1];self.assertIsInstance(result,Result);self.assertFalse(result.ok)
        self.assertEqual(self.store.booking(self.b['id'],self.owner)['state'],'confirmed')


class TransportAndPreflight(unittest.TestCase):
    def test_transient_reply_failure_retries_same_message_without_reexecuting_action(self):
        from unittest.mock import AsyncMock
        from servicesetu.transport import send_customer
        msg=object();ctx=SimpleNamespace(send=AsyncMock(side_effect=[SimpleNamespace(status='failed'),SimpleNamespace(status='delivered')]))
        with patch('servicesetu.transport.asyncio.sleep',new=AsyncMock()):result=asyncio.run(send_customer(ctx,'customer',msg))
        self.assertEqual(result.status,'delivered');self.assertEqual(ctx.send.call_count,2)
        self.assertTrue(all(call.args==('customer',msg) for call in ctx.send.call_args_list))

    def test_stripe_preflight_rejects_live_account_without_returning_private_balance(self):
        from servicesetu.stripe_check import check
        adapter=SimpleNamespace(stripe=Mock(return_value=SimpleNamespace(Balance=SimpleNamespace(retrieve=Mock(return_value=SimpleNamespace(livemode=True))))))
        with self.assertRaises(Rejected):check(adapter)
        adapter.stripe.return_value.Balance.retrieve.return_value.livemode=False
        self.assertIsNone(check(adapter))
