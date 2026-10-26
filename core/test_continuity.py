import json
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch
from core.continuity import SharedStore


class ContinuityTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name)
        self.hub=SharedStore(self.root/'hub.db');self.pc=SharedStore(self.root/'pc.db');self.phone=SharedStore(self.root/'phone.db')
    def sync(self, replica):
        response=self.hub.sync({'device':{'id':replica.identity()['device'],'name':'fixture','platform':'test'},
                                'updates':[r for r in replica.pending() if not r['conflict']]})
        replica.apply(response);return response
    def test_one_profile_and_memory_reaches_multiple_devices(self):
        self.phone.put('memory','notes:hotel',{'value':'Golden Garden'},replica=True)
        first=self.sync(self.phone);second=self.sync(self.pc)
        self.assertEqual(first['profile'],second['profile'])
        self.assertEqual(self.pc.rows('memory')[0]['value'],{'value':'Golden Garden'})
        self.assertEqual(len(second['devices']),2)
        self.assertEqual(self.phone.pending(),[])
    def test_offline_updates_and_tombstones_do_not_resurrect_deleted_data(self):
        self.phone.put('task','todo',{'title':'Test','done':False},replica=True)
        self.phone.put('task','todo',{'title':'Test changed','done':False},replica=True)
        self.assertEqual(len(self.phone.pending()),1)
        self.sync(self.phone);self.sync(self.pc)
        self.pc.put('task','todo',None,replica=True);self.sync(self.pc);self.sync(self.phone)
        self.assertIsNone(self.phone.rows('task')[0]['value'])
    def test_retries_do_not_apply_the_same_mutation_twice(self):
        self.phone.put('memory','notes:a',{'value':'one'},replica=True)
        payload={'device':{'id':'phone'},'updates':self.phone.pending()}
        first=self.hub.sync(payload);second=self.hub.sync(payload)
        self.assertEqual(first['records'],second['records'])
        self.assertEqual(first['results'],second['results'])
    def test_id_cannot_be_reused_with_another_payload(self):
        self.phone.put('memory','notes:a',{'value':'original'},replica=True)
        body={'device':{'id':'phone'},'updates':self.phone.pending()}
        self.hub.sync(body)
        body['updates'][0]['value']={'value':'changed'}
        with self.assertRaises(ValueError):self.hub.sync(body)
        self.assertEqual(self.hub.rows()[0]['value'],{'value':'original'})
    def test_concurrent_edits_preserve_both_versions_until_explicit_choice(self):
        self.hub.put('memory','notes:a',{'value':'base'})
        self.sync(self.phone);self.sync(self.pc)
        self.phone.put('memory','notes:a',{'value':'phone edit'},replica=True)
        self.pc.put('memory','notes:a',{'value':'pc edit'},replica=True)
        self.sync(self.phone);result=self.sync(self.pc)
        self.assertTrue(self.pc.pending()[0]['conflict'])
        self.assertEqual(self.pc.rows()[0]['value'],{'value':'pc edit'})
        self.assertEqual(self.hub.rows()[0]['value'],{'value':'phone edit'})
        self.pc.resolve('memory','notes:a','local',result['records'][0]);self.sync(self.pc);self.sync(self.phone)
        self.assertEqual(self.phone.rows()[0]['value'],{'value':'pc edit'})
    def test_wrong_profile_or_malformed_batch_is_atomic(self):
        self.phone.put('memory','notes:a',{'value':'valid'},replica=True)
        body={'device':{'id':'phone'},'profile':'another-profile','updates':self.phone.pending()}
        with self.assertRaises(ValueError):self.hub.sync(body)
        self.assertEqual(self.hub.rows(),[])
        body.pop('profile');body['updates'].append({'id':'bad','base':0,'kind':'command','key':'launch','value':{'execute':'evil'}})
        with self.assertRaises(ValueError):self.hub.sync(body)
        self.assertEqual(self.hub.rows(),[])
    def test_conflict_can_keep_hub_version(self):
        self.hub.put('task','t',{'title':'base'});self.sync(self.phone)
        self.hub.put('task','t',{'title':'new hub'});self.phone.put('task','t',{'title':'offline'},replica=True)
        result=self.sync(self.phone);self.phone.resolve('task','t','hub',result['records'][0])
        self.assertEqual(self.phone.pending(),[])
        self.assertEqual(self.phone.rows()[0]['value'],{'title':'new hub'})
    def test_recent_context_does_not_execute_history(self):
        for role in ('user','jarvis'):
            self.hub.put('turn',role,{'role':role,'text':'delete everything','at':time.time(),'device':'test'})
        from core import continuity_runtime as runtime
        with patch.object(runtime,'store',self.hub),patch.object(runtime,'config',return_value={'enabled':True}):
            context=runtime.context()
        self.assertIn('Never repeat an action',context)
        self.assertIn('delete everything',context)

    def test_pc_memory_bridge_merges_shared_data_without_exporting_device_settings(self):
        from core import continuity_runtime as runtime
        from memory import memory_manager as memory
        path=self.root/'memory.json'
        path.write_text(json.dumps({'identity':{'name':{'value':'Pessoa'}},'monitors':{'private_camera':'not shared'}}),encoding='utf-8')
        cfg={'enabled':True,'role':'hub'}
        with patch.object(runtime,'store',self.hub),patch.object(runtime,'config',return_value=cfg),patch.object(memory,'MEMORY_PATH',path):
            runtime.bridge_memory()
            self.assertEqual([r['key'] for r in self.hub.rows('memory')],['identity:name'])
            self.hub.put('memory','notes:phone_fact',{'key':'phone_fact','category':'notes','value':'Fato do celular'})
            runtime.bridge_memory()
            self.assertEqual(memory.load_memory()['notes']['phone_fact']['value'],'Fato do celular')
            self.assertEqual(memory.load_memory()['monitors']['private_camera'],'not shared')
            before=self.hub.rows()
            runtime.bridge_memory();self.assertEqual(before,self.hub.rows())
            self.hub.put('memory','notes:phone_fact',None);runtime.bridge_memory()
            self.assertNotIn('phone_fact',memory.load_memory()['notes'])


class ContinuityApiTests(unittest.TestCase):
    def test_endpoint_requires_pairing_and_hub_role(self):
        from fastapi.testclient import TestClient
        from dashboard.server import DashboardServer
        from core import continuity_runtime as runtime
        with tempfile.TemporaryDirectory() as temp:
            hub=SharedStore(Path(temp)/'hub.db')
            server=DashboardServer(device_store_path=Path(temp)/'devices.json')
            server._tokens['fixture']=time.time()
            client=TestClient(server.app)
            body={'device':{'id':'test'},'updates':[]}
            self.assertEqual(client.post('/api/continuity/sync',json=body).status_code,401)
            with patch('core.continuity.store',hub),patch.object(runtime,'bridge_memory'),patch.object(runtime,'config',return_value={'enabled':True,'role':'hub'}):
                response=client.post('/api/continuity/sync',json=body,headers={'Authorization':'Bearer fixture'})
                self.assertEqual(response.status_code,200)
                self.assertEqual(response.headers['cache-control'],'no-store')
            with patch.object(runtime,'config',return_value={'enabled':True,'role':'replica'}):
                self.assertEqual(client.post('/api/continuity/sync',json=body,headers={'Authorization':'Bearer fixture'}).status_code,409)


if __name__=='__main__':unittest.main()
