"""Loopback-only provider inbox; credentials are sent in headers, never URLs."""
import json
import threading
import time
from collections import defaultdict,deque
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlsplit,parse_qs
from .communications import Messaging
from .core import Rejected


def make_server(store,port=8765):
    messaging=Messaging(store);failures=defaultdict(deque);lock=threading.Lock()
    class Handler(BaseHTTPRequestHandler):
        server_version='ServiceSetu'
        sys_version=''
        def log_message(self,*args):pass
        def log_error(self,*args):pass
        def reply(self,status,data,content_type='application/json'):
            raw=json.dumps(data).encode() if content_type=='application/json' else data
            self.send_response(status)
            for key,value in {'Content-Type':content_type,'Content-Length':str(len(raw)),'Cache-Control':'no-store','X-Content-Type-Options':'nosniff','Referrer-Policy':'no-referrer','X-Frame-Options':'DENY',
                              'Content-Security-Policy':"default-src 'none'; script-src 'self'; style-src 'self'; connect-src 'self'; frame-ancestors 'none'; base-uri 'none'; form-action 'self'"}.items():self.send_header(key,value)
            self.end_headers();self.wfile.write(raw)
        def valid_origin(self):
            allowed={f'127.0.0.1:{self.server.server_port}',f'localhost:{self.server.server_port}'}
            host=self.headers.get('Host','')
            origin=self.headers.get('Origin')
            return host in allowed and (origin is None or origin in {'http://'+value for value in allowed})
        def provider(self):
            if not self.valid_origin():raise PermissionError()
            now=time.monotonic();ip=self.client_address[0]
            with lock:
                while failures[ip] and failures[ip][0]<now-60:failures[ip].popleft()
                if len(failures[ip])>=20:raise PermissionError()
            auth=self.headers.get('Authorization','')
            try:return messaging.authenticate(auth[7:] if auth.startswith('Bearer ') else '')
            except Rejected:
                with lock:failures[ip].append(now)
                raise PermissionError() from None
        def do_GET(self):
            if not self.valid_origin():self.reply(403,{'error':'Request denied'});return
            path=urlsplit(self.path)
            assets={'/':('index.html','text/html; charset=utf-8'),'/portal.js':('portal.js','text/javascript; charset=utf-8'),'/portal.css':('portal.css','text/css; charset=utf-8')}
            if path.path in assets and not path.query:
                name,kind=assets[path.path];self.reply(200,(Path(__file__).parent/'portal'/name).read_bytes(),kind);return
            try:
                provider=self.provider()
                if path.path=='/api/bookings' and not path.query:self.reply(200,{'bookings':messaging.provider_bookings(provider)});return
                parts=path.path.strip('/').split('/')
                if len(parts)==4 and parts[:2]==['api','bookings'] and parts[3]=='messages':
                    params=parse_qs(path.query);after=int(params.get('after',['0'])[0])
                    if set(params)-{'after'}:raise ValueError()
                    self.reply(200,messaging.thread(parts[2],provider,'provider',after));return
                self.reply(404,{'error':'Unavailable'})
            except PermissionError:self.reply(401,{'error':'Authentication required'})
            except (Rejected,ValueError,TypeError):self.reply(404,{'error':'Booking unavailable'})
            except Exception:self.reply(503,{'error':'Inbox temporarily unavailable'})
        def do_POST(self):
            try:
                provider=self.provider()
                if self.headers.get('Transfer-Encoding') or self.headers.get('Content-Type','').split(';')[0]!='application/json':raise ValueError()
                length=int(self.headers.get('Content-Length','0'))
                if not 0<length<=12000:raise ValueError()
                self.connection.settimeout(5)
                body=json.loads(self.rfile.read(length))
                parts=urlsplit(self.path).path.strip('/').split('/')
                if len(parts)!=4 or parts[:2]!=['api','bookings'] or parts[3]!='messages' or urlsplit(self.path).query:
                    self.reply(404,{'error':'Unavailable'});return
                if not isinstance(body,dict) or set(body)!={'text','client_id'}:raise ValueError()
                result=messaging.post(parts[2],provider,'provider',body['text'],body['client_id'])
                self.reply(200,result)
            except PermissionError:self.reply(401,{'error':'Authentication required'})
            except Rejected as exc:
                error=str(exc)
                self.reply(400,{'error':error if error.startswith(('Messages must','Message limit','Message request')) else 'Booking unavailable'})
            except (ValueError,TypeError,UnicodeError):self.reply(400,{'error':'Invalid request'})
            except Exception:self.reply(503,{'error':'Inbox temporarily unavailable'})
    return ThreadingHTTPServer(('127.0.0.1',port),Handler)


def run(store,provider,port=8765):
    store.provider(provider)
    server=make_server(store,port)
    token=Messaging(store).issue_access(provider)
    print(f'Local provider inbox: http://127.0.0.1:{server.server_port}/')
    print('Provider:',provider)
    print('Private access token (expires in one hour; do not share or publish):',token)
    print('This portal is available only on this PC. Use fictional demo data.')
    try:server.serve_forever()
    except KeyboardInterrupt:pass
    finally:
        with store.tx() as db:db.execute('UPDATE provider_access SET revoked=1 WHERE digest=?',(__import__('hashlib').sha256(token.encode()).hexdigest(),))
        server.server_close()
