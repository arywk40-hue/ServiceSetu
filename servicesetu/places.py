"""Google Places API (New) Text Search client for live local-service discovery.

Enforces server-side bounded access, explicit field masks, and strict booking boundaries.
Business details are not cached in SQLite; sessions retain discovered place IDs.
"""
from __future__ import annotations
import math
import os
import re
import urllib.parse
from typing import Optional, List, Dict, Any

from .catalogue import SERVICES, detect_service
from .locations import mentions, canonical, suggestion, ALIASES, LOCATION_FIELDS

DEFAULT_ENDPOINT = "https://places.googleapis.com/v1/places:searchText"
DEFAULT_FIELD_MASK = (
    "places.id,"
    "places.displayName,"
    "places.formattedAddress,"
    "places.googleMapsUri,"
    "places.rating,"
    "places.userRatingCount,"
    "places.businessStatus,"
    "places.pureServiceAreaBusiness"
)
DEFAULT_TIMEOUT_SECONDS = 6.0
DEFAULT_PAGE_SIZE = 5


class PlacesError(Exception):
    """Base exception for Google Places operations."""


class PlacesMissingKeyError(PlacesError):
    """Raised when GOOGLE_PLACES_API_KEY is not configured in the environment."""


class PlacesAuthError(PlacesError):
    """Raised when Google Places API authentication fails (401/403)."""


class PlacesQuotaError(PlacesError):
    """Raised when Google Places API quota is exceeded (429 / RESOURCE_EXHAUSTED)."""


class PlacesTimeoutError(PlacesError):
    """Raised when Google Places API times out."""


class PlacesApiError(PlacesError):
    """Raised when Google Places API returns an unhandled error status."""


def safe_maps_url(value):
    """Accept only HTTPS Google Maps links, including card selections."""
    if not isinstance(value, str):
        return None
    try:
        p = urllib.parse.urlsplit(value)
        if p.scheme != 'https' or p.username or p.password or p.port not in (None, 443):
            return None
        if p.hostname == 'maps.google.com':
            return value
        if p.hostname in ('www.google.com', 'google.com') and (p.path == '/maps' or p.path.startswith('/maps/')):
            return value
    except ValueError:
        pass
    return None


def normalize_place(item: Dict[str, Any]) -> Dict[str, Any]:
    """Normalize a place item from the Places API (New) Text Search response."""
    display_name = item.get("displayName")
    if isinstance(display_name, dict):
        text = display_name.get("text")
        name = text.strip()[:200] if isinstance(text, str) and text.strip() else "Local Business"
    elif isinstance(display_name, str):
        name = display_name.strip() or "Local Business"
    else:
        name = "Local Business"

    place_id = item.get("id") if isinstance(item.get("id"), str) else ""
    is_service_area = bool(item.get("pureServiceAreaBusiness"))
    formatted_address = item.get("formattedAddress") if isinstance(item.get("formattedAddress"), str) else None

    rating = item.get("rating")
    if type(rating) in (int, float) and math.isfinite(rating) and 0 <= rating <= 5:
        rating = round(float(rating), 1)
    else:
        rating = None

    review_count = item.get("userRatingCount")
    if type(review_count) is not int or review_count < 0:
        review_count = None

    google_maps_uri = safe_maps_url(item.get("googleMapsUri"))
    if not google_maps_uri and place_id:
        clean_id = place_id.split("/")[-1]
        google_maps_uri = f"https://www.google.com/maps/place/?q=place_id:{urllib.parse.quote(clean_id)}"
    elif not google_maps_uri:
        search_query = f"{name} {formatted_address or ''}".strip()
        google_maps_uri = f"https://www.google.com/maps/search/?api=1&query={urllib.parse.quote(search_query)}"

    return {
        "id": place_id,
        "name": name,
        "address": formatted_address,
        "is_service_area": is_service_area,
        "rating": rating,
        "review_count": review_count,
        "google_maps_uri": google_maps_uri,
        "business_status": item.get("businessStatus"),
        "source": "google_maps",
        "onboarded": False,
    }


