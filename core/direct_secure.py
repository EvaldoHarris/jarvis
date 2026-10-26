"""Direct TLS transport. Device certificates, signed requests, replay rejection.

Only personal synchronization is exposed here; no dashboard, login or UI commands.
Enrollment is sealed with a 256-bit secret transferred on the PC's screen/offline.
"""
import asyncio
import base64
import hashlib
import ipaddress
import json
import secrets
import sqlite3
import ssl
import tempfile
import threading
import time
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.x509.oid import NameOID, ExtendedKeyUsageOID
from memory.config_manager import get_base_dir

ROOT = get_base_dir() / 'config' / 'direct'
PORT = 9443
_lock = threading.RLock()


def _protect(data):
    import win32crypt
    return win32crypt.CryptProtectData(data,'Jarvis direct TLS',None,None,None,0)


def _unprotect(data):
    import win32crypt
    return win32crypt.CryptUnprotectData(data,None,None,None,0)[1]


def b64(data):return base64.b64encode(data).decode()
def un64(text):return base64.b64decode(text,validate=True)
def pem(cert):return cert.public_bytes(serialization.Encoding.PEM).decode()


def compact_invitation(raw):
    """Keep only the CA fingerprint in the QR; the public CA is fetched locally."""
    import zlib
    encoded=raw.removeprefix('jarvis-direct:')
    data=json.loads(zlib.decompress(base64.urlsafe_b64decode(encoded[2:])) if encoded.startswith('z:') else base64.urlsafe_b64decode(encoded))
    data['ca_sha256']=hashlib.sha256(data.pop('ca').encode()).hexdigest()
    return 'jarvis-direct:z:'+base64.urlsafe_b64encode(zlib.compress(json.dumps(data,separators=(',',':')).encode(),9)).decode()


