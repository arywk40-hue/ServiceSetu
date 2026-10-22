"""Booking-scoped messaging. Message bodies never enter model prompts or audit payloads."""
import base64
import hashlib
import json
import os
import re
import secrets
import sqlite3
import stat
import unicodedata
from pathlib import Path
from .core import Rejected,encode,ident

SCHEMA='''
CREATE TABLE IF NOT EXISTS booking_messages(
 seq INTEGER PRIMARY KEY AUTOINCREMENT,id TEXT UNIQUE NOT NULL,
 booking TEXT NOT NULL REFERENCES bookings(id),provider TEXT NOT NULL,
 actor TEXT NOT NULL,side TEXT NOT NULL CHECK(side IN ('customer','provider')),
 at REAL NOT NULL,body BLOB NOT NULL,client_id TEXT NOT NULL,
 notice TEXT NOT NULL DEFAULT 'none',attempts INTEGER NOT NULL DEFAULT 0,next_attempt REAL NOT NULL DEFAULT 0,
 UNIQUE(booking,actor,client_id));
CREATE INDEX IF NOT EXISTS message_thread ON booking_messages(booking,seq);
CREATE TABLE IF NOT EXISTS provider_access(
 digest TEXT PRIMARY KEY,provider TEXT NOT NULL REFERENCES providers(id),expires REAL NOT NULL,revoked INTEGER NOT NULL DEFAULT 0);
'''


def _protect(data,encrypt):
    """Windows user-scoped DPAPI; no locally invented encryption."""
    import ctypes
    from ctypes import wintypes
    class Blob(ctypes.Structure):_fields_=[('size',wintypes.DWORD),('data',ctypes.POINTER(ctypes.c_ubyte))]
    buffer=ctypes.create_string_buffer(data);source=Blob(len(data),ctypes.cast(buffer,ctypes.POINTER(ctypes.c_ubyte)));dest=Blob()
    api=ctypes.windll.crypt32.CryptProtectData if encrypt else ctypes.windll.crypt32.CryptUnprotectData
    if not api(ctypes.byref(source),None,None,None,None,1,ctypes.byref(dest)):raise Rejected('Private messaging key is unavailable for this Windows user')
    try:return ctypes.string_at(dest.data,dest.size)
    finally:ctypes.windll.kernel32.LocalFree(dest.data)