async def search_places(
    query: str,
    api_key: Optional[str] = None,
    page_size: int = DEFAULT_PAGE_SIZE,
    timeout: float = DEFAULT_TIMEOUT_SECONDS,
    endpoint: str = DEFAULT_ENDPOINT,
    client: Optional[Any] = None,
) -> List[Dict[str, Any]]:
    """Search Google Places API (New) via Text Search.

    Server-side only. Does not expose keys in cards or logs.
    """
    if endpoint != DEFAULT_ENDPOINT:
        raise PlacesApiError("Google Places requests must use the configured official endpoint.")
    if not isinstance(query, str) or not 1 <= len(query.strip()) <= 300:
        raise PlacesApiError("Provide a service and location in a search of at most 300 characters.")
    page_size = max(1, min(int(page_size), 5))
    resolved_key = (api_key or os.getenv("GOOGLE_PLACES_API_KEY") or "").strip()
    if not resolved_key:
        raise PlacesMissingKeyError(
            "Google Places API key is not configured (GOOGLE_PLACES_API_KEY is missing from the environment). "
            "Please configure GOOGLE_PLACES_API_KEY in .env to discover real local businesses on Google Maps."
        )

    # Keep the no-key core booking/demo commands usable without optional extras.
    try:
        import httpx
    except ImportError:
        raise PlacesApiError("Install the project's external extras to enable Google Places discovery.") from None

    headers = {
        "Content-Type": "application/json",
        "X-Goog-Api-Key": resolved_key,
        "X-Goog-FieldMask": DEFAULT_FIELD_MASK,
    }

    body = {
        "textQuery": query,
        "pageSize": max(1, min(page_size, 5)),
        "languageCode": "en",
        "regionCode": "IN",
    }

    async def _execute_post(http_client: httpx.AsyncClient) -> httpx.Response:
        return await http_client.post(endpoint, json=body, headers=headers, timeout=timeout)

    should_close_client = False
    if client is None:
        client = httpx.AsyncClient(timeout=timeout)
        should_close_client = True

    try:
        response = None
        for attempt in range(2):
            try:
                response = await _execute_post(client)
                if response.status_code >= 500 and attempt == 0:
                    import asyncio
                    await asyncio.sleep(0.5)
                    continue
                break
            except httpx.TimeoutException:
                if attempt == 0:
                    import asyncio
                    await asyncio.sleep(0.5)
                    continue
                raise PlacesTimeoutError(
                    f"Google Places API request timed out after {timeout} seconds."
                ) from None
            except httpx.RequestError:
                if attempt == 0:
                    import asyncio
                    await asyncio.sleep(0.5)
                    continue
                raise PlacesApiError(
                    "Google Places network connection failed. Please try again later."
                ) from None

        if response is None:
            raise PlacesApiError("No response received from Google Places API.")

        if response.status_code == 200:
            if len(response.content) > 200_000:
                raise PlacesApiError("Google Places returned an oversized response.")
            try:
                # Even a malformed upstream response must not echo the API key.
                import json
                data = json.loads(response.text.replace(resolved_key, '[redacted]'))
            except (ValueError, TypeError):
                raise PlacesApiError("Google Places returned an invalid response.") from None
            if not isinstance(data, dict) or not isinstance(data.get('places', []), list):
                raise PlacesApiError("Google Places returned an unsupported response format.")
            raw_places = data.get("places", [])
            return [normalize_place(p) for p in raw_places[:page_size] if isinstance(p, dict)]
        elif response.status_code in (401, 403):
            raise PlacesAuthError(
                "Google Places API authentication failed (invalid or restricted API key). "
                "Check your GOOGLE_PLACES_API_KEY in .env and verify that Places API (New) is enabled."
            )
        elif response.status_code == 429:
            raise PlacesQuotaError(
                "Google Places API quota exceeded or rate limit reached. Please try again later."
            )
        else:
            raise PlacesApiError(
                f"Google Places API error (HTTP {response.status_code}). Please try again later."
            )
    finally:
        if should_close_client:
            await client.aclose()


