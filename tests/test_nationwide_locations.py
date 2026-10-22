from tests.flows import with_address
"""India-wide intake must not imply India-wide provider availability."""
import asyncio
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch,AsyncMock

from servicesetu.__main__ import main
from servicesetu.core import Store,Rejected
from servicesetu.conversation import Conversation
from servicesetu.coverage import covers,requires_pin
from servicesetu.locations import canonical,pin_code,country_code,mentions
from servicesetu.reasoning import Reasoner,offline_parse
from servicesetu.service import Services,LocalBus
from servicesetu import cards
from tests.test_proofs import Clock


class NationwideLocations(unittest.TestCase):
    def setUp(self):
        tmp=tempfile.TemporaryDirectory();self.addCleanup(tmp.cleanup)
        self.path=Path(tmp.name)/'india.db';self.clock=Clock()
        self.store=Store(self.path,self.clock);self.store.seed(days=3,nationwide_demo=True)
        self.reasoner=Reasoner();self.reasoner.key=None
        self.conversation=Conversation(self.store,self.reasoner)
        self.services=Services(self.store,payment_mode='mock');self.bus=LocalBus(self.services)
        self.slot=self.store.provider('p1')['slots'][0]
        self.job=dict(service='ac',city='mumbai',area='powai',pincode='400076',slot=self.slot,budget=100000)

    def send(self,text):return asyncio.run(with_address(self.conversation,'alice',text,self.bus))

    def search(self,**changes):
        return self.send(json.dumps(dict(self.job,action='search',budget_rupees=1000,**changes)))

    def payload(self):
        return self.store.get_quote(self.store.session('alice')['quotes'][0],'alice')

    def write_provider(self,provider):
        with self.store.tx() as db:db.execute('UPDATE providers SET payload=? WHERE id=?',(json.dumps(provider),provider['id']))

    def test_unknown_indian_places_are_accepted_without_a_whitelist(self):
        for city,area in [('Palanpur','Abu Highway'),('Rourkela','Sector 6'),('राउरकेला','सेक्टर ६')]:
            with self.subTest(city=city):
                result=self.store.normalize_job(dict(self.job,city=city,area=area,pincode='123456'))
                self.assertEqual(result['city'],canonical(city,'city'))
                self.assertEqual(result['area'],canonical(area,'area'))
                self.assertEqual(self.store.match(result)[0],[])

    def test_aliases_and_case_do_not_create_new_places(self):
        self.assertEqual(canonical(' BOMBAY ','city'),'mumbai')
        self.assertEqual(canonical('BANGALORE','city'),'bengaluru')
        self.assertEqual(canonical('  Vaishali   Nagar ','area'),'vaishali nagar')
        self.assertEqual(canonical('Mangaluru','city'),'mangaluru')

    def test_pin_validation_checks_format_without_claiming_postal_lookup(self):
        self.assertEqual(mentions('AC in Powai Mumbai PIN 400076 2026-10-25T10:00:00+05:30 under INR 1000')['pincode'],'400076')
        self.assertEqual(pin_code('400 076'),'400076')
        self.assertEqual(pin_code(400076),'400076')
        for value in ('40007','4000767','000000',True,400076.0,'ABC076'):
            with self.subTest(value=value):self.assertIsNone(pin_code(value))
        self.assertEqual(pin_code('123456'),'123456')

    def test_foreign_country_and_malformed_pin_are_rejected_by_core(self):
        for change in ({'country':'US'},{'pincode':'12345'},{'pincode':True},{'city':None},{'area':[]}):
            with self.subTest(change=change),self.assertRaises(Rejected):self.store.normalize_job(dict(self.job,**change))
        self.assertEqual(country_code('भारत'),'IN')

    def test_default_demo_never_returns_bengaluru_providers_for_mumbai(self):
        store=Store(self.path.parent/'legacy.db',self.clock);store.seed()
        choices,excluded=store.match(self.job)
        self.assertEqual(choices,[])
        self.assertTrue(all('coverage' in row['reason'] for row in excluded))
        self.assertEqual(store.available_slots(self.job),[])
        with self.assertRaises(Rejected):store.quote('alice','p1',self.slot,job=self.job)

    def test_legacy_indiranagar_requests_work_with_or_without_its_demo_pin(self):
        store=Store(self.path.parent/'legacy.db',self.clock);store.seed()
        job=dict(self.job,city='bengaluru',area='indiranagar')
        job.pop('pincode')
        self.assertTrue(store.match(job)[0])
        self.assertTrue(store.match(dict(job,pincode='560038'))[0])
        self.assertEqual(store.match(dict(job,pincode='400076'))[0],[])

    def test_declared_city_locality_and_pin_must_all_match(self):
        provider=self.store.provider('p1')
        self.assertTrue(covers(provider,self.job))
        for change in ({'city':'delhi'},{'area':'bandra'},{'pincode':'400072'},{'country':'US'}):
            with self.subTest(change=change):self.assertFalse(covers(provider,dict(self.job,**change)))

    def test_invalid_or_empty_coverage_fails_closed(self):
        provider=self.store.provider('p1')
        for value in ([],{},[{'city':'mumbai'}],[{'city':'mumbai','areas':['*'],'pincodes':['400076']}],
                      [{'city':'mumbai','areas':['powai'],'pincodes':'400076'}],
                      [{'country':'US','city':'mumbai','areas':['powai'],'pincodes':['400076']}]):
            with self.subTest(value=value):self.assertFalse(covers(dict(provider,coverage=value),self.job))

    def test_new_location_without_pin_can_find_providers(self):
        reply=self.send('AC service in Powai, Mumbai tomorrow 10am under INR 1000')
        self.assertEqual(reply['metadata']['card_kind'],'carousel')
        state=self.store.session('alice')
        self.assertEqual(state['job']['budget'],100000)
        self.assertEqual(state['job']['slot'],self.slot)
        self.assertNotIn('pincode',self.payload()['location'])

    def test_unserved_location_is_retained_with_specific_coverage_response(self):
        reply=self.search(city='Jaipur',area='Vaishali Nagar',pincode='302021')
        self.assertIn('Your location was accepted',reply['text'])
        self.assertIn('No onboarded demo provider',reply['text'])
        self.assertNotIn('raise',reply['text'].lower())
        self.assertEqual(self.store.session('alice')['partial_job']['city'],'jaipur')
        with self.store.connect() as db:
            self.assertEqual(db.execute("SELECT count(*) FROM bookings WHERE state IN ('held','confirmed')").fetchone()[0],0)
            self.assertEqual(db.execute('SELECT count(*) FROM payments').fetchone()[0],0)

    def test_city_correction_clears_old_locality_and_pin(self):
        self.store.save_session('alice',{'partial_job':dict(self.job)})
        reply=self.send('Actually Pune')
        self.assertIn('your area',reply['text'])
        partial=self.store.session('alice')['partial_job']
        self.assertIsNone(partial.get('area'));self.assertIsNone(partial.get('pincode'))
        reply=self.send('Kothrud')
        self.assertIn('Your location was accepted',reply['text'])
        reply=self.send('411038')
        self.assertIn('Your location was accepted',reply['text'])
        self.assertEqual(self.store.session('alice')['job']['budget'],100000)

    def test_unknown_city_and_locality_can_be_given_as_bare_followups(self):
        self.send('AC service tomorrow 10am under INR 1000')
        self.send('Palanpur')
        reply=self.send('Abu Highway')
        self.assertIn('Your location was accepted',reply['text'])
        reply=self.send('385001')
        self.assertIn('Your location was accepted',reply['text'])
        self.assertEqual(self.store.session('alice')['job']['city'],'palanpur')
        self.assertEqual(self.store.session('alice')['job']['area'],'abu highway')

    def test_location_details_survive_service_specific_followup_questions(self):
        self.send('sofa cleaning in Powai Mumbai PIN 400076 tomorrow 10am under INR 1000')
        self.send('three seats');reply=self.send('fabric')
        self.assertEqual(reply['metadata']['card_kind'],'carousel')
        self.assertEqual(self.payload()['location']['pincode'],'400076')
        self.assertEqual(self.payload()['service'],'sofa_cleaning')

    def test_pin_correction_cannot_change_budget_or_appointment(self):
        self.reasoner.parse=AsyncMock(return_value=dict(self.job,budget=1,slot='2030-01-01T10:00:00+05:30'))
        for text in ('400076','PIN 400076','pincode: 400076'):
            with self.subTest(text=text):
                self.store.save_session('alice',{'partial_job':dict(self.job,pincode=None)})
                reply=self.send(text)
                self.assertEqual(reply['metadata']['card_kind'],'carousel')
                self.reasoner.parse.assert_not_called()
                self.assertEqual(self.store.session('alice')['job']['budget'],100000)
                self.assertEqual(self.store.session('alice')['job']['slot'],self.slot)

    def test_close_locality_typo_requires_confirmation_and_does_not_pay(self):
        reply=self.send('AC service in Pawai Mumbai PIN 400076 tomorrow 10am under INR 1000')
        self.assertIn('Did you mean Powai, Mumbai',reply['text'])
        reply=self.send('yes')
        self.assertEqual(reply['metadata']['card_kind'],'carousel')
        with self.store.connect() as db:self.assertEqual(db.execute('SELECT count(*) FROM payments').fetchone()[0],0)

    def test_postal_code_is_not_extracted_from_a_large_budget(self):
        parsed=offline_parse('AC service in Powai Mumbai tomorrow 10am under INR 100000',self.clock())
        self.assertNotIn('pincode',parsed)
        self.assertEqual(parsed['budget'],10000000)

    def test_explicit_labels_preserve_places_outside_aliases(self):
        result=mentions('city: Rourkela; locality: Sector 6; PIN: 769006')
        self.assertEqual(result['city'],'Rourkela')
        self.assertEqual(result['area'],'Sector 6')
        self.assertEqual(result['pincode'],'769006')

    def test_quote_and_review_bind_requested_location(self):
        self.search()
        quote=self.payload();reply=self.send('option 1')
        self.assertIn('Powai, Mumbai',reply['text']);self.assertIn('400076',reply['text'])
        self.assertNotIn('Indiranagar',reply['text'])
        approval=json.loads(reply['metadata']['card_payload'])['approve_cta']['selection']
        self.send(json.dumps(approval))
        bid=self.store.session('alice')['booking']
        self.assertEqual(self.store.booking(bid,'alice')['state'],'confirmed')
        self.assertEqual(quote['location']['city'],'mumbai')

    def test_withdrawn_coverage_is_rechecked_at_hold_and_payment(self):
        quote=self.store.quote('alice','p1',self.slot,job=self.job)
        provider=self.store.provider('p1');original=provider['coverage'];provider['coverage']=[];self.write_provider(provider)
        with self.assertRaises(Rejected):self.store.hold('alice',quote['id'])
        provider['coverage']=original;self.write_provider(provider)
        held=self.store.hold('alice',quote['id']);self.store.approve('alice',held['id'],quote['id'])
        provider['coverage']=[];self.write_provider(provider)
        with self.assertRaises(Rejected):self.store.begin_payment('alice',held['id'],'not-paid')

    def test_recovery_cannot_switch_city_or_pin_even_if_both_are_covered(self):
        self.search();review=self.send('option 1')
        self.send(json.dumps(json.loads(review['metadata']['card_payload'])['approve_cta']['selection']))
        bid=self.store.session('alice')['booking'];self.services.payments.cancel('alice',bid,actor='provider:p1')
        other=dict(self.job,city='bengaluru',area='indiranagar',pincode='560038')
        with self.assertRaises(Rejected):self.store.recovery('alice',bid,other)
        quote=self.store.quote('alice','p2',self.slot,job=other)
        with self.assertRaises(Rejected):self.store.hold('alice',quote['id'],recovery_of=bid)
        choices,_=self.store.recovery('alice',bid,self.job)
        self.assertTrue(choices)

    def test_shared_company_capacity_applies_across_cities(self):
        quote=self.store.quote('alice','p1',self.slot,job=self.job);self.store.hold('alice',quote['id'])
        other=dict(self.job,city='bengaluru',area='indiranagar',pincode='560038')
        with self.assertRaises(Rejected):self.store.quote('bob','p1',self.slot,job=other)

    def test_nationwide_seed_reuses_all_existing_identities(self):
        self.assertEqual(len(self.store.providers()),16)
        self.assertTrue(all(len(p['coverage'])==2 for p in self.store.providers()))

    def test_copy_upgrade_preserves_bookings_and_original_coverage(self):
        source=self.path.parent/'source.db';store=Store(source,self.clock);store.seed(extended_catalogue=True)
        quote=store.quote('existing','p1',self.slot);held=store.hold('existing',quote['id'])
        before=store.providers();target=self.path.parent/'upgrade.db'
        with patch('sys.argv',['servicesetu','seed-demo','--db',str(target),'--nationwide-demo','--from-db',str(source)]):main()
        upgraded=Store(target,self.clock)
        self.assertEqual(store.providers(),before)
        self.assertEqual(upgraded.booking(held['id'],'existing'),store.booking(held['id'],'existing'))
        self.assertEqual(len(upgraded.providers()),16)
        self.assertTrue(upgraded.match(self.job)[0])

    def test_custom_provider_coverage_is_not_expanded_by_demo_upgrade(self):
        provider=self.store.provider('p1');provider['coverage']=[];self.write_provider(provider)
        self.store.enable_demo_coverage()
        self.assertEqual(self.store.provider('p1')['coverage'],[])

    def test_form_collects_city_locality_and_pin(self):
        fields=json.loads(cards.job_form(self.slot)['metadata']['card_payload'])['fields']
        self.assertTrue({'city','area','pincode'}<={field['name'] for field in fields})
        self.assertFalse(next(field for field in fields if field['name']=='pincode')['required'])
