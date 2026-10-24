"""Protocol, geography and booking boundaries; no live lookups or draft creation."""
import asyncio
from contextlib import asynccontextmanager
import copy
import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import httpx
from mcp.server.fastmcp import FastMCP
from mcp.types import CallToolResult, TextContent
from mcp.server.transport_security import TransportSecuritySettings

from servicesetu.external_mcp import (MCPGateway, ExternalError, DiscoveredTools,
    RequestLimits, result_data, clean_text)
from servicesetu.discovery import TomTom, Taskrabbit, coordinates, normalize_locations, public_business_phone
from servicesetu.external_conversation import ExternalConversation
from servicesetu.external_cards import price_text
from servicesetu.external_cards import tomtom_results
from servicesetu.conversation import Conversation
from servicesetu.core import Store
from servicesetu.service import Services, LocalBus
from tests.test_proofs import Clock

TASK_TOOLS=json.loads((Path(__file__).parent/'fixtures/taskrabbit-mcp-tools.json').read_text())
TOM_TOOLS=[
    {'name':'tomtom-geocode','inputSchema':{'type':'object','properties':{'query':{'type':'string'},'countries':{'type':'array'},'limit':{'type':'integer'},'response_detail':{'type':'string'}},'required':['query']}},
    {'name':'tomtom-fuzzy-search','inputSchema':{'type':'object','properties':{'query':{'type':'string'},'countries':{'type':'array'},'limit':{'type':'integer'},'idxSet':{'type':'string'},'response_detail':{'type':'string'}},'required':['query']}},
    {'name':'tomtom-routing','inputSchema':{'type':'object','properties':{'locations':{'type':'array'},'response_detail':{'type':'string'}},'required':['locations']}}]


def feature(country='IN',business=True):
    return {'type':'Feature','id':'synthetic-place','geometry':{'type':'Point','coordinates':[76.93,31.71]},
        'properties':{'address':{'countryCode':country,'freeformAddress':'Synthetic Road, Mandi, India'},
            **({'poi':{'name':'Synthetic repair business'}} if business else {})}}


def availability():
    return {'available':True,'citySupported':True,'categoryId':'furniture_assembly','serviceLabel':'Furniture Assembly',
        'location':{'address':'New York City, NY','postal_code':'10001','lat':40.7484,'lng':-73.9967},
        'pricing':{'type':'hourly','averageHourlyRate':59,'currency':'USD'},
        'scopingQuestions':[{'question':'Describe your task','param':'description'},
            {'question':'How big is your task?','param':'job_size','options':[{'value':'small','text':'Small','acceptsUserInput':False}]}]}


class StubSession:
    def __init__(self,responses):self.responses=responses;self.calls=[]
    async def call_tool(self,name,arguments):
        self.calls.append((name,arguments))
        item=self.responses[name]
        if isinstance(item,Exception):raise item
        if isinstance(item,list):item=item.pop(0)
        return CallToolResult(content=[TextContent(type='text',text=json.dumps(item))])


class GatewayDouble:
    def __init__(self,responses,tools=None):self.session=StubSession(responses);self.tools=tools;self.runs=[]
    async def run(self,provider,operation,owner='operator',read_only=True):
        self.runs.append((provider,owner,read_only))
        tools=self.tools if self.tools is not None else TASK_TOOLS if provider=='taskrabbit' else TOM_TOOLS
        return await operation(DiscoveredTools(self.session,provider,[SimpleNamespace(**t) for t in tools]))


