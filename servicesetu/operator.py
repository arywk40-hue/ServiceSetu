"""Trusted local operator commands. No public onboarding or remote admin API."""
import argparse
import json
import os
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo
from .core import Store,Rejected,encode
from .locations import canonical,pin_code


def import_pilot(store,config):
    """Reuse p4 and its registered seed-derived identity, in an isolated DB."""
    if not isinstance(config,dict):raise Rejected('A pilot configuration object is required')
    if config.get('provider_id')!='p4' or config.get('service')!='plumbing':raise Rejected('This narrow pilot reuses p4 for one plumbing visit package')
    if config.get('permission_obtained') is not True or config.get('availability_confirmed') is not True:raise Rejected('Record actual provider agreement and confirmed availability first')
    fields=('name','scope','exclusions','operator','agreement_reference')
    if any(not isinstance(config.get(f),str) or not 1<=len(config[f].strip())<=1000 for f in fields):raise Rejected('Business name, scope, exclusions, operator and private agreement reference are required')
    amount=config.get('amount_paise')
    if type(amount) is not int or not 0<amount<=10000000:raise Rejected('Set a positive fixed total in paise')
    city=canonical(config.get('city'),'city');area=canonical(config.get('area'),'area')
    if not city or not area:raise Rejected('Specify one Indian city and service area')
    pins=config.get('pincodes',[])
    if not isinstance(pins,list) or any(not isinstance(p,str) or pin_code(p)!=p for p in pins):raise Rejected('PIN codes must be six-digit strings')
    slots=config.get('slots')
    if not isinstance(slots,list) or not 1<=len(slots)<=28:raise Rejected('Enter 1–28 provider-confirmed appointment slots')
    normalized=[]
    for value in slots:
        try:
            dt=datetime.fromisoformat(value)
            if dt.tzinfo is None or dt.timestamp()<=store.clock():raise ValueError()
        except (ValueError,TypeError):raise Rejected('Appointment slots must be future ISO timestamps with timezone') from None
        normalized.append(dt.astimezone(ZoneInfo('Asia/Kolkata')).isoformat())
    checks=config.get('checked_items')
    if not isinstance(checks,list) or not checks or any(not isinstance(x,str) or not 1<=len(x.strip())<=300 for x in checks):raise Rejected('Describe exactly what the operator checked')
    try:
        valid_until=datetime.strptime(config['review_valid_until'],'%Y-%m-%d').date().isoformat()
        if valid_until<max(datetime.fromisoformat(x).date().isoformat() for x in normalized):raise ValueError()
    except (KeyError,ValueError,TypeError):raise Rejected('Manual review validity must cover all appointments') from None
    store.seed()
    now=datetime.fromtimestamp(store.clock(),ZoneInfo('Asia/Kolkata')).isoformat()
    provider=dict(id='p4',name=config['name'].strip(),service='plumbing',city=city,area=area,amount=amount,
                  slots=sorted(set(normalized)),available=True,record_kind='pilot',pilot_scope=config['scope'].strip(),
                  pilot_exclusions=config['exclusions'].strip(),coverage=[dict(country='IN',city=city,areas=[area],pincodes=pins)],
                  credential=dict(type='manual_pilot_review',jurisdiction='IN',issuer='Local pilot operator',status='manually_reviewed',
                                  source='Private operator agreement record',checked_at=now,expires=valid_until,method='manual_review',
                                  verifier=config['operator'].strip(),checked_items=[x.strip() for x in checks],policy_version='pilot-v1'))
    with store.tx() as db:
        store.expire(db)
        if db.execute("SELECT 1 FROM bookings WHERE state IN ('held','confirmed') LIMIT 1").fetchone():raise Rejected('Release or complete active bookings before changing pilot configuration')
        for row in db.execute('SELECT id,payload FROM providers').fetchall():
            old=json.loads(row['payload']);old['available']=False
            db.execute('UPDATE providers SET payload=? WHERE id=?',(encode(old),row['id']))
        db.execute('UPDATE providers SET payload=? WHERE id=?',(encode(provider),'p4'))
        store.event(db,'p4','pilot_configuration_recorded','operator',operator=config['operator'].strip(),agreement_reference=config['agreement_reference'],record_kind='pilot')
    return provider


