"""Bounded MCP access to two fixed, explicitly allowed external services."""
from __future__ import annotations

import asyncio
from collections import OrderedDict, deque
from datetime import timedelta
import json
import os
import time
import logging

# SDK transport failures must not dump response bodies or task descriptions.
logging.getLogger('mcp.client').setLevel(logging.CRITICAL)

ENDPOINTS = {
    'tomtom': 'https://mcp.tomtom.com/maps?apps=false',
    'taskrabbit': 'https://mcp.taskrabbit.com/mcp',
}
TOOLS = {
    'tomtom': {'tomtom-geocode', 'tomtom-fuzzy-search', 'tomtom-routing'},
    'taskrabbit': {'list_supported_services', 'check_service_availability', 'generate_deep_link'},
}


class ExternalError(Exception):
    def __init__(self, code, message):
        self.code = code
        super().__init__(message)


def clean_text(value, limit=700):
    text = str(value or '')
    # Keys never belong in a response, even if an upstream error echoes one.
    key = os.getenv('TOMTOM_API_KEY')
    if key:
        text = text.replace(key, '[redacted]')
    return ''.join(c for c in text if c >= ' ' or c == '\n')[:limit]


def result_data(result):
    if getattr(result, 'isError', False):
        raise ExternalError('upstream', 'The external service rejected the request. Check service access or try again later.')
    data = getattr(result, 'structuredContent', None)
    if data is None:
        blocks = [getattr(c, 'text', '') for c in getattr(result, 'content', []) if getattr(c, 'type', '') == 'text']
        if len(blocks) != 1 or len(blocks[0]) > 200_000:
            raise ExternalError('schema', 'The external service returned an unsupported response format.')
        try:
            data = json.loads(blocks[0])
        except (ValueError, TypeError):
            raise ExternalError('schema', 'The external service returned an unsupported response format.') from None
    if not isinstance(data, dict) or len(json.dumps(data)) > 200_000:
        raise ExternalError('schema', 'The external service response was invalid or too large.')
    if data.get('error'):
        raise ExternalError('upstream', 'The external service could not complete this request.')
    return data


class RequestLimits:
    """Bound work per customer/session and across this process, without logging identities."""
    def __init__(self, clock=time.monotonic):
        self.clock = clock
        self.users = OrderedDict()
        self.global_requests = deque()

    def take(self, owner):
        now = self.clock()
        bucket = self.users.setdefault(owner, deque())
        self.users.move_to_end(owner)
        for q in (bucket, self.global_requests):
            while q and q[0] <= now - 60:
                q.popleft()
        if len(bucket) >= 8 or len(self.global_requests) >= 40:
            raise ExternalError('rate_limit', 'External lookup limit reached. Please wait a minute before trying again.')
        bucket.append(now)
        self.global_requests.append(now)
        while len(self.users) > 512:
            self.users.popitem(last=False)


LIMITS = RequestLimits()


class DiscoveredTools:
    def __init__(self, session, provider, tools):
        self.session, self.provider = session, provider
        self.tools = {t.name: t for t in tools}
        self.calls = 0

    def schema(self, name):
        if name not in TOOLS[self.provider] or name not in self.tools:
            raise ExternalError('schema', 'The external service does not currently expose the required supported tool.')
        return self.tools[name].inputSchema

    def arguments(self, name, required, optional=None):
        properties = self.schema(name).get('properties', {})
        return dict(required, **{k: v for k, v in (optional or {}).items() if k in properties})

    async def call(self, name, arguments):
        from jsonschema import Draft202012Validator
        from jsonschema.exceptions import ValidationError, SchemaError
        schema = self.schema(name)
        try:
            Draft202012Validator.check_schema(schema)
            Draft202012Validator(schema).validate(arguments)
        except (ValidationError, SchemaError):
            raise ExternalError('schema', 'Required external tool fields changed or are missing. Please reopen the request.') from None
        if self.calls >= 5 or len(json.dumps(arguments)) > 12_000:
            raise ExternalError('limit', 'This external lookup exceeded its request limit.')
        self.calls += 1
        result = await self.session.call_tool(name, arguments=arguments)
        return result_data(result)


def _leaves(error):
    for child in getattr(error, 'exceptions', ()):
        yield from _leaves(child)
    if not getattr(error, 'exceptions', None):
        yield error


class MCPGateway:
    def __init__(self, limits=None):
        self.limits = limits or LIMITS

    async def run(self, provider, operation, owner='operator', *, read_only=True):
        if provider not in ENDPOINTS:
            raise ExternalError('endpoint', 'Unsupported external service.')
        headers = {}
        if provider == 'tomtom':
            key = os.getenv('TOMTOM_API_KEY', '').strip()
            if not key:
                raise ExternalError('missing_key', 'TomTom discovery is not configured. The operator must set TOMTOM_API_KEY privately.')
            headers['tomtom-api-key'] = key
        try:
            import anyio
            import httpx
            from mcp import ClientSession
            from mcp.client.streamable_http import streamable_http_client
        except ImportError:
            raise ExternalError('setup', 'External integrations need the ServiceSetu external dependency extra installed.') from None
        self.limits.take(owner)
        for attempt in range(2 if read_only else 1):
            try:
                # Covers initialization, schema discovery, calls and transport cleanup.
                with anyio.fail_after(18):
                    async with httpx.AsyncClient(headers=headers, timeout=7, follow_redirects=False) as client:
                        async with streamable_http_client(ENDPOINTS[provider], http_client=client) as (read, write, _):
                            async with ClientSession(read, write, read_timeout_seconds=timedelta(seconds=7)) as session:
                                await session.initialize()
                                tools, cursor = [], None
                                for _page in range(2):
                                    page = await session.list_tools(cursor=cursor)
                                    tools.extend(page.tools)
                                    cursor = page.nextCursor
                                    if not cursor:
                                        break
                                if cursor or len(tools) > 80:
                                    raise ExternalError('schema', 'External tool discovery exceeded its supported limit.')
                                return await operation(DiscoveredTools(session, provider, tools))
            except Exception as error:
                leaves = list(_leaves(error))
                known = next((e for e in leaves if isinstance(e, ExternalError)), None)
                if known:
                    raise known from None
                codes = {e.response.status_code for e in leaves if isinstance(e, httpx.HTTPStatusError)}
                if codes & {401, 403}:
                    raise ExternalError('auth', 'External service access was refused. The operator must check account permissions or credentials.') from None
                if 429 in codes:
                    raise ExternalError('rate_limit', 'The external service rate limit was reached. Try again later.') from None
                retryable = any(isinstance(e, (TimeoutError, httpx.TransportError)) for e in leaves) or any(c >= 500 for c in codes)
                if attempt == 0 and read_only and retryable:
                    await asyncio.sleep(0.25)
                    continue
                raise ExternalError('unavailable', 'The external service is unavailable or timed out. No ServiceSetu booking or payment was created.') from None
