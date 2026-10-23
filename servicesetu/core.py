"""Deterministic marketplace. SQLite serializes consequences, never the model."""
from __future__ import annotations

import hashlib
import json
import sqlite3
import time
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path
from uuid import uuid4
from zoneinfo import ZoneInfo
from .locations import canonical,pin_code,country_code
from .coverage import covers,location_key,DEMO_REGIONS
from .addresses import validate_address
from .catalogue import SERVICES,CLEANING_OFFERINGS,EXTENDED_OFFERINGS,unavailable_message,provider_services,provider_amount,quote_scope
from .service_details import validate_details


class Rejected(ValueError):
    pass


def ident(prefix):
    return f"{prefix}_{uuid4().hex[:16]}"


def encode(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"))


SCHEMA = """
PRAGMA journal_mode=WAL;
CREATE TABLE IF NOT EXISTS providers(id TEXT PRIMARY KEY, payload TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS quotes(id TEXT PRIMARY KEY, provider TEXT NOT NULL,
 slot TEXT NOT NULL, owner TEXT NOT NULL, version INTEGER NOT NULL,
 amount INTEGER NOT NULL CHECK(amount>0), expires REAL NOT NULL,
 payload TEXT NOT NULL, digest TEXT NOT NULL, previous TEXT);
CREATE TABLE IF NOT EXISTS bookings(id TEXT PRIMARY KEY, owner TEXT NOT NULL,
 quote TEXT REFERENCES quotes(id), provider TEXT, slot TEXT,
 state TEXT NOT NULL CHECK(state IN ('requested','held','confirmed','completed','cancelled')),
 hold_until REAL NOT NULL DEFAULT 0, approved INTEGER NOT NULL DEFAULT 0,
 payment_state TEXT NOT NULL DEFAULT 'none', recovery_of TEXT REFERENCES bookings(id));
CREATE UNIQUE INDEX IF NOT EXISTS exclusive_slot ON bookings(provider,slot)
 WHERE state IN ('held','confirmed','completed');
CREATE TABLE IF NOT EXISTS payments(id TEXT PRIMARY KEY,
 booking TEXT NOT NULL UNIQUE REFERENCES bookings(id), idem TEXT NOT NULL UNIQUE,
 amount INTEGER NOT NULL, state TEXT NOT NULL, external TEXT UNIQUE);
CREATE TABLE IF NOT EXISTS verified_transfers(
 tx_hash TEXT PRIMARY KEY, booking TEXT NOT NULL REFERENCES bookings(id),
 direction TEXT NOT NULL CHECK(direction IN ('incoming','refund')),
 sender TEXT NOT NULL, recipient TEXT NOT NULL, amount TEXT NOT NULL, denom TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS events(seq INTEGER PRIMARY KEY AUTOINCREMENT,
 at REAL NOT NULL, entity TEXT NOT NULL, kind TEXT NOT NULL, actor TEXT NOT NULL,
 payload TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS sessions(id TEXT PRIMARY KEY, payload TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS booking_notices(
 event INTEGER PRIMARY KEY REFERENCES events(seq),booking TEXT NOT NULL,
 attempts INTEGER NOT NULL DEFAULT 0,next_attempt REAL NOT NULL DEFAULT 0,sent INTEGER NOT NULL DEFAULT 0);
CREATE TABLE IF NOT EXISTS gateway_operations(
 booking TEXT NOT NULL REFERENCES bookings(id),operation TEXT NOT NULL,
 external TEXT,PRIMARY KEY(booking,operation));
CREATE TRIGGER IF NOT EXISTS no_quote_update BEFORE UPDATE ON quotes
 BEGIN SELECT RAISE(ABORT,'immutable quote'); END;
CREATE TRIGGER IF NOT EXISTS no_quote_delete BEFORE DELETE ON quotes
 BEGIN SELECT RAISE(ABORT,'immutable quote'); END;
CREATE TRIGGER IF NOT EXISTS no_event_update BEFORE UPDATE ON events
 BEGIN SELECT RAISE(ABORT,'append-only audit'); END;
CREATE TRIGGER IF NOT EXISTS no_event_delete BEFORE DELETE ON events
 BEGIN SELECT RAISE(ABORT,'append-only audit'); END;
"""


class ClosingConnection(sqlite3.Connection):
    def __exit__(self, *args):
        try:
            return super().__exit__(*args)
        finally:
            self.close()


class Store:
    def __init__(self, path="data/servicesetu.db", clock=time.time):
        self.path, self.clock = str(path), clock
        Path(self.path).parent.mkdir(parents=True, exist_ok=True)
        with self.connect() as db:
            db.executescript(SCHEMA)
            if 'mode' not in {r['name'] for r in db.execute('PRAGMA table_info(payments)')}:
                db.execute("ALTER TABLE payments ADD COLUMN mode TEXT NOT NULL DEFAULT 'mock'")
                db.execute("UPDATE payments SET mode='stripe_test' WHERE external IS NOT NULL")
            payment_columns={r['name'] for r in db.execute('PRAGMA table_info(payments)')}
            for name,definition in (('invoice','TEXT'),('payer_wallet','TEXT'),('refund_external','TEXT')):
                if name not in payment_columns:db.execute(f'ALTER TABLE payments ADD COLUMN {name} {definition}')
            db.execute('CREATE UNIQUE INDEX IF NOT EXISTS unique_payment_refund ON payments(refund_external) WHERE refund_external IS NOT NULL')
            sql=db.execute("SELECT sql FROM sqlite_master WHERE name='bookings'").fetchone()[0]
            if "'requested'" not in sql:
                self.migrate_requests(db)

    def migrate_requests(self,db):
        """Preserve existing bookings/payment references when adding intake state."""
        db.execute("PRAGMA foreign_keys=OFF")
        try:
            db.execute("BEGIN IMMEDIATE")
            definition=SCHEMA.split("CREATE TABLE IF NOT EXISTS bookings",1)[1].split(";",1)[0]
            db.execute("CREATE TABLE bookings_next"+definition)
            db.execute("INSERT INTO bookings_next SELECT * FROM bookings")
            db.execute("DROP TABLE bookings")
            db.execute("ALTER TABLE bookings_next RENAME TO bookings")
            db.execute("CREATE UNIQUE INDEX exclusive_slot ON bookings(provider,slot) WHERE state IN ('held','confirmed','completed')")
            if db.execute("PRAGMA foreign_key_check").fetchall():
                raise RuntimeError("Booking migration failed referential-integrity check")
            db.commit()
        except Exception:
            db.rollback()
            raise
        finally:
            db.execute("PRAGMA foreign_keys=ON")

    def connect(self):
        db = sqlite3.connect(self.path, timeout=15, isolation_level=None, factory=ClosingConnection)
        db.row_factory = sqlite3.Row
        db.execute("PRAGMA foreign_keys=ON")
        return db

    @contextmanager
    def tx(self):
        db = self.connect()
        try:
            db.execute("BEGIN IMMEDIATE")
            yield db
            db.commit()
        except Exception:
            db.rollback()
            raise
        finally:
            db.close()

    def event(self, db, entity, kind, actor="system", **payload):
        row=db.execute("INSERT INTO events(at,entity,kind,actor,payload) VALUES(?,?,?,?,?)",
                   (self.clock(), entity, kind, actor, encode(payload)))
        if kind in ('booking_confirmed','payment_compensated','provider_cancelled','stripe_test_refunded','razorpay_test_refunded'):
            db.execute('INSERT INTO booking_notices(event,booking) VALUES(?,?)',(row.lastrowid,entity))

    def denied(self, entity, reason, actor):
        with self.tx() as db:
            self.event(db, entity, "action_rejected", actor, reason=reason)

    def providers(self):
        with self.connect() as db:
            return [json.loads(r[0]) for r in db.execute("SELECT payload FROM providers ORDER BY id")]

    def provider(self, provider_id):
        for p in self.providers():
            if p["id"] == provider_id:
                return p
        raise Rejected("Unknown provider")

    def seed(self, days=1, expanded=False, full_catalogue=False, extended_catalogue=False, nationwide_demo=False):
        """Six default or twelve expanded fictional providers; mock registry."""
        if not isinstance(days,int) or isinstance(days,bool) or not 1<=days<=14:
            raise Rejected("Demo days must be a whole number from 1 to 14")
        extended_catalogue=extended_catalogue or nationwide_demo
        full_catalogue=full_catalogue or extended_catalogue
        now = datetime.fromtimestamp(self.clock(), timezone.utc)
        dates=[(now.astimezone(ZoneInfo("Asia/Kolkata"))+timedelta(days=offset)).date().isoformat()
               for offset in range(1,days+1)]
        names = ["CoolCare AC", "Breeze AC", "Lapsed AC", "FlowFix Plumbing", "TapCare Plumbing", "Renewal Plumbing"]
        if expanded or full_catalogue:
            names += ["FreshNest Cleaning", "SparkleSpace Cleaning", "Lapsed Cleaning",
                      "CircuitCheck Electrical", "BrightWire Electrical", "Lapsed Electrical"]
        if full_catalogue:
            names += ["SpinCheck Appliances","DrumCare Appliances","AssemblyWorks","BuildBuddy Assembly"]
        for i, name in enumerate(names):
            service = ("ac","plumbing","cleaning","electrical")[i//3] if i<12 else "washing_machine" if i<14 else "furniture"
            expiry = (now + timedelta(days=-1 if i in (2,8,11) else 1 if i == 5 else 90)).date().isoformat()
            p = {"id": f"p{i+1}", "name": name, "service": service, "city": "bengaluru",
                 "area": "indiranagar", "amount": [69900, 74900, 59900, 49900, 54900, 45900,79900,89900,59900,39900,49900,29900,44900,54900,34900,44900][i],
                 "slots": [f"{day}T{hour}:00:00+05:30" for day in dates for hour in ("10","14")],
                 "credential": {"type": "demo_skill_certificate", "jurisdiction": "IN-demo",
                  "issuer": "Mock Service Registry", "status": "provider_supplied" if i in (1,4,7,10,13,15) else "verified",
                  "source": "seeded provider upload" if i in (1,4,7,10,13,15) else "mock-registry://servicesetu",
                  "checked_at": now.isoformat(), "expires": expiry, "method": "mock_lookup",
                  "verifier": "demo-verification-agent", "policy_version": "IN-demo-v1"},
                 "available": True,"record_kind":"demo"}
            if full_catalogue and i in (6,7,8):
                p["offerings"]=dict(CLEANING_OFFERINGS[p["id"]])
            if extended_catalogue and p["id"] in EXTENDED_OFFERINGS:
                p.setdefault("offerings",{}).update(EXTENDED_OFFERINGS[p["id"]])
            if i in (14,15): p["assembly_surcharge"]=0 if i==14 else 10000
            with self.tx() as db:
                db.execute("INSERT OR IGNORE INTO providers VALUES(?,?)", (p["id"], encode(p)))
        if nationwide_demo:self.enable_demo_coverage()

    def extend_demo_offerings(self,extended_catalogue=False):
        """Explicit demo-copy upgrade; retain prices, capacity and existing history."""
        with self.tx() as db:
            upgrades={pid:dict(offerings) for pid,offerings in CLEANING_OFFERINGS.items()}
            if extended_catalogue:
                for pid,offerings in EXTENDED_OFFERINGS.items():upgrades.setdefault(pid,{}).update(offerings)
            for pid,offerings in upgrades.items():
                row=db.execute("SELECT payload FROM providers WHERE id=?",(pid,)).fetchone()
                if not row: continue
                provider=json.loads(row[0])
                expected="cleaning" if pid in CLEANING_OFFERINGS else "washing_machine"
                if provider["service"]!=expected: continue
                provider.setdefault("offerings",{})
                for service,amount in offerings.items():provider["offerings"].setdefault(service,amount)
                db.execute("UPDATE providers SET payload=? WHERE id=?",(encode(provider),pid))

    def enable_demo_coverage(self):
        """Opt-in fictional branches in a demo copy; existing declarations win."""
        with self.tx() as db:
            for row in db.execute('SELECT id,payload FROM providers').fetchall():
                provider=json.loads(row['payload'])
                if 'coverage' in provider or provider.get('credential',{}).get('verifier')!='demo-verification-agent':continue
                if canonical(provider.get('city'),'city')!='bengaluru' or canonical(provider.get('area'),'area')!='indiranagar':continue
                provider['coverage']=DEMO_REGIONS
                db.execute('UPDATE providers SET payload=? WHERE id=?',(encode(provider),row['id']))

    def trust(self, p, slot):
        # End-of-day expiry must cover the appointment's local calendar day.
        c = p["credential"]
        day = datetime.fromisoformat(slot).date().isoformat()
        today = datetime.fromtimestamp(self.clock(), ZoneInfo("Asia/Kolkata")).date().isoformat()
        status = "expired" if c["expires"] < max(day, today) else c["status"]
        return dict(c, status=status, eligible=status in ("verified", "provider_supplied", "manually_reviewed"))

    def slot_free(self,provider,slot):
        with self.connect() as db:
            busy=db.execute("SELECT 1 FROM bookings WHERE provider=? AND slot=? AND (state IN ('confirmed','completed') OR (state='held' AND hold_until>?)) LIMIT 1",(provider,slot,self.clock())).fetchone()
        return busy is None

    def normalize_job(self,job):
        if not isinstance(job,dict): raise Rejected("A structured service request is required")
        if not isinstance(job.get("service"),str) or job["service"] not in SERVICES or not SERVICES[job["service"]]["bookable"]:
            raise Rejected(unavailable_message(job.get("service")))
        package=SERVICES[job["service"]].get("package")
        if package and job.get("package")!=package:
            raise Rejected("Confirm the service package: "+package)
        try: details=validate_details(job["service"],job.get("details",{}))
        except ValueError as exc: raise Rejected(str(exc)) from None
        city=job.get("city")
        area=job.get("area","")
        if not isinstance(city,str) or not isinstance(area,str):
            raise Rejected("City and area must be text")
        city,area=canonical(city,"city"),canonical(area,"area")
        if not city or not area:raise Rejected("Provide a city and locality in India")
        if country_code(job.get("country"))!='IN':raise Rejected("Provide a service location in India")
        pin=pin_code(job['pincode']) if job.get('pincode') is not None else None
        if job.get('pincode') is not None and pin is None:raise Rejected("Provide a six-digit Indian PIN code")
        try:
            dt=datetime.fromisoformat(job["slot"])
            if dt.tzinfo is None or dt.timestamp()<=self.clock(): raise ValueError
            budget=job["budget"]
            if not isinstance(budget,int) or isinstance(budget,bool) or budget<=0: raise ValueError
        except (ValueError,TypeError,KeyError,OverflowError):
            raise Rejected("Provide a future timezone-qualified slot and a positive whole-paise budget") from None
        return {"service":job["service"],**({"package":package} if package else {}),**({"details":details} if details else {}),**({'pincode':pin} if pin else {}),**({'country':'IN'} if job.get('country') else {}),"city":city.lower(),"area":area.lower(),
                "slot":dt.astimezone(ZoneInfo("Asia/Kolkata")).isoformat(timespec="seconds"),"budget":budget}

    def match(self, job):
        job=self.normalize_job(job)
        slot,budget=job["slot"],job["budget"]
        selected, excluded = [], []
        for p in self.providers():
            if job["service"] not in provider_services(p):
                continue
            amount=provider_amount(p,job["service"],job.get("details",{}))
            trust = self.trust(p, slot)
            reason = None
            if not covers(p,job):reason="Outside this provider's declared service coverage"
            elif not trust["eligible"]: reason = "Credential expired before the service date"
            elif not p["available"] or slot not in p["slots"]: reason = "Provider has no matching slot"
            elif not self.slot_free(p["id"],slot): reason = "Slot already reserved"
            elif amount > budget: reason = "Above your budget"
            if reason: excluded.append({"provider": p["id"], "name": p["name"], "reason": reason})
            else: selected.append(dict(p, trust=trust,amount=amount))
        selected.sort(key=lambda p: (p["trust"]["status"] != "verified", p["amount"]))
        return selected, excluded

    def available_slots(self, job, limit=4):
        """Read-only suggestions; never change a request or reserve capacity."""
        job = self.normalize_job(job)
        slots = {slot for p in self.providers() if job["service"] in provider_services(p) and covers(p,job) for slot in p["slots"]}
        options = []
        for slot in sorted(slots, key=lambda value: datetime.fromisoformat(value).timestamp()):
            if slot == job["slot"] or datetime.fromisoformat(slot).timestamp() <= self.clock():
                continue
            choices, _ = self.match(dict(job, slot=slot))
            if choices:
                options.append({"slot": slot, "from_amount": min(p["amount"] for p in choices),
                                "provider_count": len(choices)})
            if len(options) >= limit:
                break
        return options

    def quote(self, owner, provider, slot, previous=None, job=None, address_required=False):
        p = self.provider(provider)
        if job is not None:
            job=self.normalize_job(job)
            if job["slot"]!=slot or job["service"] not in provider_services(p) or not covers(p,job):
                raise Rejected("Provider quote does not match the service request")
        service=job["service"] if job else p["service"]
        if job is None and service in ("washing_machine","furniture"):
            raise Rejected("A complete service request is required for this package")
        details=job.get("details",{}) if job else {}
        amount=provider_amount(p,service,details)
        if job and amount>job["budget"]: raise Rejected("Provider quote exceeds your budget")
        if not self.trust(p, slot)["eligible"] or slot not in p["slots"] or not p["available"]:
            raise Rejected("Provider ineligible or slot unavailable")
        if not self.slot_free(provider,slot):
            # A provider may issue a revision for this customer's existing hold.
            # The original consent remains bound to the original quote.
            with self.connect() as db:
                own_hold=db.execute("SELECT 1 FROM bookings WHERE owner=? AND provider=? AND slot=? AND quote=? AND state='held'",(owner,provider,slot,previous)).fetchone() if previous else None
            if not own_hold: raise Rejected("Slot already reserved")
        if datetime.fromisoformat(slot).timestamp() <= self.clock():
            raise Rejected("Service date is in the past")
        qid = ident("q")
        with self.tx() as db:
            version = 1
            if previous:
                old = db.execute("SELECT * FROM quotes WHERE id=? AND owner=?", (previous, owner)).fetchone()
                if not old or old["provider"] != provider: raise Rejected("Invalid prior quote")
                version = old["version"] + 1
            payload = {"id": qid, "provider": provider, "name": p["name"], "slot": slot,
                "owner": owner, "version": version, "amount": amount, "currency": "INR",
                "service":service,**({"details":details} if details else {}),
                **({'address_required':True} if address_required else {}),
                "location":{field:job[field] for field in ('city','area','pincode','country') if field in job} if job else {'city':p['city'],'area':p['area']},
                "kind": "fixed", "record_kind":p.get('record_kind','demo'),
                "scope": p.get('pilot_scope',quote_scope(service,details)),
                "exclusions": p.get('pilot_exclusions',SERVICES[service]["exclusions"]),
                "cancellation": "Full test-payment reversal before work starts; no real money collected",
                "trust": self.trust(p, slot), "expires": self.clock()+300,
                "availability": {"source": f"provider-agent:{provider}", "observed_at": self.clock(),
                    "expires": self.clock()+300, "confidence": "operator-entered pilot availability" if p.get('record_kind')=='pilot' else "provider-confirmed demo", "hold_capable": True}}
            digest = hashlib.sha256(encode(payload).encode()).hexdigest()
            db.execute("INSERT INTO quotes VALUES(?,?,?,?,?,?,?,?,?,?)", (qid, provider, slot, owner, version,
                       amount, payload["expires"], encode(payload), digest, previous))
            self.event(db, qid, "quote_created", "provider:"+provider, digest=digest, quote=payload, previous=previous)
        return payload

    def get_quote(self, qid, owner):
        with self.connect() as db:
            row = db.execute("SELECT payload FROM quotes WHERE id=? AND owner=?", (qid, owner)).fetchone()
        if not row: raise Rejected("Quote not found in this conversation")
        return json.loads(row[0])

    def expire(self, db):
        rows = db.execute("SELECT * FROM bookings WHERE state='held' AND hold_until<=?", (self.clock(),)).fetchall()
        for b in rows:
            # A pending Stripe checkout can still complete: preserve its reference for reconciliation.
            db.execute("UPDATE bookings SET state='cancelled' WHERE id=?", (b["id"],))
            self.event(db, b["id"], "hold_expired", quote=b["quote"])

    def request(self,owner,job):
        # Validate before persisting an intake. No provider reservation or consent.
        job=self.normalize_job(job)
        bid=ident("b")
        with self.tx() as db:
            db.execute("INSERT INTO bookings(id,owner,slot,state) VALUES(?,?,?,'requested')",(bid,owner,job["slot"]))
            self.event(db,bid,"booking_requested",owner,job=job)
        return self.booking(bid,owner)

    def validate_recovery(self,owner,bid,slot,service,details,location,budget=None,amount=None):
        old=self.booking(bid,owner)
        if old['state']!='cancelled':raise Rejected('Recovery starts only after cancellation')
        quote=self.get_quote(old['quote'],owner)
        provider=self.provider(old['provider'])
        original_location=quote.get('location',{'city':provider['city'],'area':provider['area']})
        if slot!=quote['slot'] or service!=quote.get('service',provider['service']) or details!=quote.get('details',{}) or location_key(location)!=location_key(original_location):
            raise Rejected('A replacement must keep the original location, appointment and service scope; start a new request to change them')
        with self.connect() as db:
            row=db.execute("SELECT payload FROM events WHERE entity=? AND kind='booking_requested' ORDER BY seq LIMIT 1",(bid,)).fetchone()
        maximum=json.loads(row[0]).get('job',{}).get('budget') if row else None
        if maximum is not None and any(value is not None and value>maximum for value in (budget,amount)):
            raise Rejected('A replacement must stay within the original requested budget')

    def hold(self, owner, qid, recovery_of=None, request_id=None, address=None, defer_address=False):
        bid = request_id or ident("b")
        with self.tx() as db:
            self.expire(db)
            q = db.execute("SELECT * FROM quotes WHERE id=? AND owner=?", (qid, owner)).fetchone()
            if not q: raise Rejected("Quote not found in this conversation")
            if q["expires"] <= self.clock(): raise Rejected("Quote and availability expired; request fresh alternatives")
            p = self.provider(q["provider"])
            location=json.loads(q['payload']).get('location',{'city':p['city'],'area':p['area']})
            saved_address=None
            if type(defer_address) is not bool or (defer_address and address is not None):raise Rejected('Choose an address or skip it for now')
            if address is not None or (json.loads(q['payload']).get('address_required') and not defer_address):
                try:saved_address=validate_address(address,location)
                except ValueError as exc:raise Rejected(str(exc)) from None
                if recovery_of:
                    original=self.booking(recovery_of,owner).get('service_address')
                    if original and saved_address!=original:raise Rejected('A replacement must keep the original service address; start a new request to change it')
            if not covers(p,location):raise Rejected("Provider no longer covers this location; request a fresh quote")
            quoted_service=json.loads(q["payload"]).get("service",p["service"])
            if quoted_service not in provider_services(p): raise Rejected("Provider no longer offers this service; request a fresh quote")
            if not p["available"] or q["slot"] not in p["slots"] or not self.trust(p,q["slot"])["eligible"]:
                raise Rejected("Final slot or credential revalidation failed")
            if recovery_of:
                old = db.execute("SELECT * FROM bookings WHERE id=? AND owner=? AND state='cancelled'", (recovery_of,owner)).fetchone()
                if not old: raise Rejected("Recovery must reference your cancelled booking")
                original=self.booking(recovery_of,owner).get('service_address')
                if original and saved_address!=original:raise Rejected('A replacement must keep the original service address')
                payload=json.loads(q['payload'])
                self.validate_recovery(owner,recovery_of,q['slot'],quoted_service,payload.get('details',{}),location,amount=q['amount'])
            existing = db.execute("SELECT id FROM bookings WHERE owner=? AND quote=? AND state='held'", (owner,qid)).fetchone()
            if existing:
                held=self.booking(existing['id'],owner)
                if saved_address and held.get('service_address')!=saved_address:
                    raise Rejected("Use 'change address' to release this hold and review a different address")
                return held
            if request_id:
                intent=db.execute("SELECT * FROM bookings WHERE id=? AND owner=? AND state='requested'",(request_id,owner)).fetchone()
                if not intent: raise Rejected("Booking request is not open in this conversation")
            else:
                db.execute("INSERT INTO bookings(id,owner,state) VALUES(?,?,'requested')",(bid,owner))
                self.event(db,bid,"booking_requested",owner,quote=qid)
            try:
                db.execute("UPDATE bookings SET quote=?,provider=?,slot=?,state='held',hold_until=?,recovery_of=? WHERE id=?",
                    (qid,q["provider"],q["slot"],min(q["expires"],self.clock()+120),recovery_of,bid))
            except sqlite3.IntegrityError:
                raise Rejected("Slot already reserved; choose a fresh alternative") from None
            self.event(db, bid, "slot_held", owner, quote=qid, hold_until=min(q["expires"],self.clock()+120), recovery_of=recovery_of)
            if saved_address:self.event(db,bid,'service_address_recorded',owner,address=saved_address)
            elif defer_address:self.event(db,bid,'service_address_deferred',owner)
        return self.booking(bid,owner)

    def provide_address(self,owner,bid,address):
        with self.tx() as db:
            b=db.execute('SELECT * FROM bookings WHERE id=? AND owner=?',(bid,owner)).fetchone()
            if not b or b['state'] not in ('held','confirmed'):raise Rejected('Add an address only to your active booking')
            if b['state']=='held' and b['approved']:raise Rejected('Finish the pending payment before adding your address')
            q=self.get_quote(b['quote'],owner)
            try:value=validate_address(address,q['location'])
            except ValueError as exc:raise Rejected(str(exc)) from None
            original=self.booking(bid,owner).get('service_address')
            if original:
                if original==value:return self.booking(bid,owner)
                raise Rejected('An address is already saved; start a new request to change a confirmed service location')
            if b['recovery_of']:
                prior=self.booking(b['recovery_of'],owner).get('service_address')
                if prior and value!=prior:raise Rejected('A replacement keeps the original service address')
            self.event(db,bid,'service_address_recorded',owner,address=value)
        return self.booking(bid,owner)

    def address_deferred(self,bid):
        with self.connect() as db:return bool(db.execute("SELECT 1 FROM events WHERE entity=? AND kind='service_address_deferred'",(bid,)).fetchone())

    def booking(self, bid, owner):
        with self.connect() as db:
            row = db.execute("SELECT * FROM bookings WHERE id=? AND owner=?", (bid,owner)).fetchone()
        if not row: raise Rejected("Booking not found in this conversation")
        result=dict(row)
        with self.connect() as db:
            payment=db.execute('SELECT mode FROM payments WHERE booking=?',(bid,)).fetchone()
            address=db.execute("SELECT payload FROM events WHERE entity=? AND kind='service_address_recorded' ORDER BY seq DESC LIMIT 1",(bid,)).fetchone()
        result['payment_mode']=payment['mode'] if payment else None
        if address:result['service_address']=json.loads(address[0])['address']
        return result

    def approve(self, owner, bid, qid, payment_terms=None):
        with self.tx() as db:
            b = db.execute("SELECT * FROM bookings WHERE id=? AND owner=?", (bid,owner)).fetchone()
            if not b or b["quote"] != qid: raise Rejected("Approval does not match the held quote")
            if self.get_quote(qid,owner).get('address_required') and not self.booking(bid,owner).get('service_address') and not self.address_deferred(bid):
                raise Rejected('A service address is required before approval')
            if b["state"] != "held" or b["hold_until"] <= self.clock(): raise Rejected("Hold expired; refresh before approving")
            if not b['approved']:
                db.execute("UPDATE bookings SET approved=1 WHERE id=?", (bid,))
                payload={'quote':qid}
                if payment_terms is not None:payload['payment_terms']=payment_terms
                self.event(db,bid,"customer_approved",owner,**payload)

    def begin_payment(self, owner, bid, idem, mode='mock'):
        with self.tx() as db:
            b = db.execute("SELECT * FROM bookings WHERE id=? AND owner=?", (bid,owner)).fetchone()
            if not b or not b["approved"]: raise Rejected("Explicit customer approval required before payment")
            if self.get_quote(b['quote'],owner).get('address_required') and not self.booking(bid,owner).get('service_address') and not self.address_deferred(bid):
                raise Rejected('A service address is required before payment')
            old = db.execute("SELECT * FROM payments WHERE idem=? OR booking=?", (idem,bid)).fetchone()
            if old:
                if old["booking"] != bid or old["idem"] != idem: raise Rejected("Idempotency key conflict")
                if old['mode']!=mode:raise Rejected('Payment mode changed; reconcile the original test payment first')
                if old['state']=='pending' and (b['state']!='held' or b['hold_until']<=self.clock()):
                    raise Rejected('Hold expired or cancelled; payment reconciliation is pending')
                return dict(old)
            if b["state"] != "held" or b["hold_until"] <= self.clock(): raise Rejected("Hold expired before payment")
            q = db.execute("SELECT * FROM quotes WHERE id=?",(b["quote"],)).fetchone()
            provider=self.provider(b["provider"])
            if provider.get('record_kind')=='pilot' and not db.execute("SELECT 1 FROM events WHERE entity=? AND kind='pilot_booking_accepted' AND json_extract(payload,'$.quote')=?",(bid,b['quote'])).fetchone():
                raise Rejected('Awaiting operator confirmation with the provider. Retry this approval after acceptance while the hold is active, or request a fresh quote')
            location=json.loads(q['payload']).get('location',{'city':provider['city'],'area':provider['area']})
            if not covers(provider,location):raise Rejected("Provider no longer covers this location; no payment started")
            if json.loads(q["payload"]).get("service",provider["service"]) not in provider_services(provider):
                raise Rejected("Provider no longer offers this service; no payment started")
            if q["expires"] <= self.clock() or not self.trust(self.provider(b["provider"]),b["slot"])["eligible"]:
                raise Rejected("Quote or credential revalidation failed")
            pid = ident("pay")
            if not provider['available'] or b['slot'] not in provider['slots']:raise Rejected('Provider availability changed; no payment started')
            db.execute("INSERT INTO payments(id,booking,idem,amount,state,external,mode) VALUES(?,?,?,?,?,?,?)",(pid,bid,idem,q["amount"],"pending",None,mode))
            db.execute("UPDATE bookings SET payment_state='pending' WHERE id=?",(bid,))
            self.event(db,bid,"payment_started",owner,payment=pid,amount=q["amount"],quote=b["quote"])
        return {"id":pid,"booking":bid,"idem":idem,"amount":q["amount"],"state":"pending","external":None,'mode':mode}

    def begin_fet_payment(self,owner,bid,idem,*,recipient,deadline_seconds):
        """Create/retrieve one quote-bound Dorado invoice; never refresh it on retry."""
        payment=self.begin_payment(owner,bid,idem,mode='fet_testnet')
        with self.tx() as db:
            b=db.execute('SELECT * FROM bookings WHERE id=? AND owner=?',(bid,owner)).fetchone()
            p=db.execute('SELECT * FROM payments WHERE booking=?',(bid,)).fetchone()
            if not b or not p or p['mode']!='fet_testnet' or not b['approved']:
                raise Rejected('Approved Dorado payment intent required')
            if p['invoice']:
                invoice=json.loads(p['invoice'])
                if invoice['recipient']!=recipient:raise Rejected('Stored FET invoice recipient does not match the configured wallet')
                return dict(payment,invoice=invoice)
            if b['state']!='held' or b['hold_until']<=self.clock():
                raise Rejected('Hold expired before FET invoice creation; request a fresh quote')
            q=db.execute('SELECT * FROM quotes WHERE id=?',(b['quote'],)).fetchone()
            if not q or q['expires']<=self.clock():raise Rejected('Quote expired before FET invoice creation; request a fresh quote')
            approval=db.execute("SELECT payload FROM events WHERE entity=? AND kind='customer_approved' ORDER BY seq DESC LIMIT 1",(bid,)).fetchone()
            approval_payload=json.loads(approval['payload']) if approval else {}
            terms=approval_payload.get('payment_terms') or {}
            if terms.get('quote_id')!=b['quote'] or terms.get('network')!='dorado-1' or terms.get('denom')!='atestfet':
                raise Rejected('Customer approval did not include this quote’s Dorado FET amount')
            token_amount=terms.get('token_amount')
            atomic_amount=terms.get('atomic_amount')
            from .fet_payments import fet_amount
            exact_amount,exact_atomic=fet_amount(token_amount)
            if exact_amount!=token_amount or str(exact_atomic)!=str(atomic_amount):
                raise Rejected('Approved FET payment amount is invalid')
            window=min(int(deadline_seconds),max(1,int(b['hold_until']-self.clock())))
            invoice={
                'booking_id':bid,'quote_id':b['quote'],'customer':owner.rsplit(':',1)[0],
                'session':owner.rsplit(':',1)[1] if ':' in owner else '',
                'network':'dorado-1','denom':'atestfet','recipient':recipient,
                'token_amount':token_amount,'atomic_amount':str(atomic_amount),
                'deadline_at':min(b['hold_until'],self.clock()+window),'deadline_seconds':window,
            }
            db.execute('UPDATE payments SET invoice=? WHERE booking=? AND invoice IS NULL',(encode(invoice),bid))
            self.event(db,bid,'fet_testnet_invoice_created',owner,quote=b['quote'],network='dorado-1',recipient=recipient,
                       token_amount=token_amount,denom='atestfet',deadline=invoice['deadline_at'])
        return dict(payment,invoice=invoice)

    def attach_checkout(self, owner, bid, checkout, mode='stripe_test'):
        self.booking(bid,owner)
        with self.tx() as db:
            old=db.execute('SELECT external FROM payments WHERE booking=?',(bid,)).fetchone()
            if not old:raise Rejected('Payment intent missing')
            if old['external'] and old['external']!=checkout:raise Rejected('Checkout already bound to another session')
            if not old['external']:
                db.execute("UPDATE payments SET external=? WHERE booking=? AND state='pending'", (checkout,bid))
                self.event(db,bid,mode+"_checkout_created",owner,checkout=checkout)

    def settle(self, owner, bid, *, success=True, provider_confirm=True, external=None, payer_wallet=None,
               transfer_sender=None,transfer_recipient=None,transfer_amount=None,transfer_denom=None):
        """Called by mock adapter or only after server-side Stripe verification."""
        with self.tx() as db:
            b = db.execute("SELECT * FROM bookings WHERE id=? AND owner=?",(bid,owner)).fetchone()
            pay = db.execute("SELECT * FROM payments WHERE booking=?",(bid,)).fetchone()
            if not b or not pay or not b["approved"]: raise Rejected("Approved payment intent required")
            if pay["state"] in ("paid","voided","declined","refund_required","refunded"):
                return dict(b)
            if external and pay['mode']=='fet_testnet':
                prior=db.execute('SELECT booking,direction FROM verified_transfers WHERE tx_hash=?',(external,)).fetchone()
                if prior and (prior['booking']!=bid or prior['direction']!='incoming'):
                    raise Rejected('This on-chain transaction was already used')
                db.execute('INSERT OR IGNORE INTO verified_transfers VALUES(?,?,?,?,?,?,?)',
                           (external,bid,'incoming',transfer_sender or '',transfer_recipient or '',str(transfer_amount or ''),transfer_denom or ''))
                db.execute('UPDATE payments SET payer_wallet=? WHERE booking=?',(payer_wallet,bid))
            q = db.execute("SELECT * FROM quotes WHERE id=?",(b["quote"],)).fetchone()
            p = self.provider(b["provider"])
            fresh = b["state"] == "held" and b["hold_until"] > self.clock() and q["expires"] > self.clock()
            if pay['mode']=='fet_testnet':
                invoice=json.loads(pay['invoice']) if pay['invoice'] else {}
                fresh=fresh and invoice.get('deadline_at',0)>self.clock()
            fresh = fresh and p["available"] and b["slot"] in p["slots"] and self.trust(p,b["slot"])["eligible"]
            payload=json.loads(q['payload'])
            fresh=fresh and covers(p,payload.get('location',p)) and payload.get('service',p['service']) in provider_services(p)
            if success and provider_confirm and fresh:
                db.execute("UPDATE payments SET state='paid',external=COALESCE(?,external) WHERE booking=?",(external,bid))
                db.execute("UPDATE bookings SET state='confirmed',payment_state='paid' WHERE id=?",(bid,))
                extra={'payment_transaction':external,'payment_network':'dorado-1'} if external and pay['mode']=='fet_testnet' else {}
                self.event(db,bid,"booking_confirmed",owner,quote=b["quote"],payment=pay["id"],amount=pay["amount"],**extra)
            else:
                state = "refund_required" if external and success else "voided" if success else "declined"
                db.execute("UPDATE payments SET state=?,external=COALESCE(?,external) WHERE booking=?",(state,external,bid))
                db.execute("UPDATE bookings SET state='cancelled',payment_state=? WHERE id=?",(state,bid))
                extra={'payment_transaction':external,'payment_network':'dorado-1'} if external and pay['mode']=='fet_testnet' else {}
                self.event(db,bid,"payment_compensated",payment_state=state,reason="payment failed" if not success else "provider declined or hold expired",**extra)
                self.event(db,bid,"slot_released")
        return self.booking(bid,owner)

    def cancel(self, owner, bid, actor="customer", stripe=False):
        with self.tx() as db:
            b = db.execute("SELECT * FROM bookings WHERE id=? AND owner=?",(bid,owner)).fetchone()
            if not b: raise Rejected("Booking not found")
            if actor not in ('customer',owner,'provider:'+str(b['provider'])):raise Rejected('Cancellation actor is not assigned to this booking')
            if b["state"] == "cancelled": return dict(b)
            if b["state"] == "completed": raise Rejected("Completed work requires human dispute review")
            payment=db.execute('SELECT mode FROM payments WHERE booking=?',(bid,)).fetchone()
            stripe=stripe or bool(payment and payment['mode'] in ('stripe_test','razorpay_test','fet_testnet'))
            state = ("refund_required" if stripe else "refunded") if b["payment_state"]=="paid" else b["payment_state"]
            db.execute("UPDATE bookings SET state='cancelled',payment_state=? WHERE id=?",(state,bid))
            db.execute("UPDATE payments SET state=? WHERE booking=?",(state,bid))
            reference=db.execute('SELECT external,mode FROM payments WHERE booking=?',(bid,)).fetchone()
            extra={'payment_transaction':reference['external'],'payment_network':'dorado-1'} if reference and reference['mode']=='fet_testnet' and reference['external'] else {}
            self.event(db,bid,"provider_cancelled" if actor.startswith("provider:") else "customer_cancelled",actor,payment_state=state,**extra)
            self.event(db,bid,"slot_released",actor)
        return self.booking(bid,owner)

    def refund_done(self, owner, bid, refund_id, mode='stripe_test', transfer=None):
        self.booking(bid,owner)
        with self.tx() as db:
            if mode=='fet_testnet':
                if not transfer:raise Rejected('A verified Dorado refund transfer is required')
                used=db.execute('SELECT booking,direction FROM verified_transfers WHERE tx_hash=?',(refund_id,)).fetchone()
                if used and (used['booking']!=bid or used['direction']!='refund'):
                    raise Rejected('This on-chain transaction was already used')
                db.execute('INSERT OR IGNORE INTO verified_transfers VALUES(?,?,?,?,?,?,?)',
                           (refund_id,bid,'refund',transfer['sender'],transfer['recipient'],str(transfer['amount']),transfer['denom']))
                changed=db.execute("UPDATE payments SET state='refunded',refund_external=? WHERE booking=? AND state='refund_required'",(refund_id,bid)).rowcount
                db.execute("UPDATE bookings SET payment_state='refunded' WHERE id=? AND payment_state='refund_required'",(bid,))
                if changed:self.event(db,bid,'fet_testnet_refunded',owner,refund=refund_id,network='dorado-1')
                return
            changed=db.execute("UPDATE payments SET state='refunded' WHERE booking=? AND state='refund_required'",(bid,)).rowcount
            db.execute("UPDATE bookings SET payment_state='refunded' WHERE id=? AND payment_state='refund_required'",(bid,))
            if changed:self.event(db,bid,mode+"_refunded",refund=refund_id)

    def complete(self, owner, bid):
        with self.tx() as db:
            old=db.execute('SELECT state FROM bookings WHERE id=? AND owner=?',(bid,owner)).fetchone()
            if old and old['state']=='completed':return
            changed = db.execute("UPDATE bookings SET state='completed' WHERE id=? AND owner=? AND state='confirmed'",(bid,owner)).rowcount
            if not changed: raise Rejected("Only a confirmed booking can complete")
            self.event(db,bid,"service_completed",owner)

    def timeline(self, owner, bid):
        self.booking(bid,owner)
        with self.connect() as db:
            # A replacement's audit includes the cancellations that caused it.
            # UNION terminates cyclic links; ownership is checked at every hop.
            rows = db.execute("""
                WITH RECURSIVE chain(id,quote,recovery_of) AS (
                    SELECT id,quote,recovery_of FROM bookings WHERE id=? AND owner=?
                    UNION
                    SELECT b.id,b.quote,b.recovery_of FROM bookings b
                    JOIN chain c ON b.id=c.recovery_of WHERE b.owner=?
                )
                SELECT DISTINCT e.* FROM events e
                JOIN chain c ON e.entity=c.id OR e.entity=c.quote
                ORDER BY e.seq
            """,(bid,owner,owner)).fetchall()
        return [dict(r, payload=json.loads(r["payload"])) for r in rows]

    def session(self, sid):
        with self.connect() as db:
            row = db.execute("SELECT payload FROM sessions WHERE id=?",(sid,)).fetchone()
        return json.loads(row[0]) if row else {}

    def save_session(self, sid, state):
        with self.tx() as db:
            db.execute("INSERT INTO sessions VALUES(?,?) ON CONFLICT(id) DO UPDATE SET payload=excluded.payload",(sid,encode(state)))

    def recovery(self, owner, bid, job):
        old = self.booking(bid,owner)
        if old["state"] != "cancelled": raise Rejected("Recovery starts only after cancellation")
        job=self.normalize_job(job)
        self.validate_recovery(owner,bid,job['slot'],job['service'],job.get('details',{}),job,budget=job['budget'])
        choices, excluded = self.match(job)
        choices = [p for p in choices if p["id"] != old["provider"]]
        # Every replacement receives a fresh review card; never silently transfer approval.
        with self.tx() as db:
            self.event(db,bid,"recovery_proposed",owner,alternatives=[p["id"] for p in choices],requires_approval=True)
        return choices, excluded