class AdapterTests(unittest.IsolatedAsyncioTestCase):
    async def test_tomtom_search_constrains_india_and_never_creates_bookable_records(self):
        gateway=GatewayDouble({'tomtom-fuzzy-search':{'features':[feature(),feature('US')]}})
        results=await TomTom(gateway).search('plumbers','Mandi, Himachal Pradesh','alice:session')
        self.assertEqual(len(results),1);self.assertFalse(results[0]['onboarded'])
        name,args=gateway.session.calls[0]
        self.assertEqual((name,args['countries'],args['idxSet'],args['limit']),('tomtom-fuzzy-search',['IN'],'POI',5))
        self.assertEqual(args['response_detail'],'full')
        self.assertEqual(gateway.runs[0],('tomtom','alice:session',True))

    async def test_public_listing_phone_is_retained_without_onboarding_or_booking(self):
        row=feature();row['properties']['poi']['phone']='+91 90000 00000'
        gateway=GatewayDouble({'tomtom-fuzzy-search':{'features':[row]}})
        result=await TomTom(gateway).search('plumbers','Mandi, Himachal Pradesh')
        self.assertEqual(result[0]['phone'],'+91 90000 00000')
        self.assertFalse(result[0]['onboarded'])
        card=tomtom_results(result)
        self.assertIn('Public listing phone: +91 90000 00000',card['text'])
        self.assertIn('ServiceSetu has not called, verified, reserved or charged',card['text'])
        payload=json.loads(card['metadata']['card_payload'])
        self.assertNotIn('primary_cta',payload['items'][0])

    async def test_malformed_or_missing_listing_phone_is_not_rendered(self):
        for bad in (None,123,{},'javascript:alert(1)','+91 90000 00000\nsecret','+123','1'*16):
            self.assertIsNone(public_business_phone(bad))
            row=feature();row['properties']['poi']['phone']=bad
            result=normalize_locations({'features':[row]},businesses=True)
            self.assertNotIn('phone',result[0])
            self.assertNotIn('Public listing phone:',tomtom_results(result)['text'])

    async def test_geocode_does_not_expose_phone_as_a_business_contact(self):
        row=feature();row['properties']['poi']['phone']='+91 90000 00000'
        result=normalize_locations({'features':[row]},businesses=False)
        self.assertNotIn('phone',result[0])
        result[0]['phone']='+91 90000 00000'
        self.assertNotIn('Public listing phone:',tomtom_results(result,geocoding=True)['text'])

    async def test_geocode_handles_geojson_and_empty_results(self):
        gateway=GatewayDouble({'tomtom-geocode':[{'features':[feature(business=False)]},{'features':[]}]})
        adapter=TomTom(gateway)
        self.assertEqual((await adapter.geocode('Mandi'))[0]['position'],[76.93,31.71])
        self.assertEqual(await adapter.geocode('Unknown locality'),[])

    async def test_route_uses_exact_resolved_points_and_geojson_summary(self):
        route={'features':[{'properties':{'summary':{'lengthInMeters':1200,'travelTimeInSeconds':300}}}]}
        gateway=GatewayDouble({'tomtom-geocode':{'features':[feature(business=False)]},'tomtom-routing':route})
        result=await TomTom(gateway).route('Mandi public origin','Mandi public destination')
        self.assertEqual((result['meters'],result['seconds']),(1200,300))
        self.assertEqual(gateway.session.calls[-1][1]['locations'],[[76.93,31.71],[76.93,31.71]])

    async def test_route_refuses_ambiguous_or_missing_origin_before_routing(self):
        for rows in ([],[feature(),feature()]):
            gateway=GatewayDouble({'tomtom-geocode':{'features':rows}})
            with self.assertRaises(ExternalError):await TomTom(gateway).route('Origin','Destination')
            self.assertNotIn('tomtom-routing',[c[0] for c in gateway.session.calls])

    async def test_invalid_route_units_and_bad_coordinates_fail_closed(self):
        gateway=GatewayDouble({'tomtom-geocode':{'features':[feature()]},'tomtom-routing':{'routes':[{'summary':{'lengthInMeters':-1,'travelTimeInSeconds':0}}]}})
        with self.assertRaises(ExternalError):await TomTom(gateway).route('Origin','Destination')
        for point in ([1,float('nan')],[181,31],[76,True],None):
            with self.assertRaises(ExternalError):coordinates(point)

    async def test_india_and_nonus_locations_do_not_call_taskrabbit(self):
        gateway=GatewayDouble({});adapter=Taskrabbit(gateway)
        for country,postal in (('IN','175001'),('GB','SW1A 1AA'),('US','560038')):
            with self.assertRaises(ExternalError):await adapter.check('plumbing',country,postal)
        self.assertEqual(gateway.session.calls,[]);self.assertEqual(gateway.runs,[])

    async def test_explicit_us_request_passes_original_service_and_postcode(self):
        gateway=GatewayDouble({'check_service_availability':availability()})
        result=await Taskrabbit(gateway).check('assemble one chair','US','10001')
        self.assertTrue(result['available'])
        self.assertEqual(gateway.session.calls[0][1],{'postalCode':'10001','service':'assemble one chair'})

    async def test_wrong_returned_location_and_missing_scoping_fields_rejected(self):
        for alter in ('location','scopingQuestions'):
            response=availability()
            if alter=='location':response['location']['postal_code']='94103'
            else:response['scopingQuestions']='not questions'
            with self.assertRaises(ExternalError):await Taskrabbit(GatewayDouble({'check_service_availability':response})).check('assembly','US','10001')

    async def test_schema_changes_and_missing_tools_prevent_remote_call(self):
        for tools in ([],[{'name':'tomtom-geocode','inputSchema':{'type':'object','required':['new_required_field']}}]):
            gateway=GatewayDouble({},tools)
            with self.assertRaises(ExternalError):await TomTom(gateway).geocode('Mandi')
            self.assertEqual(gateway.session.calls,[])

    async def test_generated_link_allowlist_and_no_retry_flag(self):
        for url,ok in [('https://www.taskrabbit.com/book/draft-example',True),('https://taskrabbit.com.evil.test/pay',False),('javascript:alert(1)',False),('https://user@www.taskrabbit.com/path',False),('https://www.taskrabbit.com:bad/path',False)]:
            gateway=GatewayDouble({'generate_deep_link':{'url':url}})
            adapter=Taskrabbit(gateway)
            answers=[{'question':'Size','param':'job_size','answer':'small'}]
            if ok:self.assertEqual(await adapter.deep_link(availability(),answers,'alice:session'),url)
            else:
                with self.assertRaises(ExternalError):await adapter.deep_link(availability(),answers,'alice:session')
            self.assertFalse(gateway.runs[0][2])

    async def test_price_is_currency_qualified_and_not_a_fixed_quote(self):
        text=price_text(availability()['pricing'])
        self.assertIn('USD 59.00 per hour',text);self.assertIn('not a fixed quote',text)
        self.assertNotIn('INR',text)
        self.assertIn('No usable',price_text({'averageHourlyRate':59}))

    async def test_error_and_unsupported_result_do_not_render_upstream_text(self):
        for result in (CallToolResult(isError=True,content=[TextContent(type='text',text='SECRET upstream error')]),
                CallToolResult(content=[TextContent(type='text',text='not json')])):
            with self.assertRaises(ExternalError) as caught:result_data(result)
            self.assertNotIn('SECRET',str(caught.exception))
        with patch.dict('os.environ',{'TOMTOM_API_KEY':'test-secret-never-display'}):
            self.assertNotIn('test-secret-never-display',clean_text('oops test-secret-never-display'))

    async def test_rate_limits_are_per_owner_and_global(self):
        limits=RequestLimits(clock=lambda:100)
        for _ in range(8):limits.take('alice:one')
        with self.assertRaises(ExternalError):limits.take('alice:one')
        limits.take('alice:two')
        for i in range(31):limits.take(str(i))
        with self.assertRaises(ExternalError):limits.take('another')


class BackendConversationTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.clock=Clock();self.store=Store(Path(self.tmp.name)/'external.db',self.clock);self.store.seed()
        self.gateway=GatewayDouble({'check_service_availability':availability(),'generate_deep_link':{'url':'https://www.taskrabbit.com/book/synthetic-draft'}})
        self.external=ExternalConversation(self.store,TomTom(self.gateway),Taskrabbit(self.gateway))
        self.conversation=Conversation(self.store,payment_mode='mock',external=self.external)
        self.bus=LocalBus(Services(self.store,'mock'));self.owner='alice:session'

    async def say(self,message,owner=None):
        if isinstance(message,dict):message=json.dumps(message)
        return await self.conversation.handle(owner or self.owner,message,self.bus)

    def card(self,reply):return json.loads(reply['metadata']['card_payload'])

    def no_booking_or_payment(self):
        with self.store.connect() as db:
            self.assertEqual(db.execute('select count(*) from bookings').fetchone()[0],0)
            self.assertEqual(db.execute('select count(*) from payments').fetchone()[0],0)

    async def prepare_review(self):
        await self.say('Taskrabbit furniture assembly in US 10001')
        token=self.store.session(self.owner)['taskrabbit_request']['token']
        first=await self.say({'action':'taskrabbit_scope','external_token':token})
        choice=self.card(first)['submit_cta']['selection']
        second=await self.say(dict(choice,answer='Assemble one synthetic chair'))
        choice=self.card(second)['submit_cta']['selection']
        review=await self.say(dict(choice,answer='small'))
        return self.card(review)['ctas'][0]['selection']

    async def test_india_refusal_and_map_results_do_not_touch_booking_tables(self):
        refusal=await self.say('Taskrabbit plumber in Mandi, Himachal Pradesh')
        self.assertIn('unavailable in India',refusal['text']);self.assertEqual(self.gateway.session.calls,[])
        listing = feature()
        listing['properties']['poi']['phone'] = '+91 90000 00000'
        self.gateway.session.responses['tomtom-fuzzy-search']={'features':[listing]}
        result=await self.say('TomTom plumbers in Mandi, Himachal Pradesh')
        self.assertIn('not onboarded',result['text']);self.assertNotIn('payment',result)
        self.assertIn('Public listing phone: +91 90000 00000',result['text'])
        self.assertNotIn('primary_cta',self.card(result)['items'][0])
        self.no_booking_or_payment()

    async def test_task_scoping_explicit_review_and_retries_do_not_confirm_booking(self):
        selection=await self.prepare_review()
        self.assertNotIn('generate_deep_link',[c[0] for c in self.gateway.session.calls])
        one=await self.say(selection);two=await self.say(selection)
        self.assertIn('Continue booking on Taskrabbit',one['text']);self.assertEqual(one['text'],two['text'])
        self.assertEqual(sum(c[0]=='generate_deep_link' for c in self.gateway.session.calls),1)
        self.no_booking_or_payment()

    async def test_foreign_session_and_expired_review_cannot_generate_draft(self):
        selection=await self.prepare_review()
        foreign=await self.say(selection,owner='alice:other-session')
        self.assertIn('same conversation',foreign['text'])
        self.clock.now+=601
        stale=await self.say(selection);self.assertIn('expired',stale['text'])
        self.assertNotIn('generate_deep_link',[c[0] for c in self.gateway.session.calls])
        self.no_booking_or_payment()

    async def test_lost_draft_response_does_not_retry_creation(self):
        selection=await self.prepare_review()
        self.gateway.session.responses['generate_deep_link']=ExternalError('timeout','Draft request timed out')
        await self.say(selection);reply=await self.say(selection)
        self.assertIn('not be sent again',reply['text'])
        self.assertEqual(sum(c[0]=='generate_deep_link' for c in self.gateway.session.calls),1)

    async def test_stale_scope_answer_does_not_answer_the_next_question(self):
        await self.say('Taskrabbit furniture assembly in US 10001')
        token=self.store.session(self.owner)['taskrabbit_request']['token']
        response=await self.say({'action':'taskrabbit_scope','external_token':token})
        selected=self.card(response)['submit_cta']['selection']
        await self.say(dict(selected,answer='One chair'))
        retry=await self.say(dict(selected,answer='One chair'))
        self.assertIn('older Taskrabbit question',retry['text'])
        self.assertEqual(len(self.store.session(self.owner)['taskrabbit_request']['answers']),1)

    async def test_external_item_cannot_be_selected_as_a_servicesetu_quote(self):
        for action in ('select','approve'):
            reply=await self.say({'action':action,'quote_id':'tomtom:synthetic-place','booking_id':'taskrabbit:0','approval_token':'external'})
            self.assertNotIn('payment',reply)
        self.no_booking_or_payment()


