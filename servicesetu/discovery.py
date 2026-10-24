"""Read-only map discovery and explicitly requested Taskrabbit draft links."""
import math
import re
from urllib.parse import urlsplit

from .external_mcp import MCPGateway, ExternalError, clean_text


def query_text(value):
    if not isinstance(value, str) or not value.strip() or len(value) > 500:
        raise ExternalError('input', 'Provide a service and a specific location, up to 500 characters.')
    return value.strip()


def coordinates(value):
    if not isinstance(value, (list, tuple)) or len(value) != 2:
        raise ExternalError('input', 'Coordinates must contain longitude followed by latitude.')
    if any(isinstance(x, bool) or not isinstance(x, (int, float)) or not math.isfinite(x) for x in value):
        raise ExternalError('input', 'Coordinates must be finite numbers.')
    if not -180 <= value[0] <= 180 or not -90 <= value[1] <= 90:
        raise ExternalError('input', 'Coordinates are out of range.')
    return list(value)


def public_business_phone(value):
    """Accept a listing phone as display text, never arbitrary links or commands."""
    if not isinstance(value, str):
        return None
    value = value.strip()
    if not re.fullmatch(r'\+?[0-9 ()-]{6,39}', value):
        return None
    if not 7 <= len(re.sub(r'\D', '', value)) <= 15:
        return None
    return value


def normalize_locations(data, country='IN', businesses=False):
    rows = data.get('features', data.get('results'))
    if not isinstance(rows, list):
        raise ExternalError('schema', 'TomTom returned an unsupported location response.')
    result = []
    for row in rows[:20]:
        if not isinstance(row, dict):
            continue
        props = row.get('properties', row)
        if not isinstance(props, dict):
            continue
        address = props.get('address', {})
        if not isinstance(address, dict):
            continue
        if address.get('countryCode') != country:
            continue
        poi = props.get('poi') or {}
        if not isinstance(poi,dict):
            continue
        if businesses and (not isinstance(poi, dict) or not poi.get('name')):
            continue
        geometry = row.get('geometry') or {}
        point = geometry.get('coordinates') if isinstance(geometry, dict) and geometry.get('type') == 'Point' else props.get('position')
        if isinstance(point, dict):
            point = [point.get('lon'), point.get('lat')]
        try:
            point = coordinates(point)
        except ExternalError:
            continue
        listing = {'id': 'tomtom:' + clean_text(row.get('id') or len(result), 150),
            'name': clean_text(poi.get('name') or address.get('freeformAddress') or 'Location', 160),
            'address': clean_text(address.get('freeformAddress'), 350), 'position': point,
            'country': country, 'source': 'tomtom', 'onboarded': False}
        phone = public_business_phone(poi.get('phone')) if businesses else None
        if phone:
            listing['phone'] = phone
        result.append(listing)
        if len(result) == 5:
            break
    return result


class TomTom:
    def __init__(self, gateway=None):
        self.gateway = gateway or MCPGateway()

    async def geocode(self, query, owner='operator'):
        query = query_text(query)
        async def operation(tools):
            args = tools.arguments('tomtom-geocode', {'query': query}, {'countries': ['IN'], 'limit': 5, 'response_detail': 'compact'})
            return normalize_locations(await tools.call('tomtom-geocode', args))
        return await self.gateway.run('tomtom', operation, owner)

    async def search(self, service, location, owner='operator'):
        service, location = query_text(service), query_text(location)
        async def operation(tools):
            # Fuzzy search accepts natural service terms; no guessed POI category codes.
            args = tools.arguments('tomtom-fuzzy-search', {'query': f'{service} in {location}'},
                {'countries': ['IN'], 'idxSet': 'POI', 'limit': 5, 'response_detail': 'full'})
            return normalize_locations(await tools.call('tomtom-fuzzy-search', args), businesses=True)
        return await self.gateway.run('tomtom', operation, owner)

    async def route(self, origin, destination, owner='operator'):
        origin, destination = query_text(origin), query_text(destination)
        async def operation(tools):
            points = []
            for query in (origin, destination):
                args = tools.arguments('tomtom-geocode', {'query': query}, {'countries': ['IN'], 'limit': 3, 'response_detail': 'compact'})
                matches = normalize_locations(await tools.call('tomtom-geocode', args))
                if len(matches) != 1:
                    raise ExternalError('location', 'The route address is missing or ambiguous. Provide a more specific origin and destination in India.')
                points.append(matches[0])
            args = tools.arguments('tomtom-routing', {'locations': [p['position'] for p in points]}, {'response_detail': 'compact'})
            data = await tools.call('tomtom-routing', args)
            routes = data.get('routes', data.get('features'))
            if not isinstance(routes, list) or not routes or not isinstance(routes[0], dict):
                raise ExternalError('schema', 'TomTom did not return a usable route estimate.')
            summary = routes[0].get('properties', routes[0]).get('summary', {})
            distance = summary.get('lengthInMeters')
            seconds = summary.get('travelTimeInSeconds')
            if any(isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(v) or v < 0 for v in (distance, seconds)):
                raise ExternalError('schema', 'TomTom returned invalid route distance or duration.')
            return {'origin': points[0]['address'], 'destination': points[1]['address'], 'meters': distance, 'seconds': seconds}
        return await self.gateway.run('tomtom', operation, owner)


