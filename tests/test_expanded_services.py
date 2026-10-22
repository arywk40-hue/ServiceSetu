"""New packages use the existing consequence and recovery boundaries."""
import asyncio
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from servicesetu.__main__ import main
from servicesetu.catalogue import SERVICES,detect_service
from servicesetu.conversation import Conversation
from servicesetu.core import Store,Rejected
from servicesetu.reasoning import Reasoner
from servicesetu.service import Services,LocalBus
from tests.test_proofs import Clock


class ExpandedServices(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.clock=Clock()
        self.store=Store(Path(self.temp.name)/'expanded.db',self.clock)
        self.store.seed(days=3,expanded=True)
        self.services=Services(self.store,payment_mode='mock')
        reasoner=Reasoner();reasoner.key=None
        self.conversation=Conversation(self.store,reasoner)
        self.bus=LocalBus(self.services)

    def send(self,text,owner='alice'):
        return asyncio.run(self.conversation.handle(owner,text,self.bus))

    def job(self,service):
        return dict(service=service,package=SERVICES[service]['package'],city='bengaluru',
                    area='indiranagar',slot=self.store.provider('p7')['slots'][0],budget=100000)

    def book(self,service):
        job=self.job(service)
        reply=self.send(f"{job['package']} in Indiranagar Bengaluru {job['slot']} under INR 1000")
        self.assertEqual(reply['metadata']['card_kind'],'carousel')
        shortlist=self.store.session('alice')['quotes']
        self.assertEqual(len(shortlist),2)
        selected=self.store.get_quote(shortlist[0],'alice')
        self.assertEqual(selected['scope'],SERVICES[service]['scope'])
        review=self.send('option 1')
        approval=json.loads(review['metadata']['card_payload'])['approve_cta']['selection']
        bid=self.store.session('alice')['booking']
        self.assertEqual(self.store.booking(bid,'alice')['payment_state'],'none')
        self.send(json.dumps(approval))
        self.assertEqual(self.store.booking(bid,'alice')['state'],'confirmed')
        self.send(json.dumps(approval))
        with self.store.connect() as db:
            self.assertEqual(db.execute('SELECT count(*) FROM payments WHERE booking=?',(bid,)).fetchone()[0],1)
        return bid,selected

    def test_cleaning_booking_and_replacement_require_separate_approval(self):
        bid,quote=self.book('cleaning')
        self.services.payments.cancel('alice',bid,actor='provider:'+quote['provider'])
        self.assertEqual(self.store.booking(bid,'alice')['payment_state'],'refunded')
        self.send('recover')
        review=self.send('option 1')
        new=self.store.session('alice')['booking']
        self.assertEqual(self.store.booking(new,'alice')['state'],'held')
        approval=json.loads(review['metadata']['card_payload'])['approve_cta']['selection']
        self.send(json.dumps(approval))
        self.assertEqual(self.store.booking(new,'alice')['state'],'confirmed')
        timeline=self.send('show what happened')['text']
        self.assertIn('Provider cancelled',timeline)
        self.assertIn('Replacement booking confirmed',timeline)

    def test_electrical_booking_carries_inspection_only_exclusions(self):
        _,quote=self.book('electrical')
        self.assertIn('assessment only',quote['scope'])
        self.assertIn('Repairs',quote['exclusions'])
        self.assertIn('emergency response',quote['exclusions'])

    def test_generic_cleaning_asks_package_and_retains_request(self):
        reply=self.send('Home cleaning in Indiranagar Bengaluru tomorrow 10am under INR 1000')
        self.assertIn('one bathroom cleaning',reply['text'])
        with self.store.connect() as db:
            self.assertEqual(db.execute('SELECT count(*) FROM quotes').fetchone()[0],0)
        reply=self.send('one bathroom cleaning')
        self.assertEqual(reply['metadata']['card_kind'],'carousel')
        self.assertEqual(self.store.session('alice')['job']['budget'],100000)

    def test_electrician_request_does_not_assume_repair_scope(self):
        reply=self.send('I need an electrician tomorrow 10am under INR 1000')
        self.assertIn('electrical inspection',reply['text'])
        self.assertIn('Repairs',reply['text'])
        self.assertNotIn('quotes',self.store.session('alice'))

    def test_whole_home_or_two_bathrooms_are_not_one_bathroom_package(self):
        for text in ('clean my whole home','clean two bathrooms','clean 2 bathrooms and one bathroom'):
            with self.subTest(text=text):
                reply=self.send(text)
                self.assertIn('reply',reply['text'])
                self.assertNotIn('quotes',self.store.session('alice'))

    def test_new_categories_exclude_expired_and_over_budget_providers(self):
        for service in ('cleaning','electrical'):
            job=self.job(service)
            providers,excluded=self.store.match(job)
            self.assertEqual(len(providers),2)
            self.assertEqual(len(excluded),1)
            self.assertIn('expired',excluded[0]['reason'])
            job['budget']=100
            self.assertEqual(self.store.match(job)[0],[])

    def test_expanded_seed_preserves_existing_provider_records_and_bookings(self):
        path=Path(self.temp.name)/'old.db'
        store=Store(path,self.clock);store.seed()
        before=store.providers()
        quote=store.quote('customer','p1',before[0]['slots'][0])
        held=store.hold('customer',quote['id'])
        store.seed(days=3,expanded=True)
        for old in before: self.assertEqual(store.provider(old['id']),old)
        self.assertEqual(len(store.providers()),12)
        self.assertEqual(store.booking(held['id'],'customer')['state'],'held')

    def test_cli_expanded_creates_twelve_providers_only_in_new_database(self):
        path=Path(self.temp.name)/'cli.db'
        with patch('sys.argv',['servicesetu','seed-demo','--db',str(path),'--expanded','--days','3']):
            main()
        self.assertEqual(len(Store(path).providers()),12)

    def test_form_selection_uses_explicitly_labelled_package(self):
        reply=self.send(json.dumps(dict(action='search',service='cleaning',city='bengaluru',
                         area='indiranagar',slot=self.job('cleaning')['slot'],budget_rupees=1000)))
        self.assertEqual(reply['metadata']['card_kind'],'carousel')
        self.assertEqual(self.store.session('alice')['job']['package'],'one bathroom cleaning')

    def test_ac_cleaning_remains_ac_and_core_rejects_wrong_package(self):
        self.assertEqual(detect_service('AC cleaning'),'ac')
        job=self.job('cleaning');job['package']='whole home'
        with self.assertRaises(Rejected):self.store.match(job)