def accept(store,bid,operator):
    if not operator.strip():raise Rejected('Operator name is required')
    with store.tx() as db:
        b=db.execute('SELECT * FROM bookings WHERE id=?',(bid,)).fetchone()
        if not b or b['state']!='held' or b['hold_until']<=store.clock():raise Rejected('Accept only a current held booking; otherwise ask for a fresh quote')
        q=store.get_quote(b['quote'],b['owner']);p=store.provider(b['provider'])
        if p.get('record_kind')!='pilot' or q.get('record_kind')!='pilot':raise Rejected('Only pilot bookings need operator acceptance')
        if not p['available'] or b['slot'] not in p['slots']:raise Rejected('Provider is no longer available')
        old=db.execute("SELECT 1 FROM events WHERE entity=? AND kind='pilot_booking_accepted' AND json_extract(payload,'$.quote')=?",(bid,b['quote'])).fetchone()
        if not old:store.event(db,bid,'pilot_booking_accepted','operator',operator=operator.strip(),quote=b['quote'])


def write_private(path,value):
    path=Path(path)
    if path.suffix.lower()!='.json' or 'data' not in path.parts:raise Rejected('Save private operator exports as JSON under an ignored data/ directory')
    path.parent.mkdir(parents=True,exist_ok=True)
    fd=os.open(path,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
    with os.fdopen(fd,'w') as out:json.dump(value,out,indent=2)


def main():
    try:
        from dotenv import load_dotenv
        load_dotenv()
    except ImportError:pass
    parser=argparse.ArgumentParser(description='Private local ServiceSetu pilot operator')
    parser.add_argument('--db',required=True)
    sub=parser.add_subparsers(dest='command',required=True)
    imp=sub.add_parser('import-pilot');imp.add_argument('--config',required=True)
    sub.add_parser('queue')
    accepted=sub.add_parser('accept');accepted.add_argument('booking');accepted.add_argument('--operator',required=True)
    cancel=sub.add_parser('cancel');cancel.add_argument('booking');cancel.add_argument('--operator',required=True)
    reports=sub.add_parser('reports');reports.add_argument('--output',required=True)
    ack=sub.add_parser('acknowledge');ack.add_argument('report');ack.add_argument('--operator',required=True)
    args=parser.parse_args()
    if args.command!='import-pilot' and not Path(args.db).is_file():parser.error('Choose the existing pilot database')
    try:
        store=Store(args.db)
        if args.command=='import-pilot':
            import_pilot(store,json.loads(Path(args.config).read_text()))
            print('Pilot p4 configured; fictional alternatives disabled. Seed and registration identities unchanged. Test payments only.')
        elif args.command=='queue':
            with store.connect() as db:
                rows=db.execute("SELECT b.id,b.state,b.hold_until FROM bookings b JOIN providers p ON p.id=b.provider WHERE json_extract(p.payload,'$.record_kind')='pilot' AND b.state IN ('held','confirmed') ORDER BY b.rowid").fetchall()
            print(json.dumps([dict(r) for r in rows],indent=2))
        elif args.command=='accept':
            accept(store,args.booking,args.operator);print('Provider acceptance recorded for the current quote; customer approval and test payment are still required.')
        elif args.command=='cancel':
            from .payments import Payments
            with store.connect() as db:row=db.execute('SELECT owner,provider FROM bookings WHERE id=?',(args.booking,)).fetchone()
            if not row or store.provider(row['provider']).get('record_kind')!='pilot':raise Rejected('Pilot booking unavailable')
            Payments(store).cancel(row['owner'],args.booking,'provider:'+row['provider'])
            print('Provider cancellation recorded. Customer notice queued; inspect payment status for pending compensation.')
        elif args.command=='reports':
            from .problems import Problems
            write_private(args.output,Problems(store).queue());print('Private report export saved. Review locally; do not publish it.')
        else:
            from .problems import Problems
            Problems(store).acknowledge(args.report,args.operator);print('Operator acknowledgement recorded; no resolution or refund implied.')
    except (Rejected,ValueError,OSError) as exc:parser.error(str(exc) if isinstance(exc,Rejected) else 'Unable to read/write private operator input; check the local files')


if __name__=='__main__':main()