class Authority:
    def __init__(self, root=ROOT, protect=_protect, unprotect=_unprotect):
        self.root=Path(root);self.protect=protect;self.unprotect=unprotect
        self.lock=threading.RLock();self.tickets={}

    def db(self):
        from core.continuity import _Connection
        self.root.mkdir(parents=True,exist_ok=True)
        conn=sqlite3.connect(self.root/'devices.db',factory=_Connection)
        conn.executescript('''CREATE TABLE IF NOT EXISTS devices(id TEXT PRIMARY KEY,name TEXT,serial TEXT,cert TEXT,revoked INTEGER DEFAULT 0);
            CREATE TABLE IF NOT EXISTS nonces(device TEXT,nonce TEXT,at INTEGER,PRIMARY KEY(device,nonce));''')
        conn.commit();return conn

    def initialize(self, addresses=()):
        with self.lock:
            self.root.mkdir(parents=True,exist_ok=True)
            if not (self.root/'ca.pem').exists():
                key=ec.generate_private_key(ec.SECP256R1())
                subject=x509.Name([x509.NameAttribute(NameOID.COMMON_NAME,'Jarvis private device CA '+str(uuid.uuid4()))])
                now=datetime.now(timezone.utc)
                cert=(x509.CertificateBuilder().subject_name(subject).issuer_name(subject).public_key(key.public_key())
                      .serial_number(x509.random_serial_number()).not_valid_before(now-timedelta(minutes=5)).not_valid_after(now+timedelta(days=3650))
                      .add_extension(x509.BasicConstraints(ca=True,path_length=0),critical=True)
                      .add_extension(x509.KeyUsage(True,False,False,False,False,True,True,False,False),critical=True)
                      .add_extension(x509.SubjectKeyIdentifier.from_public_key(key.public_key()),critical=False).sign(key,hashes.SHA256()))
                (self.root/'ca.key.bin').write_bytes(self.protect(key.private_bytes(serialization.Encoding.PEM,serialization.PrivateFormat.PKCS8,serialization.NoEncryption())))
                (self.root/'ca.pem').write_text(pem(cert),encoding='ascii')
            self.ca=x509.load_pem_x509_certificate((self.root/'ca.pem').read_bytes())
            self.ca_key=serialization.load_pem_private_key(self.unprotect((self.root/'ca.key.bin').read_bytes()),password=None)
            requested={str(ipaddress.ip_address(ip)) for ip in ('127.0.0.1','::1',*addresses)}
            old=None
            try:old=x509.load_pem_x509_certificate((self.root/'server.pem').read_bytes())
            except OSError:pass
            have={str(ip) for ip in old.extensions.get_extension_for_class(x509.SubjectAlternativeName).value.get_values_for_type(x509.IPAddress)} if old else set()
            if not old or not requested.issubset(have) or old.not_valid_after_utc < datetime.now(timezone.utc)+timedelta(days=7):
                key=ec.generate_private_key(ec.SECP256R1())
                cert=self.issue(key.public_key(),'Jarvis direct server',ExtendedKeyUsageOID.SERVER_AUTH,
                                x509.SubjectAlternativeName([x509.IPAddress(ipaddress.ip_address(ip)) for ip in sorted(have|requested)]+[x509.DNSName('localhost')]))
                (self.root/'server.key.bin').write_bytes(self.protect(key.private_bytes(serialization.Encoding.PEM,serialization.PrivateFormat.PKCS8,serialization.NoEncryption())))
                (self.root/'server.pem').write_text(pem(cert),encoding='ascii')

    def issue(self, public, name, purpose, san=None):
        now=datetime.now(timezone.utc)
        builder=(x509.CertificateBuilder().subject_name(x509.Name([x509.NameAttribute(NameOID.COMMON_NAME,name)]))
                 .issuer_name(self.ca.subject).public_key(public).serial_number(x509.random_serial_number())
                 .not_valid_before(now-timedelta(minutes=5)).not_valid_after(now+timedelta(days=180))
                 .add_extension(x509.BasicConstraints(ca=False,path_length=None),critical=True)
                 .add_extension(x509.KeyUsage(True,False,False,False,False,False,False,False,False),critical=True)
                 .add_extension(x509.ExtendedKeyUsage([purpose]),critical=False)
                 .add_extension(x509.AuthorityKeyIdentifier.from_issuer_public_key(self.ca_key.public_key()),critical=False))
        if san:builder=builder.add_extension(san,critical=False)
        return builder.sign(self.ca_key,hashes.SHA256())

    def ticket(self, enroll_url, direct_url):
        from urllib.parse import urlparse
        target=urlparse(direct_url)
        if target.scheme!='https' or not target.hostname:raise ValueError('Use HTTPS com o IP do PC e porta 9443')
        self.initialize()
        installed=x509.load_pem_x509_certificate((self.root/'server.pem').read_bytes())
        valid={str(ip) for ip in installed.extensions.get_extension_for_class(x509.SubjectAlternativeName).value.get_values_for_type(x509.IPAddress)}
        if str(ipaddress.ip_address(target.hostname)) not in valid:
            raise ValueError('Prepare o listener com este endereço HTTPS, reinicie o Jarvis e depois gere o convite.')
        key=secrets.token_bytes(32);ident=hashlib.sha256(key).hexdigest()
        with self.lock:
            self.tickets={k:v for k,v in self.tickets.items() if v['expires']>time.time()}
            self.tickets[ident]={'key':key,'expires':time.time()+600,'url':direct_url,'reply':None,'digest':None}
        data={'v':1,'enroll':enroll_url,'url':direct_url,'secret':b64(key),'ca':pem(self.ca),'expires':int(time.time()+600)}
        import zlib
        return 'jarvis-direct:z:'+base64.urlsafe_b64encode(zlib.compress(json.dumps(data,separators=(',',':')).encode(),9)).decode()

    def enroll(self, sealed):
        from cryptography.exceptions import InvalidSignature,InvalidTag
        with self.lock:
            ticket=self.tickets.get(sealed.get('ticket'))
            if not ticket or ticket['expires']<time.time():raise ValueError('Convite expirado ou desconhecido')
            digest=hashlib.sha256(json.dumps(sealed,sort_keys=True).encode()).hexdigest()
            if ticket['reply']:
                if digest!=ticket['digest']:raise ValueError('Convite já utilizado por outro pedido')
                return ticket['reply']
            request=json.loads(AESGCM(ticket['key']).decrypt(un64(sealed['nonce']),un64(sealed['data']),b'jarvis-enroll-request-v1'))
            ident=str(uuid.UUID(request['id']))
            der=un64(request['public']);public=serialization.load_der_public_key(der)
            if not isinstance(public,ec.EllipticCurvePublicKey) or not isinstance(public.curve,ec.SECP256R1):raise ValueError('Expected P-256 device key')
            public.verify(un64(request['proof']),('jarvis-enroll\n'+ident+'\n'+hashlib.sha256(der).hexdigest()).encode(),ec.ECDSA(hashes.SHA256()))
            cert=self.issue(public,ident,ExtendedKeyUsageOID.CLIENT_AUTH)
            with self.db() as db:
                if db.execute('SELECT 1 FROM devices WHERE id=?',(ident,)).fetchone():raise ValueError('Device already enrolled; create a fresh key/identity')
                db.execute('INSERT INTO devices VALUES (?,?,?,?,0)',(ident,str(request.get('name',''))[:100],str(cert.serial_number),pem(cert)))
            payload=json.dumps({'id':ident,'cert':pem(cert),'ca':pem(self.ca),'url':ticket['url']}).encode()
            nonce=secrets.token_bytes(12)
            reply={'nonce':b64(nonce),'data':b64(AESGCM(ticket['key']).encrypt(nonce,payload,b'jarvis-enroll-response-v1'))}
            ticket['reply']=reply;ticket['digest']=digest
            return reply

    def authorize(self, method,path,headers,body,now=None):
        now=int(time.time() if now is None else now)
        ident=headers.get('x-jarvis-device','');nonce=headers.get('x-jarvis-nonce','');stamp=headers.get('x-jarvis-time','')
        if len(nonce)!=32 or any(c not in '0123456789abcdef' for c in nonce) or not stamp.isdigit() or abs(now-int(stamp))>90:
            raise ValueError('Invalid or expired request')
        with self.lock, self.db() as db:
            row=db.execute('SELECT cert,revoked FROM devices WHERE id=?',(ident,)).fetchone()
            if not row or row[1]:raise ValueError('Device not authorized')
            cert=x509.load_pem_x509_certificate(row[0].encode())
            if cert.not_valid_after_utc < datetime.now(timezone.utc):raise ValueError('Device certificate expired')
            payload='\n'.join((ident,method,path,stamp,nonce,hashlib.sha256(body).hexdigest())).encode()
            cert.public_key().verify(un64(headers.get('x-jarvis-signature','')),payload,ec.ECDSA(hashes.SHA256()))
            db.execute('DELETE FROM nonces WHERE at<?',(now-180,))
            if db.execute('SELECT COUNT(*) FROM nonces WHERE device=? AND at>?',(ident,now-60)).fetchone()[0]>=120:raise ValueError('Device rate limit')
            try:db.execute('INSERT INTO nonces VALUES (?,?,?)',(ident,nonce,now))
            except sqlite3.IntegrityError:raise ValueError('Replay rejected')
        return ident

    def devices(self):
        with self.db() as db:return [{'id':i,'name':n,'revoked':bool(r)} for i,n,r in db.execute('SELECT id,name,revoked FROM devices')]

    def revoke(self, ident):
        with self.lock,self.db() as db:db.execute('UPDATE devices SET revoked=1 WHERE id=?',(ident,))

    def load_tls(self, config):
        # Only a short-lived owner-private temporary file is used to feed OpenSSL.
        with tempfile.TemporaryDirectory(prefix='jarvis-tls-') as temporary:
            key=Path(temporary)/'key.pem';key.write_bytes(self.unprotect((self.root/'server.key.bin').read_bytes()))
            config.ssl_keyfile=str(key);config.ssl_certfile=str(self.root/'server.pem')
            config.ssl_ca_certs=str(self.root/'ca.pem');config.ssl_cert_reqs=ssl.CERT_REQUIRED
            config.load()
            config.ssl.minimum_version=ssl.TLSVersion.TLSv1_2


