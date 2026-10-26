"""Google OAuth desktop integration. Tokens stay DPAPI-encrypted on Windows."""
import base64
import json
import threading
from datetime import datetime, timezone
from email.message import EmailMessage
from email.utils import parseaddr
from pathlib import Path

from core.task_plan import _path

SCOPES = ['https://www.googleapis.com/auth/gmail.readonly', 'https://www.googleapis.com/auth/gmail.send',
          'https://www.googleapis.com/auth/calendar.events']
_lock = threading.Lock()


def folder():
    return _path().parent.parent / 'config'


def status():
    return {'client_configured': (folder() / 'google_credentials.json').is_file(),
            'token_saved': (folder() / 'google_token.bin').is_file(),
            'note': 'A saved token is not a live connectivity test. Google consent is required before account access.'}


def save_token(credentials):
    import win32crypt
    target = folder() / 'google_token.bin'
    target.parent.mkdir(parents=True, exist_ok=True)
    data = win32crypt.CryptProtectData(credentials.to_json().encode(), 'Jarvis Google OAuth', None, None, None, 0)
    temp = target.with_suffix('.tmp')
    temp.write_bytes(data)
    temp.replace(target)


def import_client(path):
    source = Path(path).expanduser().resolve(strict=True)
    if source.stat().st_size > 50000:
        raise ValueError('OAuth client JSON is too large')
    data = json.loads(source.read_text(encoding='utf-8-sig'))
    client = data.get('installed', {})
    if (not client.get('client_id') or not client.get('client_secret') or
            client.get('auth_uri') not in ('https://accounts.google.com/o/oauth2/auth','https://accounts.google.com/o/oauth2/v2/auth') or
            client.get('token_uri') != 'https://oauth2.googleapis.com/token'):
        raise ValueError('Choose the official Google Desktop app OAuth client JSON')
    if status()['token_saved']:
        raise ValueError('A Google account is already paired; do not replace its client configuration silently')
    target = folder() / 'google_credentials.json'
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(data), encoding='utf-8')


def connect():
    from google_auth_oauthlib.flow import InstalledAppFlow
    with _lock:
        path = folder() / 'google_credentials.json'
        if not path.exists():
            raise ValueError('Import the Google Desktop OAuth client JSON in the PC settings first')
        flow = InstalledAppFlow.from_client_secrets_file(str(path), SCOPES)
        credentials = flow.run_local_server(host='127.0.0.1', port=0, open_browser=True, timeout_seconds=150)
        save_token(credentials)
    return {'authorized': True}


def credentials():
    import win32crypt
    from google.oauth2.credentials import Credentials
    from google.auth.transport.requests import Request
    target = folder() / 'google_token.bin'
    if not target.exists():
        raise ValueError('Google account is not connected. Use the Google button in the PC settings.')
    with _lock:
        _, raw = win32crypt.CryptUnprotectData(target.read_bytes(), None, None, None, 0)
        creds = Credentials.from_authorized_user_info(json.loads(raw), SCOPES)
        if not creds.valid:
            if not creds.refresh_token:
                raise ValueError('Google authorization expired; reconnect through PC settings')
            creds.refresh(Request())
            save_token(creds)
        return creds


def service(name):
    from googleapiclient.discovery import build
    return build(name, 'v1' if name == 'gmail' else 'v3', credentials=credentials(), cache_discovery=False)


def list_emails(query='', count=10):
    api = service('gmail')
    result = api.users().messages().list(userId='me', q=query[:500], maxResults=max(1,min(20,count))).execute(num_retries=0)
    rows = []
    for row in result.get('messages', []):
        message = api.users().messages().get(userId='me', id=row['id'], format='metadata', metadataHeaders=['Subject','From','Date']).execute(num_retries=0)
        headers = {h['name'].lower(): h['value'] for h in message.get('payload',{}).get('headers',[])}
        rows.append({'id':message['id'], 'subject':headers.get('subject',''), 'from':headers.get('from',''), 'date':headers.get('date',''), 'snippet':message.get('snippet','')})
    return {'messages':rows, 'has_more':bool(result.get('nextPageToken'))}


def read_email(message_id):
    message = service('gmail').users().messages().get(userId='me', id=message_id, format='full').execute(num_retries=0)
    texts = []
    def collect(part):
        if part.get('mimeType') == 'text/plain' and part.get('body',{}).get('data'):
            texts.append(base64.urlsafe_b64decode(part['body']['data']).decode('utf-8',errors='replace'))
        for child in part.get('parts',[]):
            collect(child)
    collect(message.get('payload',{}))
    body = '\n'.join(texts)
    return {'id':message['id'], 'headers':message.get('payload',{}).get('headers',[]), 'text':body[:20000],
            'snippet':message.get('snippet',''), 'truncated':len(body)>20000,
            'note':'Plain-text MIME body only; HTML-only messages may have only a snippet. Attachments are not read automatically.'}


def send_email(to, subject, body):
    if not isinstance(to,str) or '\n' in to or '\r' in to or parseaddr(to)[1] != to or '@' not in to:
        raise ValueError('Provide one explicit recipient email address')
    if not isinstance(subject,str) or not subject.strip() or len(subject)>300 or '\n' in subject or '\r' in subject:
        raise ValueError('Provide a plain subject, at most 300 characters')
    if not isinstance(body,str) or not body.strip() or len(body)>20000:
        raise ValueError('Provide a message body, at most 20000 characters')
    message = EmailMessage()
    api = service('gmail')
    message['From'] = api.users().getProfile(userId='me').execute(num_retries=0)['emailAddress']
    message['To'], message['Subject'] = to, subject
    message.set_content(body)
    encoded = base64.urlsafe_b64encode(message.as_bytes()).decode()
    result = api.users().messages().send(userId='me',body={'raw':encoded}).execute(num_retries=0)
    return {'id':result['id'], 'sent':True}


def aware(value):
    parsed = datetime.fromisoformat(value.replace('Z','+00:00'))
    if parsed.tzinfo is None:
        raise ValueError('Include the timezone offset in event dates, e.g. -03:00')
    return parsed


def list_events(start=None, end=None, count=10):
    minimum = aware(start).isoformat() if start else datetime.now(timezone.utc).isoformat()
    args = {'calendarId':'primary','timeMin':minimum,'singleEvents':True,'orderBy':'startTime','maxResults':max(1,min(50,count))}
    if end:
        args['timeMax']=aware(end).isoformat()
    result = service('calendar').events().list(**args).execute(num_retries=0)
    return {'events':[{'id':e['id'],'title':e.get('summary',''),'start':e.get('start'), 'end':e.get('end'),'link':e.get('htmlLink','')} for e in result.get('items',[])], 'has_more':bool(result.get('nextPageToken'))}


def create_event(title, start, end, description=''):
    if not title or len(title)>300 or len(description)>20000 or aware(end)<=aware(start):
        raise ValueError('Provide title and a valid start/end interval with timezone offsets')
    result = service('calendar').events().insert(calendarId='primary', sendUpdates='none', body={
        'summary':title,'description':description,'start':{'dateTime':aware(start).isoformat()},'end':{'dateTime':aware(end).isoformat()}}).execute(num_retries=0)
    return {'id':result['id'],'link':result.get('htmlLink',''),'created':True}
