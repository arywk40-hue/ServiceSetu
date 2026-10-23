"""Small private booking-linked operator queue; no automated dispute decisions."""
import json
import secrets
from .core import Rejected,encode,ident
from .communications import Messaging


class Problems:
    def __init__(self,store):
        self.store=store
        self.messaging=Messaging(store)
        with store.connect() as db:
            db.execute('''CREATE TABLE IF NOT EXISTS booking_problems(
              id TEXT PRIMARY KEY,booking TEXT NOT NULL REFERENCES bookings(id),
              owner TEXT NOT NULL,at REAL NOT NULL,body BLOB NOT NULL,client_id TEXT NOT NULL,
              acknowledged_by TEXT,UNIQUE(booking,owner,client_id))''')

    def report(self,owner,bid,text,client_id=None):
        if not isinstance(text,str) or not 1<=len(text.strip())<=2000:raise Rejected('Describe the problem in 1–2000 characters')
        text=text.strip();client_id=client_id or secrets.token_hex(16)
        if not isinstance(client_id,str) or not 1<=len(client_id)<=100:raise Rejected('Invalid report identifier')
        b=self.store.booking(bid,owner)
        if not b['quote'] or b['state'] not in ('confirmed','completed','cancelled'):raise Rejected('Report a problem with a confirmed, completed or cancelled booking')
        box=self.messaging._box()
        with self.store.tx() as db:
            self.store.booking(bid,owner)
            prior=db.execute('SELECT * FROM booking_problems WHERE booking=? AND owner=? AND client_id=?',(bid,owner,client_id)).fetchone()
            if prior:
                saved=json.loads(box.decrypt(bytes(prior['body'])))
                if saved!=dict(booking=bid,owner=owner,text=text):raise Rejected('Report identifier already used for another problem')
                return {'id':prior['id'],'status':'recorded','duplicate':True}
            count=db.execute('SELECT count(*) FROM booking_problems WHERE owner=? AND at>?',(owner,self.store.clock()-60)).fetchone()[0]
            if count>=5:raise Rejected('Report limit reached; wait a minute')
            rid=ident('problem')
            body=bytes(box.encrypt(encode(dict(booking=bid,owner=owner,text=text)).encode()))
            db.execute('INSERT INTO booking_problems VALUES(?,?,?,?,?,?,NULL)',(rid,bid,owner,self.store.clock(),body,client_id))
            self.store.event(db,bid,'problem_reported',owner,report=rid,status='recorded')
        return {'id':rid,'status':'recorded','duplicate':False}

    def queue(self):
        """Trusted local operator only; never exposed as an agent/provider action."""
        with self.store.connect() as db:rows=db.execute('SELECT * FROM booking_problems ORDER BY at,id').fetchall()
        box=self.messaging._box() if rows else None
        results=[]
        for row in rows:
            value=json.loads(box.decrypt(bytes(row['body'])))
            if value['booking']!=row['booking'] or value['owner']!=row['owner']:raise Rejected('Report could not be read safely')
            results.append(dict(id=row['id'],booking=row['booking'],at=row['at'],text=value['text'],acknowledged_by=row['acknowledged_by']))
        return results

    def acknowledge(self,rid,operator):
        if not isinstance(operator,str) or not operator.strip():raise Rejected('Operator name is required')
        with self.store.tx() as db:
            row=db.execute('SELECT * FROM booking_problems WHERE id=?',(rid,)).fetchone()
            if not row:raise Rejected('Problem report unavailable')
            if not row['acknowledged_by']:
                db.execute('UPDATE booking_problems SET acknowledged_by=? WHERE id=?',(operator.strip(),rid))
                self.store.event(db,row['booking'],'problem_acknowledged','operator',report=rid,operator=operator.strip())
