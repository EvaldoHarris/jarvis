"""PC peer for the same direct TLS protocol as Android. No proxy or HTTP fallback."""
import base64
import hashlib
import ipaddress
import json
import secrets
import ssl
import tempfile
import time
import uuid
from pathlib import Path
from urllib.parse import urlparse

import httpx
from cryptography import x509
from cryptography.hazmat.primitives import hashes,serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from core import direct_secure as protocol

FILE=protocol.ROOT.parent/'direct_client.bin'
PENDING=protocol.ROOT.parent/'direct_client_pending.bin'


def _read(path=None):
    path=path or FILE
    return json.loads(protocol._unprotect(path.read_bytes()))
def _save(value,path=None):
    path=path or FILE
    path.parent.mkdir(parents=True,exist_ok=True)
    temporary=path.with_suffix('.tmp')
    temporary.write_bytes(protocol._protect(json.dumps(value).encode()));temporary.replace(path)


def endpoint():
    try:return _read()['url']
    except (OSError,ValueError):return ''


def set_endpoint(url):
    parsed=urlparse(url)
    if parsed.scheme!='https' or not parsed.hostname or parsed.username or parsed.password or parsed.path not in ('','/') or parsed.query or parsed.fragment:
        raise ValueError('Informe HTTPS com o endereço do mesmo PC principal')
    value=_read();value['url']=url.rstrip('/');_save(value)


def enroll(raw,name):
    encoded=raw.strip().removeprefix('jarvis-direct:')
    import zlib
    if encoded.startswith('z:'):
        packed=base64.urlsafe_b64decode(encoded[2:])
        decoded=zlib.decompressobj().decompress(packed,16001)
        if len(decoded)>16000:raise ValueError('Convite muito grande')
    else:decoded=base64.urlsafe_b64decode(encoded)
    ticket=json.loads(decoded)
    secret=protocol.un64(ticket['secret']);ident=hashlib.sha256(secret).hexdigest()
    try:
        if _read().get('ticket')==ident:return
    except (OSError,ValueError):pass
    if ticket.get('v')!=1 or len(secret)!=32 or ticket['expires']<time.time():raise ValueError('Convite expirado')
    uri=urlparse(ticket['enroll']);ip=ipaddress.ip_address(uri.hostname)
    if uri.scheme!='http' or not (ip.is_private or ip.is_loopback or ip in ipaddress.ip_network('100.64.0.0/10')) or uri.path!='/api/direct/enroll' or uri.query or uri.fragment or uri.username:
        raise ValueError('Use o convite do PC na rede local para o primeiro pareamento')
    target=urlparse(ticket['url'])
    if target.scheme!='https' or not target.hostname or target.username or target.query or target.fragment or target.path not in ('','/'):
        raise ValueError('Invalid secure endpoint')
    if 'ca' not in ticket:
        response=httpx.get(f'{uri.scheme}://{uri.netloc}/api/direct/ca',timeout=8,trust_env=False,follow_redirects=False)
        response.raise_for_status()
        if len(response.content)>8192:raise ValueError('Certificado muito grande')
        ca_text=response.json()['ca']
        if hashlib.sha256(ca_text.encode()).hexdigest()!=ticket.get('ca_sha256'):
            raise ValueError('Certificado recebido não corresponde ao QR')
        ticket['ca']=ca_text
    ca=x509.load_pem_x509_certificate(ticket['ca'].encode())
    ca.verify_directly_issued_by(ca)
    try:pending=_read(PENDING)
    except (OSError,ValueError):pending={}
    if pending.get('ticket')!=ident:
        key=ec.generate_private_key(ec.SECP256R1());device=str(uuid.uuid4())
        public=key.public_key().public_bytes(serialization.Encoding.DER,serialization.PublicFormat.SubjectPublicKeyInfo)
        proof=key.sign(('jarvis-enroll\n'+device+'\n'+hashlib.sha256(public).hexdigest()).encode(),ec.ECDSA(hashes.SHA256()))
        body=json.dumps({'id':device,'name':name,'public':protocol.b64(public),'proof':protocol.b64(proof)}).encode()
        nonce=secrets.token_bytes(12)
        sealed={'ticket':ident,'nonce':protocol.b64(nonce),'data':protocol.b64(AESGCM(secret).encrypt(nonce,body,b'jarvis-enroll-request-v1'))}
        pending={'ticket':ident,'id':device,'private':key.private_bytes(serialization.Encoding.PEM,serialization.PrivateFormat.PKCS8,serialization.NoEncryption()).decode(),'request':sealed}
        _save(pending,PENDING)
    response=httpx.post(ticket['enroll'],json=pending['request'],timeout=8,trust_env=False,follow_redirects=False)
    response.raise_for_status();sealed=response.json()
    reply=json.loads(AESGCM(secret).decrypt(protocol.un64(sealed['nonce']),protocol.un64(sealed['data']),b'jarvis-enroll-response-v1'))
    cert=x509.load_pem_x509_certificate(reply['cert'].encode());cert.verify_directly_issued_by(ca)
    key=serialization.load_pem_private_key(pending['private'].encode(),None)
    if cert.public_key().public_numbers()!=key.public_key().public_numbers() or reply['id']!=pending['id'] or reply['url']!=ticket['url']:
        raise ValueError('Enrollment identity mismatch')
    _save({**reply,'ca':ticket['ca'],'private':pending['private'],'ticket':ident})
    PENDING.unlink(missing_ok=True)


def sync(body):
    cfg=_read();key=serialization.load_pem_private_key(cfg['private'].encode(),None)
    body=json.loads(json.dumps(body));body['device']['id']=cfg['id']
    encoded=json.dumps(body,ensure_ascii=False).encode();nonce=secrets.token_hex(16);stamp=str(int(time.time()));path='/api/continuity/sync'
    payload='\n'.join((cfg['id'],'POST',path,stamp,nonce,hashlib.sha256(encoded).hexdigest())).encode()
    headers={'x-jarvis-device':cfg['id'],'x-jarvis-time':stamp,'x-jarvis-nonce':nonce,'x-jarvis-signature':protocol.b64(key.sign(payload,ec.ECDSA(hashes.SHA256()))),'content-type':'application/json'}
    ctx=ssl.create_default_context(cadata=cfg['ca']);ctx.minimum_version=ssl.TLSVersion.TLSv1_2
    with tempfile.TemporaryDirectory(prefix='jarvis-client-tls-') as temp:
        cert=Path(temp)/'cert.pem';private=Path(temp)/'key.pem'
        cert.write_text(cfg['cert']);private.write_text(cfg['private'])
        ctx.load_cert_chain(cert,private)
    with httpx.Client(verify=ctx,trust_env=False,follow_redirects=False,timeout=8) as client:
        response=client.post(cfg['url']+path,content=encoded,headers=headers)
        response.raise_for_status();return response.json()
