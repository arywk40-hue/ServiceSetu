"""Expansion must not advertise providers or change existing quote terms."""
import asyncio
import tempfile
import unittest
from pathlib import Path

from servicesetu.catalogue import SERVICES,detect_service
from servicesetu.conversation import Conversation
from servicesetu.core import Store,Rejected
from servicesetu.reasoning import Reasoner,offline_parse
from servicesetu.service import Services,LocalBus
from tests.test_proofs import Clock


class Catalogue(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.store = Store(Path(temp.name)/'catalogue.db', Clock())
        self.store.seed()
        reasoner = Reasoner(); reasoner.key = None
        self.conversation = Conversation(self.store,reasoner)
        self.bus = LocalBus(Services(self.store,payment_mode='mock'))

    def test_catalogue_request_requires_no_reasoning_or_booking(self):
        reply = asyncio.run(self.conversation.handle('alice','show services',self.bus))
        self.assertIn('Bathroom cleaning', str(reply))
        self.assertIn('no providers in this demo database', str(reply))
        with self.store.connect() as db:
            self.assertEqual(db.execute('SELECT count(*) FROM bookings').fetchone()[0], 0)

    def test_generic_cleaning_requires_an_explicit_package(self):
        parsed = offline_parse('I need home cleaning tomorrow 10am under INR 1000',Clock()())
        self.assertEqual(parsed['service'],'cleaning')
        reply = asyncio.run(self.conversation.handle('alice','I need home cleaning',self.bus))
        self.assertIn('one bathroom cleaning',str(reply))
        with self.assertRaises(Rejected):
            self.store.normalize_job(dict(parsed,city='bengaluru',area='indiranagar'))

    def test_existing_quote_scopes_and_identities_are_preserved(self):
        self.assertEqual(len(self.store.providers()),6)
        for pid,service in [('p1','ac'),('p4','plumbing')]:
            provider = self.store.provider(pid)
            quote = self.store.quote('alice',pid,provider['slots'][0])
            self.assertEqual(quote['scope'],SERVICES[service]['scope'])
            self.assertEqual(quote['exclusions'],SERVICES[service]['exclusions'])

    def test_multiple_categories_are_not_arbitrarily_selected(self):
        self.assertIsNone(detect_service('AC service and plumbing'))
        self.assertEqual(detect_service('HOME CLEANING'),'cleaning')