class Taskrabbit:
    def __init__(self, gateway=None):
        self.gateway = gateway or MCPGateway()

    @staticmethod
    def location(country, postal='', city='', state=''):
        if str(country).upper() == 'IN':
            raise ExternalError('geography', 'Taskrabbit is unavailable in India. No overseas location has been substituted. Use TomTom local discovery for India.')
        if str(country).upper() != 'US':
            raise ExternalError('geography', 'This MCP connector currently supports US locations only, even though Taskrabbit operates in other countries. No location has been substituted.')
        if postal:
            if not re.fullmatch(r'\d{5}', str(postal)):
                raise ExternalError('input', 'Provide an explicit US five-digit ZIP code, or city and state. Indian PIN codes cannot be used here.')
            return {'postalCode': str(postal)}
        if not city or not re.fullmatch(r'[A-Za-z]{2}', state):
            raise ExternalError('input', 'Provide the US city and two-letter state, or a five-digit US ZIP code.')
        return {'city': query_text(city), 'state': state.upper()}

    async def services(self, country, postal='', city='', state='', owner='operator'):
        location = self.location(country, postal, city, state)
        async def operation(tools):
            return await tools.call('list_supported_services', location)
        return await self.gateway.run('taskrabbit', operation, owner)

    async def check(self, service, country, postal='', city='', state='', owner='operator'):
        location = self.location(country, postal, city, state)
        async def operation(tools):
            return await tools.call('check_service_availability', dict(location, service=query_text(service)))
        data = await self.gateway.run('taskrabbit', operation, owner)
        if data.get('available') is True:
            loc = data.get('location') or {}
            if (not isinstance(loc, dict) or not re.fullmatch(r'\d{5}', str(loc.get('postal_code', '')))
                    or not loc.get('address') or not data.get('categoryId') or not isinstance(data.get('scopingQuestions'), list)):
                raise ExternalError('schema', 'Taskrabbit availability lacks the required location or scoping details.')
            coordinates([loc.get('lng'), loc.get('lat')])
            if 'postalCode' in location and loc['postal_code'] != location['postalCode']:
                raise ExternalError('geography', 'Taskrabbit returned a different location. Please check your requested ZIP code.')
            questions=data['scopingQuestions']
            if (len(questions)>12 or any(not isinstance(q,dict) or not isinstance(q.get('question'),str)
                    or not isinstance(q.get('param'),str) or not q['param']
                    or not isinstance(q.get('options',[]),list) or len(q.get('options',[]))>20
                    or any(not isinstance(o,dict) or not isinstance(o.get('value',o.get('id')),str)
                           for o in q.get('options',[])) for q in questions)):
                raise ExternalError('schema','Taskrabbit returned unsupported scoping questions.')
            if not isinstance(data.get('topTaskers',[]),list) or any(not isinstance(t,dict) for t in data.get('topTaskers',[])[:3]):
                raise ExternalError('schema','Taskrabbit returned unsupported marketplace suggestions.')
        return data

    async def deep_link(self, availability, questionnaire, owner):
        # A link creates a draft, never a ServiceSetu booking or a reservation.
        if availability.get('available') is not True:
            raise ExternalError('availability', 'Check Taskrabbit availability before requesting a draft link.')
        async def operation(tools):
            return await tools.call('generate_deep_link', {'categoryId': availability['categoryId'],
                'locale': 'en-US', 'questionnaire': questionnaire, 'location': availability['location']})
        data = await self.gateway.run('taskrabbit', operation, owner, read_only=False)
        url = data.get('deepLink') or data.get('url') or data.get('deep_link')
        try:
            parts = urlsplit(url) if isinstance(url, str) else None
            if parts:parts.port
        except ValueError:
            raise ExternalError('schema','Taskrabbit returned an invalid booking link.') from None
        if (not parts or parts.scheme != 'https' or parts.hostname not in ('taskrabbit.com', 'www.taskrabbit.com')
                or parts.username or parts.password or parts.port or len(url) > 3000 or any(c.isspace() for c in url)):
            raise ExternalError('schema', 'Taskrabbit did not return a supported secure booking link. No ServiceSetu booking was made.')
        return url
