"""Package details bind matching, pricing, approval and shared capacity."""
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
from servicesetu.service_details import extract_details,validate_details
from tests.test_proofs import Clock


class ServicePackages(unittest.TestCase):
    def setUp(self):
        tmp=tempfile.TemporaryDirectory();self.addCleanup(tmp.cleanup)
        self.path=Path(tmp.name)/'packages.db'
        self.store=Store(self.path,Clock());self.store.seed(days=3,full_catalogue=True)
        self.reasoner=Reasoner();self.reasoner.key=None
        self.conversation=Conversation(self.store,self.reasoner)
        self.services=Services(self.store,payment_mode='mock');self.bus=LocalBus(self.services)
        self.slot=self.store.provider('p1')['slots'][0]

    def send(self,text,owner='alice'):
        return asyncio.run(self.conversation.handle(owner,text,self.bus))

    def request(self,service,owner='alice'):
        requests={
            'kitchen_cleaning':'one kitchen cleaning',
            'sofa_cleaning':'sofa cleaning for three seats, fabric',
            'washing_machine':'washing machine inspection, front-loading, not spinning',
            'furniture':'furniture assembly for two flat-pack chairs, instructions available',
        }
        return self.send(requests[service]+f' in Indiranagar Bengaluru {self.slot} under INR 5000',owner)

    def current_quote(self,owner='alice'):
        return self.store.get_quote(self.store.session(owner)['quotes'][0],owner)

    def approve(self,owner='alice'):
        reply=self.send('option 1',owner)
        self.assertEqual(reply['metadata']['card_kind'],'review')
        approval=json.loads(reply['metadata']['card_payload'])['approve_cta']['selection']
        bid=self.store.session(owner)['booking']
        self.assertEqual(self.store.booking(bid,owner)['payment_state'],'none')
        self.send(json.dumps(approval),owner)
        self.assertEqual(self.store.booking(bid,owner)['state'],'confirmed')
        return bid,approval

    def test_all_four_packages_book_and_recover_with_fresh_approval(self):
        for service in ('kitchen_cleaning','sofa_cleaning','washing_machine','furniture'):
            owner=service
            with self.subTest(service=service):
                reply=self.request(service,owner)
                self.assertEqual(reply['metadata']['card_kind'],'carousel')
                original=self.current_quote(owner)
                self.assertEqual(original['service'],service)
                bid,_=self.approve(owner)
                self.services.payments.cancel(owner,bid,actor='provider:'+original['provider'])
                self.assertEqual(self.store.booking(bid,owner)['payment_state'],'refunded')
                self.send('recover',owner)
                replacement=self.current_quote(owner)
                self.assertNotEqual(original['provider'],replacement['provider'])
                self.assertEqual(original.get('details',{}),replacement.get('details',{}))
                new,_=self.approve(owner)
                self.assertEqual(self.store.booking(new,owner)['recovery_of'],bid)
                # Free shared cleaning-provider capacity for the next category.
                self.services.payments.cancel(owner,new,actor='customer')

    def test_sofa_follows_up_for_seats_then_material_without_losing_budget(self):
        reply=self.send('sofa cleaning in Indiranagar Bengaluru tomorrow 10am under INR 1000')
        self.assertIn('How many sofa seats',reply['text'])
        reply=self.send('3')
        self.assertIn('fabric, leather or suede',reply['text'])
        reply=self.send('fabric')
        self.assertEqual(reply['metadata']['card_kind'],'carousel')
        quote=self.current_quote()
        self.assertEqual(quote['amount'],74700)
        self.assertEqual(quote['details'],{'seats':3,'material':'fabric'})
        self.assertIn('3 fabric sofa seats',quote['scope'])
        self.assertEqual(self.store.session('alice')['job']['budget'],100000)

    def test_invalid_seat_count_can_be_corrected_in_follow_up(self):
        reply=self.send('sofa cleaning 9 seats fabric in Indiranagar Bengaluru tomorrow 10am under INR 3000')
        self.assertIn('1 to 6',reply['text'])
        reply=self.send('3')
        self.assertEqual(reply['metadata']['card_kind'],'carousel')
        self.assertEqual(self.current_quote()['details']['seats'],3)

    def test_leather_is_not_silently_changed_to_fabric(self):
        reply=self.send('sofa cleaning 3 seats leather tomorrow 10am under INR 1000')
        self.assertIn('fabric sofas only',reply['text'])
        with self.store.connect() as db:self.assertEqual(db.execute('SELECT count(*) FROM quotes').fetchone()[0],0)

    def test_budget_checks_use_total_for_all_seats(self):
        self.send('sofa cleaning 6 seats fabric in Indiranagar Bengaluru tomorrow 10am under INR 1000')
        self.assertEqual(self.store.session('alice')['quotes'],[])

    def test_washer_type_and_problem_are_required_before_quotes(self):
        reply=self.send('washing machine inspection in Indiranagar Bengaluru tomorrow 10am under INR 700')
        self.assertIn('front-loading or top-loading',reply['text'])
        reply=self.send('top-loading')
        self.assertIn('What problem',reply['text'])
        reply=self.send('It makes a loud rattling noise')
        self.assertEqual(reply['metadata']['card_kind'],'carousel')
        quote=self.current_quote()
        self.assertIn('top-loading',quote['scope'])
        self.assertIn('rattling noise',quote['scope'])
        self.assertIn('repairs',quote['exclusions'])

    def test_furniture_requires_item_quantity_and_instructions(self):
        self.send('furniture assembly in Indiranagar Bengaluru tomorrow 10am under INR 2000')
        self.assertIn('How many',self.send('chair')['text'])
        self.assertIn('instructions',self.send('two')['text'])
        reply=self.send('instructions available')
        self.assertEqual(reply['metadata']['card_kind'],'carousel')
        self.assertEqual(self.current_quote()['amount'],69800)
        self.assertIn('2 flat-pack chair',self.current_quote()['scope'])

    def test_missing_instructions_block_assembly(self):
        reply=self.send("furniture assembly, one chair, I don't have instructions")
        self.assertIn("requires the manufacturer's instructions",reply['text'])
        self.assertFalse(self.store.session('alice').get('quotes'))

    def test_mixed_items_and_wardrobes_need_separate_quote(self):
        for request in ('furniture assembly two chairs and one table','furniture assembly one wardrobe'):
            with self.subTest(request=request):
                reply=self.send(request)
                self.assertIn('separate quote',reply['text'])
                self.assertFalse(self.store.session('alice').get('quotes'))

    def test_cleaning_packages_share_provider_capacity(self):
        self.request('kitchen_cleaning')
        quote=self.current_quote();self.store.hold('alice',quote['id'])
        reply=self.request('sofa_cleaning','bob')
        self.assertEqual(reply['metadata']['card_kind'],'carousel')
        self.assertTrue(all(self.store.get_quote(qid,'bob')['provider']!=quote['provider']
                            for qid in self.store.session('bob')['quotes']))

    def test_changed_seat_count_cannot_reuse_old_approval(self):
        self.request('sofa_cleaning')
        review=self.send('option 1')
        old=json.loads(review['metadata']['card_payload'])['approve_cta']['selection']
        self.send(f'sofa cleaning 4 seats fabric in Indiranagar Bengaluru {self.slot} under INR 5000')
        self.assertEqual(self.current_quote()['amount'],99600)
        self.send('option 1')
        reply=self.send(json.dumps(old))
        self.assertNotIn('Booking confirmed',reply['text'])
        with self.store.connect() as db:self.assertEqual(db.execute('SELECT count(*) FROM payments').fetchone()[0],0)

    def test_core_rejects_missing_or_malformed_details(self):
        job=dict(service='sofa_cleaning',package='sofa cleaning',city='bengaluru',area='indiranagar',slot=self.slot,budget=200000)
        for details in ({},{'seats':True,'material':'fabric'},{'seats':3,'material':'leather'},'3 fabric seats'):
            with self.subTest(details=details),self.assertRaises(Rejected):self.store.match(dict(job,details=details))

    def test_model_cannot_invent_service_details(self):
        class Model:
            async def parse(self,*args):
                return {'service':'sofa_cleaning','details':{'seats':3,'material':'fabric'},'package':'sofa cleaning'}
        conversation=Conversation(self.store,Model())
        reply=asyncio.run(conversation.handle('alice','sofa cleaning',self.bus))
        self.assertIn('How many sofa seats',reply['text'])
        self.assertEqual(self.store.session('alice')['partial_job']['details'],{})

    def test_service_menu_and_category_filter_do_not_reserve(self):
        reply=self.send('show cleaning services')
        payload=json.loads(reply['metadata']['card_payload'])
        self.assertEqual({item['id'] for item in payload['items']},{'cleaning','kitchen_cleaning','sofa_cleaning'})
        chosen=next(item for item in payload['items'] if item['id']=='sofa_cleaning')['primary_cta']['selection']
        reply=self.send(json.dumps(chosen))
        self.assertIn('How many sofa seats',reply['text'])
        with self.store.connect() as db:self.assertEqual(db.execute('SELECT count(*) FROM bookings').fetchone()[0],0)

    def test_full_seed_preserves_default_and_expanded_counts(self):
        self.assertEqual(len(self.store.providers()),16)
        path=self.path.parent/'expanded.db';store=Store(path,Clock());store.seed(expanded=True)
        self.assertEqual(len(store.providers()),12)
        before=store.providers();store.seed(full_catalogue=True)
        # Existing provider rows are never replaced, even when a larger seed is requested.
        for provider in before:self.assertEqual(store.provider(provider['id']),provider)

    def test_cli_full_catalogue_requires_new_database(self):
        path=self.path.parent/'cli.db'
        with patch('sys.argv',['servicesetu','seed-demo','--db',str(path),'--full-catalogue']):main()
        self.assertEqual(len(Store(path).providers()),16)
        with patch('sys.argv',['servicesetu','seed-demo','--db',str(path),'--full-catalogue']),self.assertRaises(SystemExit):main()

    def test_specific_cleaning_names_do_not_become_bathroom_cleaning(self):
        for text,service in [('clean my kitchen','kitchen_cleaning'),('sofa cleaning','sofa_cleaning'),('AC cleaning','ac'),('washing machine cleaning','washing_machine')]:
            with self.subTest(text=text):self.assertEqual(detect_service(text),service)
        async def wrong_category(*args):
            return dict(service='cleaning',city='bengaluru',area='indiranagar',slot=self.slot,budget=100000)
        with patch.object(self.reasoner,'parse',wrong_category):
            reply=self.send('sofa cleaning 3 seats fabric')
        self.assertEqual(reply['metadata']['card_kind'],'carousel')
        self.assertEqual(self.current_quote()['service'],'sofa_cleaning')

    def test_quantity_validation_does_not_accept_boolean_or_float(self):
        for quantity in (True,1.5,0,4):
            with self.subTest(quantity=quantity),self.assertRaises(ValueError):
                validate_details('furniture',{'item':'chair','quantity':quantity,'instructions':True})

    def test_short_detail_answer_does_not_call_model_or_change_budget(self):
        self.send('sofa cleaning in Indiranagar Bengaluru tomorrow 10am under INR 1000')
        async def fail(*args):raise AssertionError('Typed detail answer should not call the model')
        with patch.object(self.reasoner,'parse',fail):
            self.send('3')
            reply=self.send('fabric')
        self.assertEqual(reply['metadata']['card_kind'],'carousel')
        self.assertEqual(self.store.session('alice')['job']['budget'],100000)

    def test_catalogue_upgrade_copies_bookings_and_keeps_original_unchanged(self):
        source=self.path.parent/'source.db';original=Store(source,Clock());original.seed(expanded=True)
        quote=original.quote('existing','p7',self.slot)
        held=original.hold('existing',quote['id'])
        before=original.providers()
        target=self.path.parent/'copy.db'
        with patch('sys.argv',['servicesetu','seed-demo','--db',str(target),'--full-catalogue','--from-db',str(source)]):main()
        upgraded=Store(target,Clock())
        self.assertEqual(upgraded.booking(held['id'],'existing'),original.booking(held['id'],'existing'))
        self.assertEqual(original.providers(),before)
        self.assertNotIn('offerings',original.provider('p7'))
        self.assertIn('kitchen_cleaning',upgraded.provider('p7')['offerings'])
        self.assertEqual(len(upgraded.providers()),16)
        self.assertFalse(upgraded.slot_free('p7',self.slot))

    def test_copy_requires_existing_source_and_does_not_create_target_on_error(self):
        target=self.path.parent/'bad-copy.db'
        with patch('sys.argv',['servicesetu','seed-demo','--db',str(target),'--full-catalogue','--from-db',str(self.path.parent/'missing.db')]),self.assertRaises(SystemExit):main()
        self.assertFalse(target.exists())

    def test_offering_upgrade_preserves_configured_prices(self):
        provider=self.store.provider('p7');provider['offerings']['kitchen_cleaning']=155500
        with self.store.tx() as db:db.execute('UPDATE providers SET payload=? WHERE id=?',(json.dumps(provider),'p7'))
        self.store.extend_demo_offerings()
        self.assertEqual(self.store.provider('p7')['offerings']['kitchen_cleaning'],155500)

    def test_removed_offering_cannot_be_held_or_paid(self):
        self.request('sofa_cleaning');quote=self.current_quote()
        provider=self.store.provider(quote['provider'])
        def remove():
            provider['offerings'].pop('sofa_cleaning')
            with self.store.tx() as db:db.execute('UPDATE providers SET payload=? WHERE id=?',(json.dumps(provider),provider['id']))
        remove()
        with self.assertRaises(Rejected):self.store.hold('alice',quote['id'])
        provider['offerings']['sofa_cleaning']=24900
        with self.store.tx() as db:db.execute('UPDATE providers SET payload=? WHERE id=?',(json.dumps(provider),provider['id']))
        held=self.store.hold('alice',quote['id']);self.store.approve('alice',held['id'],quote['id'])
        remove()
        with self.assertRaises(Rejected):self.store.begin_payment('alice',held['id'],'test-idempotency')

    def test_fractional_or_negative_counts_are_not_reinterpreted_as_positive_counts(self):
        for value in ('3.5','-3'):
            with self.subTest(value=value):
                details=extract_details('sofa_cleaning',value+' seats fabric')
                with self.assertRaises(ValueError):validate_details('sofa_cleaning',details)
                details=extract_details('furniture','assemble '+value+' chairs instructions available')
                with self.assertRaises(ValueError):validate_details('furniture',details)

    def test_sofa_material_between_number_and_seats_creates_full_shortlist(self):
        reply=self.send(f'sofa cleaning for three fabric seats in Indiranagar Bengaluru {self.slot} under INR 1000')
        self.assertEqual(reply['metadata']['card_kind'],'carousel')
        self.assertEqual(self.current_quote()['amount'],74700)
        self.assertIn('FreshNest',reply['text'])
        self.assertIn('SparkleSpace',reply['text'])

    def test_partial_request_ignores_stale_provider_list_when_answering_seat_count(self):
        self.request('washing_machine')
        old=self.store.session('alice')['quotes']
        self.send(f'sofa cleaning fabric in Indiranagar Bengaluru {self.slot} under INR 1000')
        self.assertFalse(self.store.session('alice').get('quotes'))
        state=self.store.session('alice');state['quotes']=old
        self.store.save_session('alice',state)
        reply=self.send('option 2')
        self.assertIn('How many sofa seats',reply['text'])
        reply=self.send('3')
        self.assertEqual(reply['metadata']['card_kind'],'carousel')
        self.assertEqual(self.current_quote()['service'],'sofa_cleaning')
        with self.store.connect() as db:self.assertEqual(db.execute('SELECT count(*) FROM payments').fetchone()[0],0)

    def test_out_of_range_choice_redisplays_the_actual_provider_list(self):
        self.send(f'sofa cleaning 3 seats fabric in Indiranagar Bengaluru {self.slot} under INR 800')
        self.assertEqual(len(self.store.session('alice')['quotes']),1)
        reply=self.send('option 2')
        self.assertEqual(reply['metadata']['card_kind'],'carousel')
        self.assertIn('FreshNest',reply['text'])
        self.assertIn('Only 1 provider option',reply['text'])
