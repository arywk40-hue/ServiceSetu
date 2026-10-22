"""Twelve packages reuse trusted identity, approval and capacity boundaries."""
import asyncio
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from servicesetu.__main__ import main
from servicesetu.catalogue import SERVICES,detect_service,provider_amount
from servicesetu.conversation import Conversation
from servicesetu.core import Store,Rejected
from servicesetu.reasoning import Reasoner
from servicesetu.service import Services,LocalBus
from servicesetu.service_details import validate_details
from tests.test_proofs import Clock


class ExtendedCatalogue(unittest.TestCase):
    def setUp(self):
        tmp=tempfile.TemporaryDirectory();self.addCleanup(tmp.cleanup)
        self.path=Path(tmp.name)/'twelve.db'
        self.clock=Clock();self.store=Store(self.path,self.clock)
        self.store.seed(days=3,extended_catalogue=True)
        reasoner=Reasoner();reasoner.key=None
        self.conversation=Conversation(self.store,reasoner)
        self.services=Services(self.store,payment_mode='mock');self.bus=LocalBus(self.services)
        self.slot=self.store.provider('p1')['slots'][0]

    def send(self,text,owner='alice'):
        return asyncio.run(self.conversation.handle(owner,text,self.bus))

    def request(self,service,owner='alice',budget=5000):
        text={'mattress_cleaning':'mattress cleaning for two queen mattresses',
              'carpet_cleaning':'one carpet cleaning, synthetic, 8 by 6 feet',
              'refrigerator':'double-door refrigerator inspection, not cooling',
              'water_purifier':'RO+UV water purifier servicing, routine maintenance'}[service]
        return self.send(text+f' in Indiranagar Bengaluru {self.slot} under INR {budget}',owner)

    def quote(self,owner='alice'):
        return self.store.get_quote(self.store.session(owner)['quotes'][0],owner)

    def approve(self,owner):
        review=self.send('option 1',owner)
        approval=json.loads(review['metadata']['card_payload'])['approve_cta']['selection']
        bid=self.store.session(owner)['booking']
        self.assertEqual(self.store.booking(bid,owner)['payment_state'],'none')
        self.send(json.dumps(approval),owner)
        self.assertEqual(self.store.booking(bid,owner)['state'],'confirmed')
        return bid

    def test_all_new_packages_book_cancel_and_replace_with_new_approval(self):
        for service in ('mattress_cleaning','carpet_cleaning','refrigerator','water_purifier'):
            with self.subTest(service=service):
                reply=self.request(service,service)
                self.assertEqual(reply['metadata']['card_kind'],'carousel')
                original=self.quote(service)
                bid=self.approve(service)
                self.services.payments.cancel(service,bid,actor='provider:'+original['provider'])
                self.assertEqual(self.store.booking(bid,service)['payment_state'],'refunded')
                self.send('recover',service)
                replacement=self.quote(service)
                self.assertNotEqual(original['provider'],replacement['provider'])
                self.assertEqual(original['details'],replacement['details'])
                new=self.approve(service)
                history=self.send('show what happened',service)['text']
                self.assertIn('Replacement booking confirmed',history)
                self.assertIn('Provider cancelled',history)
                self.services.payments.cancel(service,new)

    def test_mattress_size_and_quantity_follow_up_preserve_budget(self):
        reply=self.send('mattress cleaning in Indiranagar Bengaluru tomorrow 10am under INR 2000')
        self.assertIn('mattress size',reply['text'])
        self.assertIn('How many',self.send('queen')['text'])
        reply=self.send('two')
        self.assertEqual(reply['metadata']['card_kind'],'carousel')
        self.assertEqual(self.quote()['amount'],159800)
        self.assertEqual(self.quote()['details'],{'size':'queen','quantity':2})
        self.assertEqual(self.store.session('alice')['job']['budget'],200000)

    def test_mixed_mattress_sizes_are_not_merged_into_one_quote(self):
        reply=self.send('mattress cleaning for one queen and one king mattress')
        self.assertIn('Mixed sizes',reply['text'])
        self.assertFalse(self.store.session('alice').get('quotes'))

    def test_mattress_quantity_total_controls_matching(self):
        self.send(f'mattress cleaning three king mattresses in Indiranagar Bengaluru {self.slot} under INR 2000')
        self.assertEqual(self.store.session('alice')['quotes'],[])

    def test_carpet_dimensions_and_material_are_requested_before_quotes(self):
        reply=self.send('one carpet cleaning in Indiranagar Bengaluru tomorrow 10am under INR 1000')
        self.assertIn('length in feet',reply['text'])
        self.assertIn('width in feet',self.send('8')['text'])
        self.assertIn('synthetic',self.send('6')['text'])
        reply=self.send('synthetic')
        self.assertEqual(reply['metadata']['card_kind'],'carousel')
        self.assertEqual(self.quote()['amount'],72000)
        self.assertIn('8 by 6 feet',self.quote()['scope'])

    def test_small_carpet_uses_minimum_visit_price(self):
        self.send(f'one carpet cleaning synthetic 2 by 2 feet in Indiranagar Bengaluru {self.slot} under INR 1000')
        self.assertEqual(self.quote()['amount'],49900)

    def test_carpet_decimal_price_rounds_up_to_whole_paise(self):
        self.send(f'one carpet cleaning synthetic 7.15 by 6.15 feet in Indiranagar Bengaluru {self.slot} under INR 1000')
        self.assertEqual(self.quote()['amount'],65959)

    def test_carpet_area_limit_can_be_corrected_with_a_short_answer(self):
        reply=self.send(f'one carpet cleaning synthetic 20 by 10 feet in Indiranagar Bengaluru {self.slot} under INR 3000')
        self.assertIn('150 square feet',reply['text'])
        reply=self.send('10')
        self.assertEqual(reply['metadata']['card_kind'],'carousel')
        self.assertEqual(self.quote()['details']['length_ft'],10)

    def test_unsupported_carpet_material_and_bad_dimensions_cannot_quote(self):
        for details in ({'length_ft':8,'width_ft':6,'material':'wool'},
                        {'length_ft':True,'width_ft':6,'material':'synthetic'},
                        {'length_ft':-8,'width_ft':6,'material':'synthetic'},
                        {'length_ft':7.123,'width_ft':6,'material':'synthetic'}):
            with self.subTest(details=details),self.assertRaises(ValueError):
                validate_details('carpet_cleaning',details)

    def test_refrigerator_collects_type_and_problem_before_quotes(self):
        reply=self.send('refrigerator inspection in Indiranagar Bengaluru tomorrow 10am under INR 700')
        self.assertIn('single-door',reply['text'])
        self.assertIn('What problem',self.send('double door')['text'])
        reply=self.send('It is not cooling')
        self.assertEqual(reply['metadata']['card_kind'],'carousel')
        self.assertEqual(self.quote()['amount'],49900)
        self.assertIn('double-door',self.quote()['scope'])
        self.assertIn('refrigerant',self.quote()['exclusions'])

    def test_refrigerator_repair_request_offers_inspection_without_promising_repair(self):
        reply=self.send('repair my double-door fridge, it is not cooling')
        self.assertIn('refrigerator inspection',reply['text'])
        self.assertIn('diagnosis only',reply['text'])
        self.assertFalse(self.store.session('alice').get('quotes'))

    def test_purifier_type_and_purpose_are_required(self):
        reply=self.send('water purifier servicing in Indiranagar Bengaluru tomorrow 10am under INR 1000')
        self.assertIn('Which purifier type',reply['text'])
        self.assertIn('routine servicing',self.send('RO+UV')['text'])
        reply=self.send('routine maintenance')
        self.assertEqual(reply['metadata']['card_kind'],'carousel')
        self.assertEqual(self.quote()['details']['purifier_type'],'RO+UV')
        self.assertEqual(self.quote()['amount'],69900)
        self.assertIn('water-quality certification',self.quote()['exclusions'])

    def test_unrecognised_purifier_type_is_not_assumed_to_be_ro(self):
        reply=self.send('gravity water purifier servicing, routine maintenance')
        self.assertIn('other purifier types',reply['text'])
        self.assertFalse(self.store.session('alice').get('quotes'))

    def test_cleaning_and_appliance_capacity_is_shared_across_new_packages(self):
        for service,other in (('mattress_cleaning','carpet_cleaning'),('refrigerator','water_purifier')):
            with self.subTest(service=service):
                self.request(service,service);quote=self.quote(service)
                self.store.hold(service,quote['id'])
                self.request(other,other)
                self.assertTrue(all(self.store.get_quote(qid,other)['provider']!=quote['provider']
                                    for qid in self.store.session(other)['quotes']))

    def test_extended_catalogue_adds_no_provider_identities(self):
        self.assertEqual(len(self.store.providers()),16)
        self.assertEqual(len(SERVICES),12)
        reply=self.send('show appliance services')
        items=json.loads(reply['metadata']['card_payload'])['items']
        self.assertEqual({item['id'] for item in items},{'ac','washing_machine','refrigerator','water_purifier'})
        root=self.send('show services')
        groups=json.loads(root['metadata']['card_payload'])['items']
        self.assertEqual({item['id'] for item in groups},{'cleaning','appliances','repairs','assembly'})
        selection=next(item for item in groups if item['id']=='cleaning')['primary_cta']['selection']
        reply=self.send(json.dumps(selection))
        choices=json.loads(reply['metadata']['card_payload'])['items']
        self.assertEqual({item['id'] for item in choices},{'cleaning','kitchen_cleaning','sofa_cleaning','mattress_cleaning','carpet_cleaning'})

    def test_extended_copy_preserves_original_history_and_prices(self):
        source=self.path.parent/'source.db';store=Store(source,self.clock);store.seed(full_catalogue=True)
        quote=store.quote('existing','p7',self.slot);held=store.hold('existing',quote['id'])
        before=store.providers();target=self.path.parent/'upgrade.db'
        with patch('sys.argv',['servicesetu','seed-demo','--db',str(target),'--extended-catalogue','--from-db',str(source)]):main()
        upgraded=Store(target,self.clock)
        self.assertEqual(store.providers(),before)
        self.assertEqual(upgraded.booking(held['id'],'existing'),store.booking(held['id'],'existing'))
        self.assertIn('mattress_cleaning',upgraded.provider('p7')['offerings'])
        self.assertIn('refrigerator',upgraded.provider('p13')['offerings'])
        self.assertEqual(upgraded.provider('p7')['offerings']['sofa_cleaning'],24900)
        self.assertFalse(upgraded.slot_free('p7',self.slot))

    def test_explicit_service_detection_handles_every_new_category(self):
        for text,service in [('mattress cleaning','mattress_cleaning'),('clean one rug','carpet_cleaning'),('fridge repair','refrigerator'),('RO purifier service','water_purifier')]:
            with self.subTest(text=text):self.assertEqual(detect_service(text),service)

    def test_core_rejects_incomplete_appliance_details(self):
        for service in ('refrigerator','water_purifier'):
            job=dict(service=service,package=SERVICES[service]['package'],city='bengaluru',area='indiranagar',slot=self.slot,budget=100000)
            with self.subTest(service=service),self.assertRaises(Rejected):self.store.match(job)