class Messaging:
    def __init__(self,store):
        self.store=store
        with store.connect() as db:db.executescript(SCHEMA)

    def _box(self):
        try:from nacl.secret import SecretBox
        except ImportError:raise Rejected('Install the communications extras before using private messaging') from None
        path=Path(self.store.path).with_suffix('.message-key')
        if path.is_symlink():raise Rejected('Messaging key must be a private regular file')
        try:
            data=path.read_bytes()
        except FileNotFoundError:
            with self.store.connect() as db:
                if db.execute('SELECT 1 FROM booking_messages LIMIT 1').fetchone():raise Rejected('Messaging key is missing; restore it before reading or sending messages')
            key=secrets.token_bytes(SecretBox.KEY_SIZE)
            data=b'DPAPI1\n'+_protect(key,True) if os.name=='nt' else b'RAW1\n'+key
            try:
                fd=os.open(path,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
                with os.fdopen(fd,'wb') as out:out.write(data)
            except FileExistsError:data=path.read_bytes()
        if os.name!='nt' and stat.S_IMODE(path.stat().st_mode)&0o077:raise Rejected('Messaging key permissions must be restricted to its owner')
        if data.startswith(b'DPAPI1\n') and os.name=='nt':key=_protect(data[7:],False)
        elif data.startswith(b'RAW1\n') and os.name!='nt':key=data[5:]
        else:raise Rejected('Messaging key is unavailable on this operating system')
        try:return SecretBox(key)
        except (ValueError,TypeError):raise Rejected('Private messaging key is invalid') from None

    def issue_access(self,provider,seconds=3600):
        self.store.provider(provider)
        if not isinstance(seconds,int) or not 60<=seconds<=28800:raise Rejected('Provider access must expire within eight hours')
        token=secrets.token_urlsafe(32)
        with self.store.tx() as db:
            db.execute('UPDATE provider_access SET revoked=1 WHERE provider=?',(provider,))
            db.execute('INSERT INTO provider_access VALUES(?,?,?,0)',(hashlib.sha256(token.encode()).hexdigest(),provider,self.store.clock()+seconds))
        return token

    def authenticate(self,token):
        if not isinstance(token,str) or not 32<=len(token)<=128:raise Rejected('Provider authentication required')
        with self.store.connect() as db:
            row=db.execute('SELECT provider FROM provider_access WHERE digest=? AND revoked=0 AND expires>?',(hashlib.sha256(token.encode()).hexdigest(),self.store.clock())).fetchone()
        if not row:raise Rejected('Provider authentication required')
        return row['provider']

    def _booking(self,db,bid,actor,side,write=False):
        row=db.execute('SELECT * FROM bookings WHERE id=?',(bid,)).fetchone()
        if not row or (row['owner'] if side=='customer' else row['provider'])!=actor:raise Rejected('Booking unavailable')
        if side=='provider' and row['state']!='confirmed':raise Rejected('Booking unavailable')
        if write and row['state']!='confirmed':raise Rejected('Messaging is available only for confirmed bookings')
        return dict(row)

    def post(self,bid,actor,side,text,client_id=None):
        if side not in ('customer','provider'):raise Rejected('Invalid message sender')
        if not isinstance(text,str) or not 1<=len(text.strip())<=2000 or any(unicodedata.category(c)=='Cc' and c not in '\n\r\t' for c in text):raise Rejected('Messages must contain 1–2000 text characters')
        text=text.strip();client_id=client_id or secrets.token_hex(16)
        if not isinstance(client_id,str) or not re.fullmatch(r'[A-Za-z0-9_-]{8,80}',client_id):raise Rejected('A valid message request identifier is required')
        with self.store.connect() as db:self._booking(db,bid,actor,side,write=True)
        box=self._box()
        with self.store.tx() as db:
            b=self._booking(db,bid,actor,side,write=True)
            old=db.execute('SELECT * FROM booking_messages WHERE booking=? AND actor=? AND client_id=?',(bid,actor,client_id)).fetchone()
            if old:
                if self._decode(old,box)['text']!=text:raise Rejected('Message request identifier was already used for different text')
                return {'id':old['id'],'status':'saved','duplicate':True}
            count=db.execute('SELECT count(*) FROM booking_messages WHERE actor=? AND at>?',(actor,self.store.clock()-60)).fetchone()[0]
            if count>=10:raise Rejected('Message limit reached; wait a minute before sending again')
            mid=ident('m');now=self.store.clock()
            payload=encode(dict(booking=bid,actor=actor,side=side,text=text))
            body=bytes(box.encrypt(payload.encode()))
            db.execute('INSERT INTO booking_messages(id,booking,provider,actor,side,at,body,client_id,notice) VALUES(?,?,?,?,?,?,?,?,?)',
                       (mid,bid,b['provider'],actor,side,now,body,client_id,'pending' if side=='provider' else 'none'))
            self.store.event(db,bid,'booking_message_saved',side,message=mid,side=side)
        return {'id':mid,'status':'saved','duplicate':False}

    def _decode(self,row,box):
        try:
            value=json.loads(box.decrypt(bytes(row['body'])))
            if any(value[field]!=row[field] for field in ('booking','actor','side')):raise ValueError()
            return {'id':row['id'],'seq':row['seq'],'side':row['side'],'at':row['at'],'text':value['text']}
        except Exception:raise Rejected('Message could not be read safely') from None

    def thread(self,bid,actor,side,after=0):
        if side not in ('customer','provider') or type(after) is not int or after<0:raise Rejected('Invalid thread request')
        with self.store.connect() as db:
            self._booking(db,bid,actor,side)
            rows=db.execute('SELECT * FROM booking_messages WHERE booking=? AND seq>? ORDER BY seq LIMIT 51',(bid,after)).fetchall()
        box=self._box() if rows else None
        return {'messages':[self._decode(row,box) for row in rows[:50]],'has_more':len(rows)>50,'next_after':rows[min(len(rows),50)-1]['seq'] if rows else after}

    def provider_bookings(self,provider):
        self.store.provider(provider)
        with self.store.connect() as db:
            rows=db.execute("SELECT id FROM bookings WHERE provider=? AND state='confirmed' ORDER BY slot LIMIT 100",(provider,)).fetchall()
        results=[]
        for row in rows:
            with self.store.connect() as db:
                b=self._booking(db,row['id'],provider,'provider')
                event=db.execute("SELECT payload FROM events WHERE entity=? AND kind='service_address_recorded' ORDER BY seq DESC LIMIT 1",(b['id'],)).fetchone()
                q=json.loads(db.execute('SELECT payload FROM quotes WHERE id=?',(b['quote'],)).fetchone()[0])
            results.append({'id':b['id'],'slot':b['slot'],'service':q['scope'],'location':q.get('location',{}),
                            'address':json.loads(event[0])['address'] if event else None})
        return results

    def pending_notices(self):
        with self.store.connect() as db:
            rows=db.execute("SELECT m.id,m.booking,b.owner FROM booking_messages m JOIN bookings b ON b.id=m.booking WHERE m.notice='pending' AND m.attempts<5 AND m.next_attempt<=? AND b.state='confirmed' ORDER BY m.seq LIMIT 20",(self.store.clock(),)).fetchall()
        return [dict(row) for row in rows]

    def notice_result(self,mid,success):
        with self.store.tx() as db:
            db.execute("UPDATE booking_messages SET notice=?,attempts=attempts+1,next_attempt=? WHERE id=?",('sent' if success else 'pending',self.store.clock()+30,mid))
