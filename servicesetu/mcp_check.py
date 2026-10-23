"""Small read-only backend checks. Never creates Taskrabbit drafts or bookings."""
import argparse
import asyncio
import json
import logging
from datetime import datetime, timezone
from pathlib import Path

from .discovery import TomTom, Taskrabbit
from .external_mcp import MCPGateway, ExternalError, TOOLS


async def check(args):
    gateway = MCPGateway()
    report = {'provider': args.provider, 'operation': args.operation,
              'checked_at': datetime.now(timezone.utc).isoformat(), 'read_only': True,
              'asi_one_rendering_checked': False, 'booking_created': False, 'payment_made': False}
    try:
        if args.operation == 'tools':
            async def operation(tools):
                # Public tool schemas only. No credentials or customer data.
                return {name: tools.schema(name) for name in sorted(tools.tools) if name in TOOLS[args.provider]}
            schemas = await gateway.run(args.provider, operation)
            report['tools'] = list(schemas)
            print(json.dumps(schemas, indent=2))
        elif args.provider == 'tomtom':
            adapter = TomTom(gateway)
            if args.operation == 'geocode':
                data = await adapter.geocode(args.location)
            elif args.operation == 'search':
                data = await adapter.search(args.service,args.location)
            elif args.operation == 'route':
                data = await adapter.route(args.origin,args.destination)
            else:
                raise ExternalError('input','Use tools, geocode, search or route for TomTom.')
            report['result_count'] = len(data) if isinstance(data,list) else 1
            report['country_filter'] = 'IN'
            if isinstance(data,dict):report['route_units']={'distance':'meters','duration':'seconds'}
        else:
            adapter = Taskrabbit(gateway)
            location = {'country':args.country,'postal':args.postal,'city':args.city,'state':args.state}
            if args.operation == 'services':
                data = await adapter.services(**location)
                report['service_count'] = len(data.get('services',[]))
            elif args.operation == 'availability':
                data = await adapter.check(args.service,**location)
                report['available'] = data.get('available')
                report['currency'] = data.get('pricing',{}).get('currency')
                report['scoping_question_count'] = len(data.get('scopingQuestions',[]))
            else:
                raise ExternalError('input','Use tools, services or availability for Taskrabbit. Draft generation is not a read-only check.')
        report['status'] = 'passed'
    except ExternalError as error:
        report.update(status='blocked',code=error.code,message=str(error))
    path=Path('artifacts/local')/f'mcp-{args.provider}-{args.operation}.json'
    path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(json.dumps(report,indent=2))
    print(json.dumps(report,indent=2))
    return report['status']=='passed'


def main():
    from dotenv import load_dotenv
    load_dotenv()
    logging.getLogger('httpx').setLevel(logging.CRITICAL)
    logging.getLogger('mcp').setLevel(logging.CRITICAL)
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('provider',choices=['tomtom','taskrabbit'])
    parser.add_argument('operation',choices=['tools','geocode','search','route','services','availability'])
    for name in ('service','location','origin','destination','country','postal','city','state'):
        parser.add_argument('--'+name,default='')
    args=parser.parse_args()
    if not asyncio.run(check(args)):raise SystemExit(2)


if __name__=='__main__':main()