def parse_places_intent(text: str) -> Optional[Dict[str, Any]]:
    """Detect if customer text is an intent to discover real local businesses.

    Supports prompts such as:
    - Find real plumbers in Mandi, Himachal Pradesh.
    - Find AC service businesses in Indiranagar, Bengaluru.
    - Find cleaning services in Powai, Mumbai.
    - Find real plumbers in Mandi
    - Search real cleaning businesses in Powai
    """
    clean = text.strip()
    low = clean.lower()

    # Reject obvious booking instructions with appointment dates or budget constraints
    has_booking_constraints = bool(
        re.search(r"\b(tomorrow|today|\d{4}-\d{2}-\d{2}|under|budget|rs\.?|inr|₹|paise|approve|reject|quote|appointment|at\s+\d{1,2}|\d{1,2}(?::\d{2})?\s*(?:am|pm))\b", low)
    )
    if has_booking_constraints:
        return None

    # Keywords indicating live provider discovery
    has_live_keyword = bool(
        re.search(r"\b(real|actual|businesses|business|google maps?|places?|unonboarded|external)\b", low)
    )

    # Patterns matching "Find [service] [businesses/services] in [location]"
    direct_pattern = re.match(
        r"^\s*(?:find|search|show|lookup|discover)\s+(?:real\s+)?(?:local\s+)?(.+?)\s+in\s+(.+?)[\.?!]?\s*$",
        clean,
        re.IGNORECASE,
    )

    if direct_pattern:
        service_part = direct_pattern.group(1).strip()
        location_part = direct_pattern.group(2).strip()

        # Check if service_part or whole text mentions real / businesses / services
        is_places_search = has_live_keyword or re.search(r"\b(services?|businesses?|providers?|shops?|plumbers?|cleaners?)\b", service_part, re.I)

        if not has_booking_constraints or is_places_search:
            service_key = detect_service(service_part) or detect_service(clean)
            return _build_places_query(service_key, service_part, location_part)

    # Fallback pattern for "plumbers in Mandi" with "real" or "google maps"
    if has_live_keyword and not has_booking_constraints:
        in_match = re.search(r"\bin\s+([^,;\n]+(?:,[^,;\n]+)?)\b", clean, re.IGNORECASE)
        if in_match:
            location_part = in_match.group(1).strip()
            service_key = detect_service(clean)
            service_part = SERVICES[service_key]["label"] if service_key else "services"
            return _build_places_query(service_key, service_part, location_part)

    return None


def _build_places_query(
    service_key: Optional[str],
    service_part: str,
    location_part: str,
) -> Dict[str, Any]:
    """Build normalized query dictionary for Google Places."""
    clean_loc = location_part.strip(" .?!,")
    clean_service = service_part.strip()

    # Clean up prefixes like "real ", "local "
    clean_service_text = re.sub(r"^(?:real|local)\s+", "", clean_service, flags=re.I).strip()

    # Formulate effective search query for Places API (New)
    query = f"{clean_service_text} in {clean_loc}"

    return {
        "is_places_search": True,
        "service": service_key,
        "service_text": clean_service_text,
        "location": clean_loc,
        "query": query,
    }


def check_places_key():
    """Perform a small live search if GOOGLE_PLACES_API_KEY is configured."""
    import asyncio
    async def _check():
        key = (os.getenv("GOOGLE_PLACES_API_KEY") or "").strip()
        if not key:
            print("Status: GOOGLE_PLACES_API_KEY is not configured in .env / environment.")
            print("Blocker: Live verification with Google Places API requires an active GOOGLE_PLACES_API_KEY.")
            print("Setup: See docs/places-discovery.md or .env.example for Google Cloud setup instructions.")
            return False
        print("GOOGLE_PLACES_API_KEY is present. Performing live search for 'plumbers in Mandi, Himachal Pradesh'...")
        try:
            results = await search_places("plumbers in Mandi, Himachal Pradesh", page_size=2)
            print(f"Success! Found {len(results)} live business(es) via Google Places API (New):")
            for r in results:
                addr = r.get("address") or ("Service-area business" if r.get("is_service_area") else "Location supplied on Maps")
                rating_str = f"Rating: {r.get('rating')} ★ ({r.get('review_count')} reviews)" if r.get('rating') else "No rating"
                print(f" - {r['name']} | {addr} | {rating_str}")
                print(f"   Listing: {r.get('google_maps_uri')}")
            return True
        except PlacesError as exc:
            print(f"Live search failed: {exc}")
            return False

    return asyncio.run(_check())


if __name__ == "__main__":
    from dotenv import load_dotenv
    load_dotenv()
    check_places_key()
