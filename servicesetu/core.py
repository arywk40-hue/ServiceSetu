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
from .locations import canonical
from .catalogue import SERVICES,unavailable_message


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
CREATE TABLE IF NOT EXISTS events(seq INTEGER PRIMARY KEY AUTOINCREMENT,
 at REAL NOT NULL, entity TEXT NOT NULL, kind TEXT NOT NULL, actor TEXT NOT NULL,
 payload TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS sessions(id TEXT PRIMARY KEY, payload TEXT NOT NULL);
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
        db.execute("INSERT INTO events(at,entity,kind,actor,payload) VALUES(?,?,?,?,?)",
                   (self.clock(), entity, kind, actor, encode(payload)))

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

    def seed(self, days=1, expanded=False):
        """Six default or twelve expanded fictional providers; mock registry."""
        if not isinstance(days,int) or isinstance(days,bool) or not 1<=days<=14:
            raise Rejected("Demo days must be a whole number from 1 to 14")
        now = datetime.fromtimestamp(self.clock(), timezone.utc)
        dates=[(now.astimezone(ZoneInfo("Asia/Kolkata"))+timedelta(days=offset)).date().isoformat()
               for offset in range(1,days+1)]
        names = ["CoolCare AC", "Breeze AC", "Lapsed AC", "FlowFix Plumbing", "TapCare Plumbing", "Renewal Plumbing"]
        if expanded:
            names += ["FreshNest Cleaning", "SparkleSpace Cleaning", "Lapsed Cleaning",
                      "CircuitCheck Electrical", "BrightWire Electrical", "Lapsed Electrical"]
        for i, name in enumerate(names):
            service = ("ac","plumbing","cleaning","electrical")[i//3]
            expiry = (now + timedelta(days=-1 if i in (2,8,11) else 1 if i == 5 else 90)).date().isoformat()
            p = {"id": f"p{i+1}", "name": name, "service": service, "city": "bengaluru",
                 "area": "indiranagar", "amount": [69900, 74900, 59900, 49900, 54900, 45900,79900,89900,59900,39900,49900,29900][i],
                 "slots": [f"{day}T{hour}:00:00+05:30" for day in dates for hour in ("10","14")],
                 "credential": {"type": "demo_skill_certificate", "jurisdiction": "IN-demo",
                  "issuer": "Mock Service Registry", "status": "provider_supplied" if i%3==1 else "verified",
                  "source": "seeded provider upload" if i%3==1 else "mock-registry://servicesetu",
                  "checked_at": now.isoformat(), "expires": expiry, "method": "mock_lookup",
                  "verifier": "demo-verification-agent", "policy_version": "IN-demo-v1"},
                 "available": True}
            with self.tx() as db:
                db.execute("INSERT OR IGNORE INTO providers VALUES(?,?)", (p["id"], encode(p)))

    def trust(self, p, slot):
        # End-of-day expiry must cover the appointment's local calendar day.
        c = p["credential"]
        day = datetime.fromisoformat(slot).date().isoformat()
        today = datetime.fromtimestamp(self.clock(), ZoneInfo("Asia/Kolkata")).date().isoformat()
        status = "expired" if c["expires"] < max(day, today) else c["status"]
        return dict(c, status=status, eligible=status in ("verified", "provider_supplied"))

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
        city=job.get("city","bengaluru")
        area=job.get("area","")
        if not isinstance(city,str) or not isinstance(area,str):
            raise Rejected("City and area must be text")
        city,area=canonical(city,"city"),canonical(area,"area")
        if city!="bengaluru" or area!="indiranagar":
            raise Rejected("Demo covers Indiranagar, Bengaluru only")
        try:
            dt=datetime.fromisoformat(job["slot"])
            if dt.tzinfo is None or dt.timestamp()<=self.clock(): raise ValueError
            budget=job["budget"]
            if not isinstance(budget,int) or isinstance(budget,bool) or budget<=0: raise ValueError
        except (ValueError,TypeError,KeyError,OverflowError):
            raise Rejected("Provide a future timezone-qualified slot and a positive whole-paise budget") from None
        return {"service":job["service"],**({"package":package} if package else {}),"city":city.lower(),"area":area.lower(),
                "slot":dt.astimezone(ZoneInfo("Asia/Kolkata")).isoformat(timespec="seconds"),"budget":budget}

    def match(self, job):
        job=self.normalize_job(job)
        slot,budget=job["slot"],job["budget"]
        selected, excluded = [], []
        for p in self.providers():
            if p["service"] != job["service"]:
                continue
            trust = self.trust(p, slot)
            reason = None
            if not trust["eligible"]: reason = "Credential expired before the service date"
            elif not p["available"] or slot not in p["slots"]: reason = "Provider has no matching slot"
            elif not self.slot_free(p["id"],slot): reason = "Slot already reserved"
            elif p["amount"] > budget: reason = "Above your budget"
            if reason: excluded.append({"provider": p["id"], "name": p["name"], "reason": reason})
            else: selected.append(dict(p, trust=trust))
        selected.sort(key=lambda p: (p["trust"]["status"] != "verified", p["amount"]))
        return selected, excluded

    def available_slots(self, job, limit=4):
        """Read-only suggestions; never change a request or reserve capacity."""
        job = self.normalize_job(job)
        slots = {slot for p in self.providers() if p["service"] == job["service"] for slot in p["slots"]}
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

    def quote(self, owner, provider, slot, previous=None):
        p = self.provider(provider)
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
                "owner": owner, "version": version, "amount": p["amount"], "currency": "INR",
                "kind": "fixed", "scope": SERVICES[p["service"]]["scope"],
                "exclusions": SERVICES[p["service"]]["exclusions"],
                "cancellation": "Demo: full test-payment reversal before work starts",
                "trust": self.trust(p, slot), "expires": self.clock()+300,
                "availability": {"source": f"provider-agent:{provider}", "observed_at": self.clock(),
                    "expires": self.clock()+300, "confidence": "provider-confirmed demo", "hold_capable": True}}
            digest = hashlib.sha256(encode(payload).encode()).hexdigest()
            db.execute("INSERT INTO quotes VALUES(?,?,?,?,?,?,?,?,?,?)", (qid, provider, slot, owner, version,
                       p["amount"], payload["expires"], encode(payload), digest, previous))
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

    def hold(self, owner, qid, recovery_of=None, request_id=None):
        bid = request_id or ident("b")
        with self.tx() as db:
            self.expire(db)
            q = db.execute("SELECT * FROM quotes WHERE id=? AND owner=?", (qid, owner)).fetchone()
            if not q: raise Rejected("Quote not found in this conversation")
            if q["expires"] <= self.clock(): raise Rejected("Quote and availability expired; request fresh alternatives")
            p = self.provider(q["provider"])
            if not p["available"] or q["slot"] not in p["slots"] or not self.trust(p,q["slot"])["eligible"]:
                raise Rejected("Final slot or credential revalidation failed")
            if recovery_of:
                old = db.execute("SELECT * FROM bookings WHERE id=? AND owner=? AND state='cancelled'", (recovery_of,owner)).fetchone()
                if not old: raise Rejected("Recovery must reference your cancelled booking")
            existing = db.execute("SELECT id FROM bookings WHERE owner=? AND quote=? AND state='held'", (owner,qid)).fetchone()
            if existing: return self.booking(existing["id"],owner)
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
        return self.booking(bid,owner)

    def booking(self, bid, owner):
        with self.connect() as db:
            row = db.execute("SELECT * FROM bookings WHERE id=? AND owner=?", (bid,owner)).fetchone()
        if not row: raise Rejected("Booking not found in this conversation")
        return dict(row)

    def approve(self, owner, bid, qid):
        with self.tx() as db:
            b = db.execute("SELECT * FROM bookings WHERE id=? AND owner=?", (bid,owner)).fetchone()
            if not b or b["quote"] != qid: raise Rejected("Approval does not match the held quote")
            if b["state"] != "held" or b["hold_until"] <= self.clock(): raise Rejected("Hold expired; refresh before approving")
            db.execute("UPDATE bookings SET approved=1 WHERE id=?", (bid,))
            self.event(db,bid,"customer_approved",owner,quote=qid)

    def begin_payment(self, owner, bid, idem):
        with self.tx() as db:
            b = db.execute("SELECT * FROM bookings WHERE id=? AND owner=?", (bid,owner)).fetchone()
            if not b or not b["approved"]: raise Rejected("Explicit customer approval required before payment")
            old = db.execute("SELECT * FROM payments WHERE idem=? OR booking=?", (idem,bid)).fetchone()
            if old:
                if old["booking"] != bid or old["idem"] != idem: raise Rejected("Idempotency key conflict")
                return dict(old)
            if b["state"] != "held" or b["hold_until"] <= self.clock(): raise Rejected("Hold expired before payment")
            q = db.execute("SELECT * FROM quotes WHERE id=?",(b["quote"],)).fetchone()
            if q["expires"] <= self.clock() or not self.trust(self.provider(b["provider"]),b["slot"])["eligible"]:
                raise Rejected("Quote or credential revalidation failed")
            pid = ident("pay")
            db.execute("INSERT INTO payments VALUES(?,?,?,?,?,?)",(pid,bid,idem,q["amount"],"pending",None))
            db.execute("UPDATE bookings SET payment_state='pending' WHERE id=?",(bid,))
            self.event(db,bid,"payment_started",owner,payment=pid,amount=q["amount"],quote=b["quote"])
        return {"id":pid,"booking":bid,"idem":idem,"amount":q["amount"],"state":"pending","external":None}

    def attach_checkout(self, owner, bid, checkout):
        self.booking(bid,owner)
        with self.tx() as db:
            db.execute("UPDATE payments SET external=? WHERE booking=? AND state='pending'", (checkout,bid))
            self.event(db,bid,"stripe_test_checkout_created",owner,checkout=checkout)

    def settle(self, owner, bid, *, success=True, provider_confirm=True, external=None):
        """Called by mock adapter or only after server-side Stripe verification."""
        with self.tx() as db:
            b = db.execute("SELECT * FROM bookings WHERE id=? AND owner=?",(bid,owner)).fetchone()
            pay = db.execute("SELECT * FROM payments WHERE booking=?",(bid,)).fetchone()
            if not b or not pay or not b["approved"]: raise Rejected("Approved payment intent required")
            if pay["state"] in ("paid","voided","declined","refund_required","refunded"):
                return dict(b)
            q = db.execute("SELECT * FROM quotes WHERE id=?",(b["quote"],)).fetchone()
            p = self.provider(b["provider"])
            fresh = b["state"] == "held" and b["hold_until"] > self.clock() and q["expires"] > self.clock()
            fresh = fresh and p["available"] and b["slot"] in p["slots"] and self.trust(p,b["slot"])["eligible"]
            if success and provider_confirm and fresh:
                db.execute("UPDATE payments SET state='paid',external=COALESCE(?,external) WHERE booking=?",(external,bid))
                db.execute("UPDATE bookings SET state='confirmed',payment_state='paid' WHERE id=?",(bid,))
                self.event(db,bid,"booking_confirmed",owner,quote=b["quote"],payment=pay["id"],amount=pay["amount"])
            else:
                state = "refund_required" if external and success else "voided" if success else "declined"
                db.execute("UPDATE payments SET state=?,external=COALESCE(?,external) WHERE booking=?",(state,external,bid))
                db.execute("UPDATE bookings SET state='cancelled',payment_state=? WHERE id=?",(state,bid))
                self.event(db,bid,"payment_compensated",payment_state=state,reason="payment failed" if not success else "provider declined or hold expired")
                self.event(db,bid,"slot_released")
        return self.booking(bid,owner)

    def cancel(self, owner, bid, actor="customer", stripe=False):
        with self.tx() as db:
            b = db.execute("SELECT * FROM bookings WHERE id=? AND owner=?",(bid,owner)).fetchone()
            if not b: raise Rejected("Booking not found")
            if b["state"] == "cancelled": return dict(b)
            if b["state"] == "completed": raise Rejected("Completed work requires human dispute review")
            state = ("refund_required" if stripe else "refunded") if b["payment_state"]=="paid" else b["payment_state"]
            db.execute("UPDATE bookings SET state='cancelled',payment_state=? WHERE id=?",(state,bid))
            db.execute("UPDATE payments SET state=? WHERE booking=?",(state,bid))
            self.event(db,bid,"provider_cancelled" if actor.startswith("provider:") else "customer_cancelled",actor,payment_state=state)
            self.event(db,bid,"slot_released",actor)
        return self.booking(bid,owner)

    def refund_done(self, owner, bid, refund_id):
        self.booking(bid,owner)
        with self.tx() as db:
            db.execute("UPDATE payments SET state='refunded' WHERE booking=? AND state='refund_required'",(bid,))
            db.execute("UPDATE bookings SET payment_state='refunded' WHERE id=? AND payment_state='refund_required'",(bid,))
            self.event(db,bid,"stripe_test_refunded",refund=refund_id)

    def complete(self, owner, bid):
        with self.tx() as db:
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
        choices, excluded = self.match(job)
        choices = [p for p in choices if p["id"] != old["provider"]]
        # Every replacement receives a fresh review card; never silently transfer approval.
        with self.tx() as db:
            self.event(db,bid,"recovery_proposed",owner,alternatives=[p["id"] for p in choices],requires_approval=True)
        return choices, excluded