authority=Authority()


def create_app(ca=authority, shared_store=None):
    from fastapi import FastAPI, Request
    from fastapi.responses import JSONResponse
    from core.continuity import store
    from core import continuity_runtime as shared
    app=FastAPI(docs_url=None,redoc_url=None,openapi_url=None)
    @app.post('/api/continuity/sync')
    async def sync(req: Request):
        if req.url.scheme!='https':
            return JSONResponse({'error':'TLS transport required'},status_code=403)
        data=bytearray()
        async for chunk in req.stream():
            data.extend(chunk)
            if len(data)>2_000_000:return JSONResponse({'error':'Payload too large'},status_code=413)
        try:
            ident=await asyncio.to_thread(ca.authorize,'POST',req.url.path,req.headers,bytes(data))
            body=json.loads(data)
            if body.get('device',{}).get('id')!=ident:raise ValueError('Device identity mismatch')
        except Exception:
            return JSONResponse({'error':'Authenticated device request required'},status_code=403)
        try:
            if shared_store is None:
                if not shared.config()['enabled'] or shared.config()['role']!='hub':raise ValueError('PC is not the profile hub')
                await asyncio.to_thread(shared.bridge_memory)
            result=await asyncio.to_thread((shared_store or store).sync,body)
            if shared_store is None:await asyncio.to_thread(shared.bridge_memory)
            return JSONResponse(result,headers={'Cache-Control':'no-store'})
        except (ValueError,TypeError,KeyError,AttributeError):
            return JSONResponse({'error':'Invalid synchronization request'},status_code=409)
    return app


def settings():
    try:return json.loads((ROOT/'listener.json').read_text())
    except (OSError,ValueError):return {'enabled':False,'host':'127.0.0.1','port':PORT}


async def serve():
    cfg=settings()
    if not cfg['enabled']:return
    import uvicorn
    authority.initialize([cfg['host']] if cfg['host'] not in ('::','0.0.0.0') else [])
    server_cfg=uvicorn.Config(create_app(),host=cfg['host'],port=cfg['port'],log_level='warning',access_log=False,use_colors=False,
                              limit_concurrency=20,timeout_keep_alive=5)
    authority.load_tls(server_cfg)
    await uvicorn.Server(server_cfg).serve()
