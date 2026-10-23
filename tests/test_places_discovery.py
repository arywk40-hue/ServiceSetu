"""Tests for Google Places API (New) live local-service discovery.

Verifies:
- Successful Text Search and normalization
- Missing fields and pure service-area business handling
- Empty results and honest messaging without fictional substitution
- Bounded errors: missing credentials, auth failure (401/403), quota limits (429), timeouts
- Strict booking and payment boundary enforcement for unpartnered businesses
- Location ambiguity clarification and intake integration
"""
import asyncio
import json
import os
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch, AsyncMock

import httpx

from servicesetu.core import Store, Rejected
from servicesetu.conversation import Conversation
from servicesetu.service import Services, LocalBus
from servicesetu.reasoning import Reasoner
from servicesetu.places import (
    search_places,
    normalize_place,
    parse_places_intent,
    PlacesMissingKeyError,
    PlacesAuthError,
    PlacesQuotaError,
    PlacesTimeoutError,
    PlacesApiError,
)
from servicesetu import cards


class PlacesDiscoveryTests(unittest.TestCase):
    def setUp(self):
        self.tmp = TemporaryDirectory()
        self.db_path = Path(self.tmp.name) / "test.db"
        self.store = Store(self.db_path)
        self.store.seed()
        self.reasoner = Reasoner()
        self.reasoner.key = None
        self.bus = LocalBus(Services(self.store, payment_mode="mock"))
        self.conv = Conversation(self.store, self.reasoner, payment_mode="mock")
        self.owner = "customer:places-session"

    def tearDown(self):
        self.tmp.cleanup()

    def test_normalize_place_full_storefront(self):
        raw = {
            "id": "places/ChIJN1t_tDeuEmsRUsoyG83frY4",
            "displayName": {"text": "Mandi Express Plumbing", "languageCode": "en"},
            "formattedAddress": "Main Bazaar, Mandi, Himachal Pradesh 175001",
            "rating": 4.7,
            "userRatingCount": 42,
            "googleMapsUri": "https://maps.google.com/?cid=12345678",
            "businessStatus": "OPERATIONAL",
            "pureServiceAreaBusiness": False,
        }
        normalized = normalize_place(raw)
        self.assertEqual(normalized["name"], "Mandi Express Plumbing")
        self.assertEqual(normalized["address"], "Main Bazaar, Mandi, Himachal Pradesh 175001")
        self.assertFalse(normalized["is_service_area"])
        self.assertEqual(normalized["rating"], 4.7)
        self.assertEqual(normalized["review_count"], 42)
        self.assertEqual(normalized["google_maps_uri"], "https://maps.google.com/?cid=12345678")
        self.assertFalse(normalized["onboarded"])
        self.assertEqual(normalized["source"], "google_maps")

    def test_normalize_place_service_area_business_with_missing_fields(self):
        raw = {
            "id": "places/ChIJServiceArea999",
            "displayName": {"text": "Himalayan Mobile AC Care"},
            "pureServiceAreaBusiness": True,
            # formattedAddress missing
            # rating & userRatingCount missing
            # googleMapsUri missing
        }
        normalized = normalize_place(raw)
        self.assertEqual(normalized["name"], "Himalayan Mobile AC Care")
        self.assertTrue(normalized["is_service_area"])
        self.assertIsNone(normalized["address"])
        self.assertIsNone(normalized["rating"])
        self.assertIsNone(normalized["review_count"])
        self.assertIn("place_id:ChIJServiceArea999", normalized["google_maps_uri"])
        self.assertFalse(normalized["onboarded"])

    def test_places_results_card_does_not_invent_prices_or_credentials(self):
        places = [
            {
                "id": "ChIJ1",
                "name": "Powai Cleaners",
                "address": "Central Avenue, Powai, Mumbai 400076",
                "is_service_area": False,
                "rating": 4.5,
                "review_count": 18,
                "google_maps_uri": "https://maps.google.com/?cid=111",
            },
            {
                "id": "ChIJ2",
                "name": "Shine Service Area Cleaners",
                "address": None,
                "is_service_area": True,
                "rating": None,
                "review_count": None,
                "google_maps_uri": "https://maps.google.com/?cid=222",
            },
        ]
        card = cards.places_results(places, "cleaning services in Powai, Mumbai")
        text = card["text"]

        # Honest Google Maps disclaimers
        self.assertIn("Found on Google Maps; not onboarded to ServiceSetu", text)
        self.assertIn("Powered by Google", text)
        self.assertIn("Powai Cleaners", text)
        self.assertIn("4.5 ★ (18 Google reviews)", text)
        self.assertIn("Shine Service Area Cleaners", text)
        self.assertIn("No Google rating available", text)
        self.assertIn("Service-area business", text)

        # Must NOT invent prices, appointments, or verified credentials
        self.assertNotIn("INR", text)
        self.assertNotIn("paise", text)
        self.assertNotIn("verified documents", text.lower())

        # Check ACP card structure
        payload = json.loads(card["metadata"]["card_payload"])
        self.assertEqual(len(payload["items"]), 2)
        item1 = payload["items"][0]
        self.assertEqual(item1["primary_cta"]["selection"]["action"], "view_maps")
        self.assertEqual(item1["primary_cta"]["selection"]["url"], "https://maps.google.com/?cid=111")

    def test_search_places_success_mock(self):
        fake_response = {
            "places": [
                {
                    "id": "places/ChIJMandiPlumb1",
                    "displayName": {"text": "Mandi Hydro Tech"},
                    "formattedAddress": "Bus Stand Rd, Mandi, HP 175001",
                    "rating": 4.8,
                    "userRatingCount": 29,
                    "googleMapsUri": "https://maps.google.com/?cid=999",
                    "businessStatus": "OPERATIONAL",
                    "pureServiceAreaBusiness": False,
                }
            ]
        }

        async def run_test():
            mock_resp = httpx.Response(200, json=fake_response, request=httpx.Request("POST", "https://test"))
            with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
                mock_post.return_value = mock_resp
                results = await search_places("plumbers in Mandi, Himachal Pradesh", api_key="AIzaSyTestKey")
                self.assertEqual(len(results), 1)
                self.assertEqual(results[0]["name"], "Mandi Hydro Tech")
                self.assertEqual(results[0]["rating"], 4.8)

        asyncio.run(run_test())

    def test_search_places_empty_results_mock(self):
        async def run_test():
            mock_resp = httpx.Response(200, json={"places": []}, request=httpx.Request("POST", "https://test"))
            with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
                mock_post.return_value = mock_resp
                results = await search_places("rare service in remote area", api_key="AIzaSyTestKey")
                self.assertEqual(results, [])

        asyncio.run(run_test())

    def test_missing_api_key_raises_informative_error(self):
        async def run_test():
            with patch.dict(os.environ, {"GOOGLE_PLACES_API_KEY": ""}):
                with self.assertRaises(PlacesMissingKeyError) as ctx:
                    await search_places("plumbers in Mandi")
                self.assertIn("GOOGLE_PLACES_API_KEY", str(ctx.exception))

        asyncio.run(run_test())

    def test_auth_error_403_raises_places_auth_error(self):
        async def run_test():
            mock_resp = httpx.Response(
                403,
                json={"error": {"code": 403, "message": "API key not valid", "status": "PERMISSION_DENIED"}},
                request=httpx.Request("POST", "https://test"),
            )
            with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
                mock_post.return_value = mock_resp
                with self.assertRaises(PlacesAuthError):
                    await search_places("plumbers in Mandi", api_key="bad-key")

        asyncio.run(run_test())

    def test_quota_error_429_raises_places_quota_error(self):
        async def run_test():
            mock_resp = httpx.Response(
                429,
                json={"error": {"code": 429, "message": "Resource exhausted", "status": "RESOURCE_EXHAUSTED"}},
                request=httpx.Request("POST", "https://test"),
            )
            with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
                mock_post.return_value = mock_resp
                with self.assertRaises(PlacesQuotaError):
                    await search_places("plumbers in Mandi", api_key="key")

        asyncio.run(run_test())

    def test_timeout_raises_places_timeout_error(self):
        async def run_test():
            with patch("httpx.AsyncClient.post", side_effect=httpx.TimeoutException("Read timed out")):
                with self.assertRaises(PlacesTimeoutError):
                    await search_places("plumbers in Mandi", api_key="key", timeout=0.1)

        asyncio.run(run_test())

    def test_prohibition_on_booking_unpartnered_places_business(self):
        """Enforces the boundary: Google Maps places cannot be booked, held, or paid."""
        async def run_test():
            # Inject a discovered place id into session state
            state = self.store.session(self.owner)
            state["discovered_places"] = ["ChIJ_Unonboarded_123"]
            self.store.save_session(self.owner, state)

            # 1. Attempting to select unonboarded place
            reply = await self.conv.handle(self.owner, '{"action":"select","quote_id":"ChIJ_Unonboarded_123"}', self.bus)
            self.assertIn("not onboarded to ServiceSetu", reply["text"])
            self.assertIn("cannot be booked", reply["text"])

            # 2. Attempting to approve unonboarded place
            reply2 = await self.conv.handle(
                self.owner,
                '{"action":"approve","booking_id":"b_fake","quote_id":"ChIJ_Unonboarded_123","approval_token":"at_fake"}',
                self.bus,
            )
            self.assertIn("not onboarded to ServiceSetu", reply2["text"])

            # 3. Assert zero bookings or payments created in database
            with self.store.connect() as db:
                self.assertEqual(db.execute("SELECT count(*) FROM bookings").fetchone()[0], 0)
                self.assertEqual(db.execute("SELECT count(*) FROM payments").fetchone()[0], 0)

        asyncio.run(run_test())

    def test_view_maps_action_shows_disclaimer(self):
        async def run_test():
            reply = await self.conv.handle(
                self.owner,
                json.dumps({
                    "action": "view_maps",
                    "name": "Mandi Leak Repair",
                    "url": "https://maps.google.com/?cid=123",
                }),
                self.bus,
            )
            self.assertIn("Mandi Leak Repair", reply["text"])
            self.assertIn("https://maps.google.com/?cid=123", reply["text"])
            self.assertIn("Found on Google Maps; not onboarded to ServiceSetu", reply["text"])
            self.assertIn("Appointments, pricing, and payments cannot be processed through ServiceSetu", reply["text"])

        asyncio.run(run_test())

    def test_direct_prompts_execution(self):
        """Test the three mandatory prompts from the specification."""
        fake_places = [
            {
                "id": "places/ChIJ1",
                "name": "Indiranagar AC Specialists",
                "address": "100ft Road, Indiranagar, Bengaluru",
                "is_service_area": False,
                "rating": 4.6,
                "review_count": 55,
                "googleMapsUri": "https://maps.google.com/?cid=1",
            }
        ]

        async def run_test():
            with patch("servicesetu.conversation.search_places", new_callable=AsyncMock) as mock_search:
                mock_search.return_value = fake_places

                # Prompt 1: Find AC service businesses in Indiranagar, Bengaluru.
                reply1 = await self.conv.handle(self.owner, "Find AC service businesses in Indiranagar, Bengaluru.", self.bus)
                self.assertIn("Indiranagar AC Specialists", reply1["text"])
                self.assertIn("Found on Google Maps; not onboarded to ServiceSetu", reply1["text"])
                mock_search.assert_called_with("AC service businesses in Indiranagar, Bengaluru")

                # Prompt 2: Find real plumbers in Mandi, Himachal Pradesh.
                mock_search.return_value = [
                    {
                        "id": "places/ChIJ2",
                        "name": "Mandi Plumber Works",
                        "address": "Gandhi Chowk, Mandi, HP",
                        "is_service_area": False,
                        "rating": 4.9,
                        "review_count": 14,
                        "googleMapsUri": "https://maps.google.com/?cid=2",
                    }
                ]
                reply2 = await self.conv.handle(self.owner, "Find real plumbers in Mandi, Himachal Pradesh.", self.bus)
                self.assertIn("Mandi Plumber Works", reply2["text"])
                mock_search.assert_called_with("plumbers in Mandi, Himachal Pradesh")

                # Prompt 3: Find cleaning services in Powai, Mumbai.
                mock_search.return_value = [
                    {
                        "id": "places/ChIJ3",
                        "name": "Powai Home Clean",
                        "address": "Hiranandani, Powai, Mumbai",
                        "is_service_area": False,
                        "rating": 4.3,
                        "review_count": 27,
                        "googleMapsUri": "https://maps.google.com/?cid=3",
                    }
                ]
                reply3 = await self.conv.handle(self.owner, "Find cleaning services in Powai, Mumbai.", self.bus)
                self.assertIn("Powai Home Clean", reply3["text"])
                mock_search.assert_called_with("cleaning services in Powai, Mumbai")

        asyncio.run(run_test())

    def test_api_failure_does_not_substitute_fictional_demo_providers(self):
        """API failures must fail honestly without silently showing demo providers."""
        async def run_test():
            with patch("servicesetu.conversation.search_places", side_effect=PlacesAuthError("API key invalid")):
                reply = await self.conv.handle(self.owner, "Find real plumbers in Mandi, Himachal Pradesh.", self.bus)
                self.assertIn("Google Places search could not be completed", reply["text"])
                self.assertIn("No fictional demo providers were substituted", reply["text"])
                # Fictional demo plumbers (FlowFix, TapCare) MUST NOT appear
                self.assertNotIn("FlowFix", reply["text"])
                self.assertNotIn("TapCare", reply["text"])

        asyncio.run(run_test())

    def test_ambiguous_location_clarification(self):
        """Tests that an ambiguous typo in location triggers a clarification question rather than guessing."""
        async def run_test():
            # 'indiranagr' has a suggestion 'indiranagar' in locations.py
            reply = await self.conv.handle(self.owner, "Find real AC service in Indiranagr", self.bus)
            self.assertIn("Did you mean Indiranagar?", reply["text"])
            self.assertIn("Reply yes to search Google Maps there", reply["text"])

        asyncio.run(run_test())

    def test_missing_location_asks_for_details(self):
        """Tests that a search without location asks for city and locality."""
        async def run_test():
            reply = await self.conv.handle(self.owner, "Find real plumbers", self.bus)
            self.assertIn("Please specify your city and locality in India", reply["text"])

    def test_zero_coverage_booking_offers_places_search_button(self):
        """When an accepted location has no onboarded coverage, card offers Google Maps search CTA."""
        async def run_test():
            # Mandi, HP has no onboarded demo provider
            reply = await self.conv.handle(
                self.owner,
                "Plumbing in Mandi, Himachal Pradesh tomorrow 10am under INR 1000",
                self.bus,
            )
            self.assertIn("Your location was accepted", reply["text"])
            self.assertIn("No onboarded demo provider currently covers", reply["text"])
            self.assertIn("To discover real local businesses on Google Maps", reply["text"])

            payload = json.loads(reply["metadata"]["card_payload"])
            cta = payload["ctas"][0]
            self.assertEqual(cta["selection"]["action"], "places_search")
            self.assertEqual(cta["selection"]["service"], "plumbing")

        asyncio.run(run_test())


    def test_booking_constraints_do_not_trigger_discovery(self):
        self.assertIsNone(parse_places_intent('Find AC service in Indiranagar Bengaluru tomorrow 10am under INR 1000'))
        self.assertIsNone(parse_places_intent('Find real plumbers in Mandi today under INR 500'))
        self.assertIsNone(parse_places_intent('Find AC service in Indiranagar Bengaluru at 10am'))

    def test_unsafe_links_and_malformed_fields_cannot_render_external_destinations(self):
        bad = normalize_place({'id': 'ChIJ1', 'displayName': {'text': 42}, 'formattedAddress': {},
                               'rating': float('nan'), 'userRatingCount': True,
                               'googleMapsUri': 'https://maps.google.com.evil.example/steal'})
        self.assertIsNone(bad['rating'])
        self.assertIsNone(bad['review_count'])
        self.assertNotIn('evil.example', bad['google_maps_uri'])
        card = cards.places_results([dict(bad, google_maps_uri='javascript:alert(1)')], 'plumbers')
        self.assertNotIn('javascript:', card['text'])
        async def run_test():
            reply = await self.conv.handle(self.owner, json.dumps({'action': 'view_maps', 'url': 'https://evil.example'}), self.bus)
            self.assertNotIn('https://evil.example', reply['text'])
            self.assertIn('Only an HTTPS Google Maps', reply['text'])
        asyncio.run(run_test())

    def test_upstream_and_transport_errors_never_echo_credentials(self):
        secret = 'synthetic-private-google-key'
        async def run_test():
            for outcome in (httpx.Response(400, json={'error': {'message': secret}}), httpx.RequestError(secret)):
                kwargs = {'side_effect': outcome} if isinstance(outcome, Exception) else {'return_value': outcome}
                with patch('httpx.AsyncClient.post', new_callable=AsyncMock, **kwargs), patch('asyncio.sleep', new_callable=AsyncMock):
                    with self.assertRaises(PlacesApiError) as caught:
                        await search_places('plumbers in Mandi', api_key=secret)
                    self.assertNotIn(secret, str(caught.exception))
        asyncio.run(run_test())

    def test_invalid_upstream_json_or_schema_is_safe(self):
        async def run_test():
            for response in (httpx.Response(200, text='not json'), httpx.Response(200, json=[]), httpx.Response(200, json={'places': {}})):
                with patch('httpx.AsyncClient.post', new_callable=AsyncMock, return_value=response):
                    with self.assertRaises(PlacesApiError):
                        await search_places('plumbers in Mandi', api_key='synthetic-key')
        asyncio.run(run_test())

    def test_page_limit_applies_to_request_and_response(self):
        async def run_test():
            response = httpx.Response(200, json={'places': [{'id': str(i)} for i in range(12)]})
            with patch('httpx.AsyncClient.post', new_callable=AsyncMock, return_value=response) as post:
                found = await search_places('plumbers in Mandi', api_key='synthetic-key', page_size=100)
                self.assertEqual(len(found), 5)
                self.assertEqual(post.call_args.kwargs['json']['pageSize'], 5)
        asyncio.run(run_test())

    def test_custom_endpoint_cannot_receive_key(self):
        async def run_test():
            with patch('httpx.AsyncClient.post', new_callable=AsyncMock) as post:
                with self.assertRaises(PlacesApiError):
                    await search_places('plumbers', api_key='synthetic-key', endpoint='https://evil.example')
                post.assert_not_called()
        asyncio.run(run_test())

    def test_core_import_does_not_require_optional_httpx(self):
        import subprocess, sys
        script = '''import builtins
original = builtins.__import__
def without_httpx(name, *args, **kwargs):
    if name == 'httpx' or name.startswith('httpx.'):
        raise ImportError('optional httpx unavailable')
    return original(name, *args, **kwargs)
builtins.__import__ = without_httpx
import servicesetu.conversation
'''
        result = subprocess.run([sys.executable, '-c', script], capture_output=True, text=True, timeout=10)
        self.assertEqual(result.returncode, 0, result.stderr)


if __name__ == "__main__":
    unittest.main()
