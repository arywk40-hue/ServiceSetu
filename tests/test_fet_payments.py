"""Dorado payment tests use ledger doubles; they do not move real tokens."""
import tempfile
import unittest
import asyncio
import json
from decimal import localcontext
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from cosmpy.aerial.wallet import LocalWallet
from uagents_core.contrib.protocols.payment import Funds

from servicesetu.core import Store,Rejected
from servicesetu.fet_payments import (DENOM,NETWORK,fet_amount,native_address,transaction_hash,
                                       verify_incoming,verify_refund,request_message)
from servicesetu.payments import Payments
from servicesetu.fet_wallet import recipient_address
from servicesetu.conversation import Conversation
from servicesetu.reasoning import Reasoner
from servicesetu.service import Services,LocalBus
from tests.test_proofs import Clock


def address():return str(LocalWallet.generate().address())


class Ledger:
    def __init__(self,tx):self.tx=tx;self.queried=[]
    def query_tx(self,tx_hash):self.queried.append(tx_hash);return self.tx


class FetPaymentTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.clock=Clock();self.store=Store(Path(self.tmp.name)/'fet.db',self.clock);self.store.seed()
        self.owner='customer:session-123';self.quote=self.store.quote(self.owner,'p1',self.store.provider('p1')['slots'][0])
        self.booking=self.store.hold(self.owner,self.quote['id']);self.recipient=address();self.payer=address()
        self.adapter=Payments(self.store,'fet_testnet',fet_recipient=self.recipient)
        self.tx_hash='A'*64

    def start(self):
        amount,atomic=fet_amount('0.1')
        self.store.approve(self.owner,self.booking['id'],self.quote['id'],payment_terms={
            'quote_id':self.quote['id'],'network':NETWORK,'denom':DENOM,'token_amount':amount,'atomic_amount':str(atomic)})
        with patch.dict('os.environ',{'FET_TEST_AMOUNT':'0.9'}):return self.adapter.start(self.owner,self.booking['id'])

    def commit(self,**overrides):
        args={'owner':self.owner,'bid':self.booking['id'],'transaction':self.tx_hash,
              'funds':Funds(currency='FET',amount='0.100000000000000000',payment_method='fet_direct'),
              'recipient':self.recipient,'metadata':{'buyer_fet_wallet':self.payer,'fet_network':NETWORK,'mainnet':'false'},
              'reference':self.booking['id']}
        args.update(overrides)
        return self.adapter.commit_fet(**args)

    def successful_transfer(self,sender=None,recipient=None,amount=None):
        attrs={'sender':sender or self.payer,'recipient':recipient or self.recipient,
               'amount':f"{amount or 100000000000000000}{DENOM}"}
        return SimpleNamespace(hash=self.tx_hash,height=1,code=0,events={'transfer':attrs},logs=[],is_successful=lambda:True)

    def test_amount_is_decimal_exact_and_address_is_native_fetch(self):
        self.assertEqual(fet_amount('0.1'),('0.100000000000000000',100000000000000000))
        self.assertTrue(native_address(self.recipient));self.assertFalse(native_address('agent1not_a_wallet'))
        self.assertTrue(recipient_address('synthetic-seed-for-tests-only').startswith('fetch1'))
        for value in ('0','-1','1e-3','0.0000000000000000001','NaN'):
            with self.subTest(value=value),self.assertRaises(Rejected):fet_amount(value)

    def test_amount_remains_exact_independent_of_decimal_context(self):
        with localcontext() as context:
            context.prec=6
            self.assertEqual(fet_amount('123456789012.123456789012345678'),
                ('123456789012.123456789012345678',123456789012123456789012345678))

    def test_mainnet_and_other_network_are_refused(self):
        with patch.dict('os.environ',{'FET_USE_TESTNET':'false'}),self.assertRaisesRegex(Rejected,'mainnet'):
            Payments(self.store,'fet_testnet',fet_recipient=self.recipient)
        with patch.dict('os.environ',{'FET_NETWORK':'fetchhub-4'}),self.assertRaisesRegex(Rejected,'Dorado'):
            Payments(self.store,'fet_testnet',fet_recipient=self.recipient)
        with self.assertRaises(Rejected):Payments(self.store,'fet_mainnet',fet_recipient=self.recipient)

    def test_invoice_created_only_after_approval_and_retries_reuse_it(self):
        with self.assertRaises(Rejected):self.adapter.start(self.owner,self.booking['id'])
        with self.store.connect() as db:self.assertEqual(db.execute('select count(*) from payments').fetchone()[0],0)
        first=self.start();second=self.adapter.start(self.owner,self.booking['id'])
        self.assertEqual(first['fet_invoice'],second['fet_invoice'])
        invoice=first['fet_invoice']
        self.assertEqual((invoice['booking_id'],invoice['quote_id'],invoice['customer'],invoice['session']),
                         (self.booking['id'],self.quote['id'],'customer','session-123'))
        self.assertEqual((invoice['network'],invoice['recipient'],invoice['token_amount'],invoice['denom']),
                         (NETWORK,self.recipient,'0.100000000000000000',DENOM))
        with self.store.connect() as db:self.assertEqual(db.execute('select count(*) from payments').fetchone()[0],1)

    def test_fet_amount_is_shown_before_approval_and_payment_request_uses_official_fields(self):
        q=self.quote;state={'quotes':[q['id']],'job':{'service':'ac','city':'bengaluru','area':'indiranagar','slot':q['slot'],'budget':100000}}
        self.store.save_session(self.owner,state)
        bus=LocalBus(Services(self.store,'fet_testnet',fet_recipient=self.recipient))
        conv=Conversation(self.store,Reasoner(),payment_mode='fet_testnet')
        with patch.dict('os.environ',{'FET_TEST_AMOUNT':'0.25'}):
            selected=asyncio.run(conv.handle(self.owner,json.dumps({'action':'select','quote_id':q['id']}),bus))
            review=asyncio.run(conv.handle(self.owner,'skip for now',bus))
            self.assertIn('0.250000000000000000 FET',review['text'])
            self.assertIn('no INR-to-FET conversion',review['text'])
            self.assertNotIn('payment',review)
        payload=json.loads(review['metadata']['card_payload'])
        with patch.dict('os.environ',{'FET_TEST_AMOUNT':'0.9'}):
            approved=asyncio.run(conv.handle(self.owner,json.dumps(payload['approve_cta']['selection']),bus))
        invoice=approved['payment']['fet_invoice']
        self.assertEqual(invoice['token_amount'],'0.250000000000000000')
        msg=request_message(invoice,self.clock())
        self.assertEqual(msg.accepted_funds[0].currency,'FET')
        self.assertEqual(msg.accepted_funds[0].amount,'0.250000000000000000')
        self.assertEqual(msg.accepted_funds[0].payment_method,'fet_direct')
        self.assertEqual(msg.recipient,self.recipient)
        self.assertTrue(msg.recipient.startswith('fetch1'))
        self.assertEqual(msg.reference,invoice['booking_id'])
        self.assertEqual(msg.metadata['fet_network'],'dorado-1')
        self.assertEqual(msg.metadata['mainnet'],'false')

    def test_commit_verifies_dorado_transfer_and_confirms_once(self):
        self.start()
        transfer={'sender':self.payer,'recipient':self.recipient,'amount':'100000000000000000','denom':DENOM}
        with patch('servicesetu.payments.verify_incoming',return_value=transfer) as verify:
            one=self.commit();two=self.commit()
        verify.assert_called_once()
        self.assertEqual((one['state'],one['payment_state']),('confirmed','paid'))
        self.assertEqual((two['state'],two['payment_state']),('confirmed','paid'))
        with self.store.connect() as db:
            self.assertEqual(db.execute("select count(*) from events where kind='booking_confirmed'").fetchone()[0],1)
            self.assertEqual(db.execute('select payer_wallet from payments').fetchone()[0],self.payer)

    def test_wrong_amount_currency_method_recipient_network_and_hash_rejected(self):
        self.start()
        bad=[{'funds':Funds(currency='FET',amount='0.11',payment_method='fet_direct')},
             {'funds':Funds(currency='FET',amount='0.100000000000000000',payment_method='other')},
             {'funds':Funds(currency='INR',amount='0.100000000000000000',payment_method='fet_direct')},
             {'recipient':address()}, {'reference':'another-booking'},
             {'metadata':{'buyer_fet_wallet':self.payer,'fet_network':'fetchhub-4','mainnet':'false'}},
             {'metadata':{'buyer_fet_wallet':'agent1messageaddress','fet_network':NETWORK}},
             {'transaction':'not-a-chain-hash'}]
        for changes in bad:
            with self.subTest(changes=changes),self.assertRaises(Rejected):self.commit(**changes)
        self.assertEqual(self.store.booking(self.booking['id'],self.owner)['state'],'held')

    def test_equivalent_decimal_and_normalized_transaction_retry_are_idempotent(self):
        self.start()
        transfer={'sender':self.payer,'recipient':self.recipient,'amount':'100000000000000000','denom':DENOM}
        with patch('servicesetu.payments.verify_incoming',return_value=transfer) as verify:
            self.commit(funds=Funds(currency='FET',amount='0.1',payment_method='fet_direct'))
            result=self.commit(transaction=self.tx_hash.lower())
        verify.assert_called_once()
        self.assertEqual(result['payment_state'],'paid')

    def test_foreign_customer_or_session_cannot_commit_invoice(self):
        self.start()
        with patch('servicesetu.payments.verify_incoming') as verify:
            for owner in ('other-customer:session-123','customer:other-session'):
                with self.subTest(owner=owner),self.assertRaises(Rejected):self.commit(owner=owner)
            verify.assert_not_called()

    def test_wrong_sender_recipient_or_amount_on_chain_rejected(self):
        self.start()
        for tx in (self.successful_transfer(sender=address()),self.successful_transfer(recipient=address()),
                   self.successful_transfer(amount=999)):
            with self.assertRaises(Rejected):verify_incoming(self.tx_hash,sender=self.payer,recipient=self.recipient,
                amount_atomic=100000000000000000,ledger=Ledger(tx))
        self.assertEqual(self.store.booking(self.booking['id'],self.owner)['state'],'held')

    def test_one_transaction_cannot_pay_a_second_booking(self):
        self.start();transfer={'sender':self.payer,'recipient':self.recipient,'amount':'100000000000000000','denom':DENOM}
        with patch('servicesetu.payments.verify_incoming',return_value=transfer):self.commit()
        other_owner='other-customer:other-session';other_quote=self.store.quote(other_owner,'p2',self.store.provider('p2')['slots'][0])
        other_booking=self.store.hold(other_owner,other_quote['id'])
        amount,atomic=fet_amount('0.1')
        self.store.approve(other_owner,other_booking['id'],other_quote['id'],payment_terms={
            'quote_id':other_quote['id'],'network':NETWORK,'denom':DENOM,'token_amount':amount,'atomic_amount':str(atomic)})
        self.adapter.start(other_owner,other_booking['id'])
        with patch('servicesetu.payments.verify_incoming',return_value=transfer),self.assertRaisesRegex(Rejected,'already used'):
            self.adapter.commit_fet(owner=other_owner,bid=other_booking['id'],transaction=self.tx_hash,
                funds=Funds(currency='FET',amount=amount,payment_method='fet_direct'),recipient=self.recipient,
                metadata={'buyer_fet_wallet':self.payer,'fet_network':NETWORK,'mainnet':'false'},reference=other_booking['id'])

    def test_network_query_must_be_dorado(self):
        self.start()
        with patch('cosmpy.aerial.client.LedgerClient') as client,patch('cosmpy.aerial.client.NetworkConfig') as network:
            network.fetchai_dorado_testnet.return_value=SimpleNamespace(chain_id='fetchhub-4')
            with self.assertRaisesRegex(Rejected,'mainnet'):
                verify_incoming(self.tx_hash,sender=self.payer,recipient=self.recipient,amount_atomic=100000000000000000)
            client.assert_not_called()

    def test_expired_hold_never_confirms_and_requires_verified_refund(self):
        self.start();self.clock.now+=121
        transfer={'sender':self.payer,'recipient':self.recipient,'amount':'100000000000000000','denom':DENOM}
        with patch('servicesetu.payments.verify_incoming',return_value=transfer):result=self.commit()
        self.assertEqual((result['state'],result['payment_state']),('cancelled','refund_required'))
        self.assertEqual(self.store.booking(self.booking['id'],self.owner)['payment_state'],'refund_required')
        refund_hash='B'*64
        transfer={'sender':self.recipient,'recipient':self.payer,'amount':'100000000000000000','denom':DENOM}
        with patch('servicesetu.payments.verify_refund',return_value=transfer):
            refunded=self.adapter.record_fet_refund(self.owner,self.booking['id'],refund_hash)
        self.assertEqual(refunded['payment_state'],'refunded')
        with self.store.connect() as db:
            self.assertEqual(db.execute('select refund_external from payments').fetchone()[0],refund_hash)
            self.assertEqual(db.execute("select count(*) from events where kind='fet_testnet_refunded'").fetchone()[0],1)

    def test_invoice_deadline_cannot_be_bypassed_while_hold_is_active(self):
        with patch.dict('os.environ',{'FET_PAYMENT_DEADLINE_SECONDS':'10'}):self.start()
        self.clock.now+=11
        self.assertGreater(self.store.booking(self.booking['id'],self.owner)['hold_until'],self.clock())
        transfer={'sender':self.payer,'recipient':self.recipient,'amount':'100000000000000000','denom':DENOM}
        with patch('servicesetu.payments.verify_incoming',return_value=transfer):result=self.commit()
        self.assertEqual((result['state'],result['payment_state']),('cancelled','refund_required'))

    def test_provider_confirmation_failure_never_confirms_received_funds(self):
        self.start()
        provider=self.store.provider('p1');provider['available']=False
        with self.store.tx() as db:db.execute('UPDATE providers SET payload=? WHERE id=?',(json.dumps(provider),'p1'))
        transfer={'sender':self.payer,'recipient':self.recipient,'amount':'100000000000000000','denom':DENOM}
        with patch('servicesetu.payments.verify_incoming',return_value=transfer):result=self.commit()
        self.assertEqual((result['state'],result['payment_state']),('cancelled','refund_required'))

    def test_fet_refund_verification_requires_the_exact_reverse_transfer(self):
        self.start();transfer={'sender':self.payer,'recipient':self.recipient,'amount':'100000000000000000','denom':DENOM}
        with patch('servicesetu.payments.verify_incoming',return_value=transfer):self.commit()
        self.adapter.cancel(self.owner,self.booking['id'])
        refund_hash='D'*64
        wrong={'sender':address(),'recipient':self.payer,'amount':'100000000000000000','denom':DENOM}
        with patch('servicesetu.payments.verify_refund',side_effect=Rejected('wrong refund transfer')),self.assertRaises(Rejected):
            self.adapter.record_fet_refund(self.owner,self.booking['id'],refund_hash)
        self.assertEqual(self.store.booking(self.booking['id'],self.owner)['payment_state'],'refund_required')

    def test_cancellation_never_marks_onchain_refund_complete_by_itself(self):
        self.start();transfer={'sender':self.payer,'recipient':self.recipient,'amount':'100000000000000000','denom':DENOM}
        with patch('servicesetu.payments.verify_incoming',return_value=transfer):self.commit()
        result=self.adapter.cancel(self.owner,self.booking['id'])
        self.assertEqual((result['state'],result['payment_state']),('cancelled','refund_required'))

    def test_transfer_verifier_requires_success_exact_hash_and_exact_amount(self):
        good=self.successful_transfer();ledger=Ledger(good)
        self.assertEqual(verify_incoming(self.tx_hash,sender=self.payer,recipient=self.recipient,
                         amount_atomic=100000000000000000,ledger=ledger)['amount'],str(100000000000000000))
        for tx in (SimpleNamespace(hash=self.tx_hash,events={},logs=[],is_successful=lambda:True),
                   SimpleNamespace(hash='C'*64,events={'transfer':good.events['transfer']},logs=[],is_successful=lambda:True),
                   SimpleNamespace(hash=self.tx_hash,events={'transfer':good.events['transfer']},logs=[],is_successful=lambda:False)):
            with self.subTest(tx=tx),self.assertRaises(Rejected):
                verify_refund(self.tx_hash,sender=self.recipient,recipient=self.payer,amount_atomic=100000000000000000,ledger=Ledger(tx))


if __name__=='__main__':unittest.main()