class SDKTransportTests(unittest.IsolatedAsyncioTestCase):
    async def test_official_sdk_initializes_discovers_and_passes_secret_in_header_only(self):
        server=FastMCP('ServiceSetu test server',stateless_http=True,json_response=True,streamable_http_path='/maps',
            transport_security=TransportSecuritySettings(allowed_hosts=['mcp.tomtom.com'],allowed_origins=['https://mcp.tomtom.com']))
        @server.tool(name='tomtom-geocode')
        def geocode(query:str)->dict:
            return {'features':[feature(business=False)]}
        app=server.streamable_http_app();seen=[]
        async def wrapped(scope,receive,send):
            if scope['type']=='http':seen.append((scope['path'],dict(scope['headers'])))
            await app(scope,receive,send)
        original=httpx.AsyncClient
        def client(**kwargs):return original(transport=httpx.ASGITransport(app=wrapped),**kwargs)
        async with server.session_manager.run():
            with patch('httpx.AsyncClient',side_effect=client),patch.dict('os.environ',{'TOMTOM_API_KEY':'synthetic-private-key'}):
                result=await TomTom(MCPGateway(RequestLimits())).geocode('Mandi')
        self.assertEqual(len(result),1)
        self.assertTrue(any(headers.get(b'tomtom-api-key')==b'synthetic-private-key' for _,headers in seen))
        self.assertTrue(all('synthetic-private-key' not in path for path,_ in seen))

    async def test_auth_rate_limits_network_errors_are_safe_and_bounded(self):
        original=httpx.AsyncClient
        for status,expected in ((401,'auth'),(403,'auth'),(429,'rate_limit'),(503,'unavailable')):
            clients=[]
            def handler(request):return httpx.Response(status,json={'error':'synthetic-secret'},request=request)
            def client(**kwargs):
                clients.append(1)
                return original(transport=httpx.MockTransport(handler),**kwargs)
            with self.subTest(status=status),patch('httpx.AsyncClient',side_effect=client):
                with self.assertRaises(ExternalError) as caught:
                    await MCPGateway(RequestLimits()).run('taskrabbit',AsyncMock())
                self.assertEqual(caught.exception.code,expected)
                self.assertLessEqual(len(clients),2 if status==503 else 1)
                self.assertNotIn('synthetic-secret',str(caught.exception))

    async def test_missing_key_refuses_before_connecting(self):
        with patch.dict('os.environ',{'TOMTOM_API_KEY':''}),patch('httpx.AsyncClient') as client:
            with self.assertRaises(ExternalError):await TomTom(MCPGateway(RequestLimits())).geocode('Mandi')
            client.assert_not_called()


if __name__=='__main__':unittest.main()
