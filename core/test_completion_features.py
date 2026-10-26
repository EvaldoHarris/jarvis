import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

from core import workbooks, google_workspace as google, task_plan
from core import task_control
from actions import window_layout as layout
from actions import google_workspace as google_action


class WorkbookTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name)
    def test_create_and_update_verified_copy_preserve_original_and_literals(self):
        source=self.root/'original.xlsx'
        first=workbooks.create(['Nome','Valor'],[['=1+1',123.45]],str(source))
        before=source.read_bytes()
        observed=workbooks.inspect(str(source))
        self.assertEqual(observed['rows'][1],['=1+1',123.45])
        from openpyxl import load_workbook
        book=load_workbook(source);self.assertEqual(book.active['A2'].data_type,'s');book.close()
        copy=self.root/'copy.xlsx'
        workbooks.update(str(source),first['sha256'],{'B2':99.5},str(copy))
        self.assertEqual(source.read_bytes(),before)
        self.assertEqual(workbooks.inspect(str(copy))['rows'][1][1],99.5)
    def test_stale_hash_overwrite_and_nonfinite_values_refused(self):
        source=self.root/'original.xlsx'
        first=workbooks.create(['A'],[[1]],str(source))
        with self.assertRaises(ValueError):workbooks.update(str(source),'stale',{'A2':2},str(self.root/'new.xlsx'))
        with self.assertRaises(ValueError):workbooks.update(str(source),first['sha256'],{'A2':2},str(source))
        with self.assertRaises(FileExistsError):workbooks.create(['A'],[[2]],str(source))
        with self.assertRaises(ValueError):workbooks.create(['A'],[[float('nan')]],str(self.root/'bad.xlsx'))
    def test_document_comparison_exports_verified_xlsx(self):
        from core.document_workflow import compare_amounts,save_comparison
        a=self.root/'A.txt';b=self.root/'B.txt'
        a.write_text('Total R$ 100,00');b.write_text('Total R$ 200,00')
        output=self.root/'comparison.xlsx'
        result=save_comparison(compare_amounts([str(a),str(b)]),str(output))
        self.assertTrue(result['verified'])
        data=workbooks.inspect(str(output))
        self.assertEqual(data['rows'][1][4],100)


class OcrTests(unittest.TestCase):
    @unittest.skipUnless(__import__('platform').system()=='Windows','Windows OCR backend')
    def test_real_local_image_and_scanned_pdf_transcription(self):
        from PIL import Image,ImageDraw,ImageFont
        from core.document_workflow import read_document
        from core.local_ocr import read_ocr
        with tempfile.TemporaryDirectory() as folder:
            image=Image.new('RGB',(1200,240),'white')
            ImageDraw.Draw(image).text((30,40),'TOTAL R$ 1234,56',font=ImageFont.truetype('C:/Windows/Fonts/arial.ttf',64),fill='black')
            path=Path(folder)/'scanned.pdf';image.save(path,'PDF',resolution=150)
            result=read_ocr(str(path),count=1)
            self.assertIn('1234,56',result['segments'][0]['text'])
            extracted=read_document(path,use_ocr=True)
            self.assertIn('1234,56',extracted['segments'][0]['text'])
            self.assertTrue(any('OCR transcription' in warning for warning in extracted['warnings']))


class GoogleTests(unittest.TestCase):
    def test_no_mail_sent_before_real_confirmation(self):
        captured={}
        def gate(key,title,detail,run):captured.update(run=run,detail=detail);return '[CONFIRMATION_PENDING]'
        with patch.object(google,'status',return_value={'token_saved':True}),patch.object(google_action.confirm,'request',side_effect=gate),patch.object(google,'send_email',return_value={'sent':True,'id':'actual'}) as send:
            result=google_action.google_workspace({'action':'send_email','to':'test@example.com','subject':'Revisar','body':'Texto concreto'})
            self.assertIn('CONFIRMATION_PENDING',result);send.assert_not_called()
            self.assertIn('Texto concreto',captured['detail'])
            captured['run']();send.assert_called_once_with('test@example.com','Revisar','Texto concreto')
    def test_event_confirmation_and_timezone_validation(self):
        with patch.object(google,'status',return_value={'token_saved':True}),patch.object(google_action.confirm,'request',return_value='pending') as gate,patch.object(google,'create_event') as create:
            result=google_action.google_workspace({'action':'create_event','title':'Reuniao','start':'2026-10-22T10:00:00-03:00','end':'2026-10-22T11:00:00-03:00'})
            self.assertEqual(result,'pending');gate.assert_called_once();create.assert_not_called()
        with self.assertRaises(ValueError):google.aware('2026-10-22T10:00:00')
    def test_mail_header_injection_and_external_oauth_endpoints_rejected(self):
        with self.assertRaises(ValueError):google.send_email('a@example.com\nBcc:evil@example.com','a','b')
        with tempfile.TemporaryDirectory() as temp:
            path=Path(temp)/'client.json';path.write_text(json.dumps({'installed':{'client_id':'a','client_secret':'b','auth_uri':'https://evil.test','token_uri':'https://evil.test'}}))
            with self.assertRaises(ValueError):google.import_client(path)
    def test_read_apis_use_actual_response_data(self):
        api=Mock()
        api.events.return_value.list.return_value.execute.return_value={'items':[{'id':'event','summary':'Real event','start':{'dateTime':'2026-10-22T10:00:00-03:00'}}]}
        with patch.object(google,'service',return_value=api):data=google.list_events()
        self.assertEqual(data['events'][0]['title'],'Real event')
    @unittest.skipUnless(__import__('platform').system()=='Windows','Windows DPAPI token backend')
    def test_dpapi_roundtrip_does_not_store_plain_token(self):
        import win32crypt
        with tempfile.TemporaryDirectory() as temp,patch.object(google,'folder',return_value=Path(temp)):
            google.save_token(SimpleNamespace(to_json=lambda:'{"token":"FAKE-TEST-TOKEN"}'))
            raw=(Path(temp)/'google_token.bin').read_bytes()
            self.assertNotIn(b'FAKE-TEST-TOKEN',raw)
            self.assertIn('FAKE-TEST-TOKEN',win32crypt.CryptUnprotectData(raw,None,None,None,0)[1].decode())
    def test_disconnected_account_never_reaches_send_confirmation(self):
        with patch.object(google,'status',return_value={'token_saved':False}),patch.object(google_action.confirm,'request') as gate:
            reply=google_action.google_workspace({'action':'send_email','to':'test@example.com','subject':'x','body':'x'})
        self.assertIn('status=unverified',reply);gate.assert_not_called()
    def test_send_uses_authenticated_sender_and_does_not_retry(self):
        import base64
        from email import message_from_bytes
        api=Mock()
        api.users.return_value.getProfile.return_value.execute.return_value={'emailAddress':'owner@example.com'}
        api.users.return_value.messages.return_value.send.return_value.execute.return_value={'id':'sent-real-id'}
        with patch.object(google,'service',return_value=api):reply=google.send_email('recipient@example.com','Subject','Body')
        request=api.users.return_value.messages.return_value.send.call_args.kwargs
        message=message_from_bytes(base64.urlsafe_b64decode(request['body']['raw']))
        self.assertEqual(message['From'],'owner@example.com');self.assertEqual(message['To'],'recipient@example.com')
        api.users.return_value.messages.return_value.send.return_value.execute.assert_called_once_with(num_retries=0)
        self.assertEqual(reply['id'],'sent-real-id')


