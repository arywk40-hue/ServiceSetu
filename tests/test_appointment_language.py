"""Everyday appointment wording must survive model omissions and follow-ups."""
import asyncio
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import AsyncMock
from servicesetu.appointments import appointment
from servicesetu.conversation import Conversation
from servicesetu.core import Store
from servicesetu.reasoning import Reasoner,offline_parse
from servicesetu.service import Services,LocalBus
from tests.test_proofs import Clock


class AppointmentLanguage(unittest.TestCase):
    def setUp(self):self.clock=Clock()

    def test_month_names_ordinals_numeric_and_case(self):
        for text in ('25 October 2026 at 2 pm','October 25th, 2026 at 2 PM','25 oct 2026 2pm',
                     '25 OCTOBER 2026 at 2:00 p.m.','25/10/2026 14:00','25-10-2026 2 Pm',
                     '2026-10-25 at 14:00','25 Oct. 2026 2 p m'):
            with self.subTest(text=text):self.assertEqual(appointment(text,self.clock())['slot'],'2026-10-25T14:00:00+05:30')

    def test_noon_midnight_and_minutes(self):
        for value,expected in (('12 am','00:00'),('12 PM','12:00'),('2:30 pm','14:30'),('09:05','09:05')):
            with self.subTest(value=value):self.assertIn('T'+expected,appointment('25 October 2026 '+value,self.clock())['slot'])

    def test_time_followup_uses_recorded_day(self):
        for value in ('2 pm','2PM','2:00 p.m.','14:00'):
            self.assertEqual(appointment(value,self.clock(),{'requested_day':'2026-10-25'})['slot'],'2026-10-25T14:00:00+05:30')

    def test_date_followup_retains_prior_time(self):
        value=appointment('25 October 2026',self.clock(),{'requested_time':'14:00'})
        self.assertEqual(value['slot'],'2026-10-25T14:00:00+05:30')

    def test_invalid_calendar_and_time_request_clarification(self):
        for text in ('31 February 2026 2pm','25 October 2026 13 pm','25 October 2026 2:75 pm','25 October 2026 24:00'):
            with self.subTest(text=text):self.assertIn('_appointment_error',appointment(text,self.clock()))

    def test_vague_period_does_not_inherit_a_precise_time(self):
        result=appointment('tomorrow morning',self.clock(),{'slot':'2026-10-14T14:00:00+05:30'})
        self.assertIsNone(result['slot']);self.assertIsNone(result['requested_time'])

    def test_iso_offset_is_normalized_to_ist(self):
        self.assertEqual(appointment('2026-10-25T08:30:00Z',self.clock())['slot'],'2026-10-25T14:00:00+05:30')

    def test_relative_dates_and_budget_not_used_as_clock(self):
        self.assertEqual(appointment('day after tomorrow at 2pm',self.clock())['requested_day'],'2026-10-15')
        self.assertEqual(appointment('under INR 1000 PIN 400076',self.clock()),{})


class AppointmentConversation(unittest.TestCase):
    def setUp(self):
        tmp=tempfile.TemporaryDirectory();self.addCleanup(tmp.cleanup)
        self.clock=Clock();self.store=Store(Path(tmp.name)/'language.db',self.clock);self.store.seed(days=3,nationwide_demo=True)
        self.reasoner=Reasoner();self.reasoner.key=None
        self.conv=Conversation(self.store,self.reasoner);self.bus=LocalBus(Services(self.store,payment_mode='mock'))
        self.date=self.store.provider('p1')['slots'][0][:10]
        from datetime import date
        self.words=date.fromisoformat(self.date).strftime('%d %B %Y')

    def send(self,text):return asyncio.run(self.conv.handle('alice',text,self.bus))

    def test_full_request_does_not_repeat_date_question(self):
        reply=self.send('AC service in Powai Mumbai on '+self.words+' at 2 pm under INR 1000')
        self.assertEqual(reply['metadata']['card_kind'],'carousel')
        self.assertEqual(self.store.session('alice')['job']['slot'],self.date+'T14:00:00+05:30')

    def test_time_then_date_keeps_other_details(self):
        self.send('AC service in Powai Mumbai at 2 pm under INR 1000')
        reply=self.send(self.words)
        self.assertEqual(reply['metadata']['card_kind'],'carousel')
        job=self.store.session('alice')['job']
        self.assertEqual(job['slot'],self.date+'T14:00:00+05:30');self.assertEqual(job['budget'],100000)
        self.assertEqual(job['area'],'powai')

    def test_day_then_lowercase_time_is_enough(self):
        question=self.send('AC service in Powai Mumbai on '+self.words+' under INR 1000')
        self.assertIn('your preferred time',question['text'])
        self.assertNotIn('your preferred day and time',question['text'])
        reply=self.send('2 pm')
        self.assertEqual(reply['metadata']['card_kind'],'carousel')

    def test_model_omission_cannot_erase_explicit_appointment(self):
        self.reasoner.parse=AsyncMock(return_value={'service':'ac','city':'mumbai','area':'powai','budget':100000,'slot':None})
        reply=self.send('AC service in Powai Mumbai '+self.words+' 2 pm under INR 1000')
        self.assertEqual(reply['metadata']['card_kind'],'carousel')

    def test_invalid_correction_clears_stale_appointment_and_no_charge(self):
        self.store.save_session('alice',{'partial_job':dict(service='ac',city='mumbai',area='powai',slot=self.date+'T10:00:00+05:30',budget=100000)})
        reply=self.send('31 February 2026 at 2 pm')
        self.assertIn('not valid',reply['text']);self.assertNotIn('slot',self.store.session('alice')['partial_job'])
        self.assertEqual(self.store.session('alice')['partial_job']['budget'],100000)
        with self.store.connect() as db:self.assertEqual(db.execute('select count(*) from payments').fetchone()[0],0)
        self.store.save_session('alice',{'partial_job':dict(service='ac',city='mumbai',area='powai',slot=self.date+'T10:00:00+05:30',requested_time='10:00',budget=100000)})
        self.send('tomorrow morning')
        self.assertIsNone(self.store.session('alice')['partial_job'].get('requested_time'))
