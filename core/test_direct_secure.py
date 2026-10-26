import asyncio
import hashlib
import json
import secrets
import ssl
import tempfile
import threading
import time
import unittest
import uuid
from pathlib import Path

import httpx
import uvicorn
from cryptography import x509
from cryptography.hazmat.primitives import hashes,serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from core.direct_secure import Authority,b64,un64,create_app
from core.continuity import SharedStore


class DirectSecureTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name)
        self.ca=Authority(self.root/'tls',protect=lambda v:v,unprotect=lambda v:v)
        self.ca.initialize(['127.0.0.1'])
        self.private=ec.generate_private_key(ec.SECP256R1());self.ident=str(uuid.uuid4())
    def enroll(self):
        import base64
        ticket=self.ca.ticket('http://127.0.0.1:8000/api/direct/enroll','https://127.0.0.1:9443')
        meta=json.loads(__import__('zlib').decompress(base64.urlsafe_b64decode(ticket.split(':',2)[2])));key=un64(meta['secret'])
        public=self.private.public_key().public_bytes(serialization.Encoding.DER,serialization.PublicFormat.SubjectPublicKeyInfo)
        proof=self.private.sign(('jarvis-enroll\n'+self.ident+'\n'+hashlib.sha256(public).hexdigest()).encode(),ec.ECDSA(hashes.SHA256()))
        payload=json.dumps({'id':self.ident,'name':'fixture','public':b64(public),'proof':b64(proof)}).encode()
        nonce=secrets.token_bytes(12)
        request={'ticket':hashlib.sha256(key).hexdigest(),'nonce':b64(nonce),'data':b64(AESGCM(key).encrypt(nonce,payload,b'jarvis-enroll-request-v1'))}
        reply=self.ca.enroll(request)
        return json.loads(AESGCM(key).decrypt(un64(reply['nonce']),un64(reply['data']),b'jarvis-enroll-response-v1')),request
    def headers(self,body,path='/api/continuity/sync',stamp=None):
        timestamp=str(int(time.time()) if stamp is None else stamp);nonce=secrets.token_hex(16)
        data='\n'.join((self.ident,'POST',path,timestamp,nonce,hashlib.sha256(body).hexdigest())).encode()
        return {'x-jarvis-device':self.ident,'x-jarvis-time':timestamp,'x-jarvis-nonce':nonce,
                'x-jarvis-signature':b64(self.private.sign(data,ec.ECDSA(hashes.SHA256())))}
    def test_listener_starts_without_console_under_pythonw(self):
        import sys
        from unittest.mock import patch,AsyncMock
        from core import direct_secure
        with patch.object(direct_secure,'authority',self.ca),patch.object(direct_secure,'settings',return_value={'enabled':True,'host':'127.0.0.1','port':19443}),patch.object(uvicorn.Server,'serve',new_callable=AsyncMock) as serve,patch.object(sys,'stdout',None),patch.object(sys,'stderr',None):
            asyncio.run(direct_secure.serve())
        serve.assert_awaited_once()

    def test_compact_qr_rejects_substituted_ca_before_pairing(self):
        from unittest.mock import patch
        from core import direct_client
        from core.direct_secure import compact_invitation
        qr=compact_invitation(self.ca.ticket('http://127.0.0.1:8000/api/direct/enroll','https://127.0.0.1:9443'))
        response=httpx.Response(200,json={'ca':'substituted'},request=httpx.Request('GET','http://127.0.0.1:8000/api/direct/ca'))
        with patch.object(direct_client,'_read',side_effect=FileNotFoundError),patch.object(direct_client.httpx,'get',return_value=response),patch.object(direct_client.httpx,'post') as post:
            with self.assertRaisesRegex(ValueError,'não corresponde'):
                direct_client.enroll(qr,'fixture')
            post.assert_not_called()

    def test_pairing_is_one_use_but_lost_response_can_be_retried(self):
        result,request=self.enroll()
        self.assertEqual(result['id'],self.ident)
        self.assertEqual(self.ca.enroll(request),self.ca.enroll(request))
        changed={**request,'nonce':b64(secrets.token_bytes(12))}
        with self.assertRaises(ValueError):self.ca.enroll(changed)
        self.assertEqual(len(self.ca.devices()),1)
    def test_signed_request_replay_body_tampering_and_revocation(self):
        self.enroll();body=b'{"updates":[]}'
        headers=self.headers(body)
        self.assertEqual(self.ca.authorize('POST','/api/continuity/sync',headers,body),self.ident)
        with self.assertRaises(ValueError):self.ca.authorize('POST','/api/continuity/sync',headers,body)
        with self.assertRaises(Exception):self.ca.authorize('POST','/api/continuity/sync',self.headers(body),b'tampered')
        with self.assertRaises(ValueError):self.ca.authorize('POST','/api/continuity/sync',self.headers(body,stamp=int(time.time())-100),body)
        self.ca.revoke(self.ident)
        with self.assertRaises(ValueError):self.ca.authorize('POST','/api/continuity/sync',self.headers(body),body)
    def test_new_public_address_requires_preparing_certificate_before_invitation(self):
        before=(self.ca.root/'server.pem').read_bytes()
        with self.assertRaises(ValueError):self.ca.ticket('http://127.0.0.1:8000/api/direct/enroll','https://203.0.113.1:9443')
        self.assertEqual(before,(self.ca.root/'server.pem').read_bytes())
    def test_real_tls_requires_client_certificate_and_rejects_wrong_server_trust(self):
        result,_=self.enroll()
        cert=self.root/'client.pem';cert.write_text(result['cert'])
        key=self.root/'client.key';key.write_bytes(self.private.private_bytes(serialization.Encoding.PEM,serialization.PrivateFormat.PKCS8,serialization.NoEncryption()))
        import socket
        listener=socket.socket();listener.bind(('127.0.0.1',0));port=listener.getsockname()[1]
        hub=SharedStore(self.root/'hub.db')
        cfg=uvicorn.Config(create_app(self.ca,hub),host='127.0.0.1',port=port,log_level='critical',access_log=False)
        self.ca.load_tls(cfg)
        self.assertFalse(Path(cfg.ssl_keyfile).exists())
        server=uvicorn.Server(cfg)
        thread=threading.Thread(target=lambda:asyncio.run(server.serve(sockets=[listener])),daemon=True);thread.start()
        try:
            deadline=time.time()+5
            while not server.started and thread.is_alive() and time.time()<deadline:time.sleep(.02)
            self.assertTrue(server.started)
            plain=ssl.create_default_context(cafile=str(self.ca.root/'ca.pem'))
            with httpx.Client(verify=plain,trust_env=False,timeout=3) as client:
                with self.assertRaises(httpx.TransportError):client.post(f'https://127.0.0.1:{port}/api/continuity/sync',content=b'{}')
            trusted=ssl.create_default_context(cafile=str(self.ca.root/'ca.pem'));trusted.load_cert_chain(cert,key)
            payload=json.dumps({'device':{'id':self.ident,'name':'fixture'},'updates':[]}).encode()
            with httpx.Client(verify=trusted,trust_env=False,timeout=3) as client:
                response=client.post(f'https://127.0.0.1:{port}/api/continuity/sync',content=payload,headers=self.headers(payload))
                self.assertEqual(response.status_code,200,response.text)
                self.assertEqual(client.get(f'https://127.0.0.1:{port}/login').status_code,404)
                self.assertEqual(client.post(f'https://127.0.0.1:{port}/api/command',content=payload).status_code,404)
                with socket.create_connection(('127.0.0.1',port),timeout=3) as sock:
                    with self.assertRaises(ssl.SSLCertVerificationError):trusted.wrap_socket(sock,server_hostname='wrong-host.invalid')
                self.ca.revoke(self.ident)
                self.assertEqual(client.post(f'https://127.0.0.1:{port}/api/continuity/sync',content=payload,headers=self.headers(payload)).status_code,403)
            wrong=ssl.create_default_context();wrong.load_cert_chain(cert,key)
            with httpx.Client(verify=wrong,trust_env=False,timeout=3) as client:
                with self.assertRaises(httpx.TransportError):client.post(f'https://127.0.0.1:{port}/api/continuity/sync',content=payload,headers=self.headers(payload))
        finally:
            server.should_exit=True;thread.join(5);listener.close()
            self.assertFalse(thread.is_alive())


if __name__=='__main__':unittest.main()
