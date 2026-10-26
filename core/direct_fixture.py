"""Emulator-only TLS integration fixture. Never imported by the application.

Run python -m core.direct_fixture; adb reverse tcp:18888 tcp:18888 and
tcp:19443 tcp:19443. All sockets bind loopback, all keys/data are temporary.
"""
import asyncio
import tempfile
from pathlib import Path
import uvicorn
from fastapi import FastAPI, Request
from core.direct_secure import Authority,create_app
from core.continuity import SharedStore


async def run():
    with tempfile.TemporaryDirectory(prefix='jarvis-direct-fixture-') as temp:
        root=Path(temp);ca=Authority(root/'tls',protect=lambda x:x,unprotect=lambda x:x)
        ca.initialize(['127.0.0.1'])
        hub=SharedStore(root/'data.db')
        hub.put('memory','notes:tls_fixture',{'key':'tls_fixture','category':'notes','value':'Canal TLS verificado'})
        enrollment=FastAPI()
        @enrollment.get('/fixture-ticket')
        async def ticket():return {'ticket':ca.ticket('http://127.0.0.1:18888/api/direct/enroll','https://127.0.0.1:19443')}
        @enrollment.post('/api/direct/enroll')
        async def enroll(req: Request):return ca.enroll(await req.json())
        @enrollment.post('/fixture-revoke')
        async def revoke(req: Request):ca.revoke((await req.json())['id']);return {'ok':True}
        secure=uvicorn.Config(create_app(ca,hub),host='127.0.0.1',port=19443,log_level='warning',access_log=False)
        ca.load_tls(secure)
        plain=uvicorn.Config(enrollment,host='127.0.0.1',port=18888,log_level='warning',access_log=False)
        await asyncio.gather(uvicorn.Server(plain).serve(),uvicorn.Server(secure).serve())


if __name__=='__main__':asyncio.run(run())