class WindowLayoutTests(unittest.TestCase):
    def test_negative_monitor_rectangles_and_asymmetric_workareas(self):
        self.assertEqual(layout.layout_rect([-1920,-200,0,880],'right'),[-960,-200,0,880])
        self.assertEqual(layout.layout_rect([3440,670,4800,1390],'left'),[3440,670,4120,1390])
    def test_observed_window_only_and_guarded_placement(self):
        window=Mock(handle=7);window.process_id.return_value=123;window.window_text.return_value='Editor'
        areas=[{'id':2,'work':[3440,670,4800,1390],'primary':False}]
        with patch.object(layout,'windows',return_value=[window]),patch.object(layout,'monitors',return_value=areas),patch.object(layout,'bounds',return_value=[10,10,200,200]),patch.object(layout,'place',return_value=[3440,670,4120,1390]) as place:
            layout.window_layout({'action':'list'});key=next(iter(layout._observed[1]))
            result=layout.window_layout({'action':'place','window_id':key,'monitor':2,'position':'left'})
            self.assertIn('status=done',result);place.assert_called_once_with(window,[3440,670,4120,1390])
            layout.window_layout({'action':'place','window_id':key,'monitor':2,'position':'left'})
            self.assertEqual(place.call_count,1)


class TaskApiTests(unittest.TestCase):
    def setUp(self):
        from dashboard.server import DashboardServer
        from fastapi.testclient import TestClient
        import time
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.patch=patch.object(task_plan,'_path',return_value=Path(self.temp.name)/'plans.db');self.patch.start();self.addCleanup(self.patch.stop)
        self.plan=task_plan.TaskPlans().update({'action':'create','objective':'Painel','steps':['Primeira','Segunda']})
        self.server=DashboardServer();self.server._tokens['task-test']=time.time();self.client=TestClient(self.server.app)
        self.headers={'Authorization':'Bearer task-test'}
    def test_auth_redaction_and_revision_checked_pause_resume_cancel(self):
        self.assertEqual(self.client.get('/api/tasks').status_code,401)
        self.assertEqual(self.client.post('/api/tasks',json={'action':'cancel'}).status_code,401)
        data=self.client.get('/api/tasks',headers=self.headers).json()['plan'];self.assertEqual(data['completed'],0)
        self.assertNotIn('receipt_id',str(data))
        result=self.client.post('/api/tasks',headers=self.headers,json={'action':'pause','plan_id':data['id'],'revision':data['revision']})
        self.assertEqual(result.status_code,200);self.assertEqual(result.json()['plan']['state'],'paused')
        stale=self.client.post('/api/tasks',headers=self.headers,json={'action':'resume','plan_id':data['id'],'revision':data['revision']})
        self.assertEqual(stale.status_code,409)
        current=result.json()['plan']
        resumed=self.client.post('/api/tasks',headers=self.headers,json={'action':'resume','plan_id':current['id'],'revision':current['revision']})
        self.assertEqual(resumed.json()['plan']['state'],'active')
        current=resumed.json()['plan']
        ended=self.client.post('/api/tasks',headers=self.headers,json={'action':'cancel','plan_id':current['id'],'revision':current['revision']})
        self.assertEqual(ended.json()['plan']['state'],'cancelled')


if __name__=='__main__':unittest.main()
