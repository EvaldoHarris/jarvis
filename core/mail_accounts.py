"""Gmail and Hotmail/Outlook over IMAP/SMTP, without any OAuth client .json file.

Both providers use browser sign-in (OAuth 2 with PKCE); IMAP/SMTP then use
XOAUTH2. No password is ever typed into Jarvis. Tokens are stored DPAPI-encrypted in config/mail_accounts.bin.
"""
import email
import imaplib
import json
import smtplib
import threading
import time
from email.header import decode_header, make_header
from email.message import EmailMessage
from email.utils import parseaddr

import requests

from core.task_plan import _path

PROVIDERS = {
    'gmail': {'imap': ('imap.gmail.com', 993), 'smtp': ('smtp.gmail.com', 587)},
    'outlook': {'imap': ('outlook.office365.com', 993), 'smtp': ('smtp-mail.outlook.com', 587)},
}
MS_AUTHORITY = 'https://login.microsoftonline.com/consumers/oauth2/v2.0'
MS_SCOPES = 'offline_access https://outlook.office.com/IMAP.AccessAsUser.All https://outlook.office.com/SMTP.Send'
_lock = threading.Lock()


def _file():
    return _path().parent.parent / 'config' / 'mail_accounts.bin'


def _load():
    target = _file()
    if not target.exists():
        return {}
    import win32crypt
    _, raw = win32crypt.CryptUnprotectData(target.read_bytes(), None, None, None, 0)
    return json.loads(raw)


def _save(accounts):
    import win32crypt
    target = _file()
    target.parent.mkdir(parents=True, exist_ok=True)
    data = win32crypt.CryptProtectData(json.dumps(accounts).encode(), 'Jarvis mail accounts', None, None, None, 0)
    temp = target.with_suffix('.tmp')
    temp.write_bytes(data)
    temp.replace(target)


def provider_for(address):
    domain = address.rsplit('@', 1)[-1].lower()
    if domain in ('gmail.com', 'googlemail.com'):
        return 'gmail'
    if domain in ('hotmail.com', 'outlook.com', 'live.com', 'msn.com') or domain.startswith(('hotmail.', 'outlook.', 'live.')):
        return 'outlook'
    raise ValueError('Use um endereco Gmail, Hotmail, Outlook ou Live')


def _check_address(address):
    address = (address or '').strip().lower()
    if parseaddr(address)[1] != address or '@' not in address:
        raise ValueError('Endereco de email invalido')
    return address


def status():
    with _lock:
        accounts = _load()
    return {'accounts': [{'address': a, 'provider': v['provider']} for a, v in accounts.items()],
            'note': 'Saved credentials are not a live connectivity test.'}


def remove(address):
    with _lock:
        accounts = _load()
        accounts.pop(_check_address(address), None)
        _save(accounts)


# ── Browser login (OAuth 2 + PKCE, loopback redirect) ─────────────────────────
# The app's own OAuth client IDs live in core/oauth_clients.py, so users only
# click "Entrar" and sign in on the official Google/Microsoft page.
OAUTH = {
    'gmail': {'auth': 'https://accounts.google.com/o/oauth2/v2/auth', 'token': 'https://oauth2.googleapis.com/token',
              'scope': 'openid email https://mail.google.com/', 'extra': {'access_type': 'offline', 'prompt': 'consent'}},
    'outlook': {'auth': f'{MS_AUTHORITY}/authorize', 'token': f'{MS_AUTHORITY}/token',
                'scope': MS_SCOPES + ' openid email', 'extra': {'prompt': 'select_account'}},
}


def _client(provider):
    from core import oauth_clients
    return oauth_clients.client(provider)


def _token_request(provider, data):
    client_id, secret = _client(provider)
    data = dict(data, client_id=client_id)
    if secret:
        data['client_secret'] = secret
    return requests.post(OAUTH[provider]['token'], data=data, timeout=20).json()


def _identity(id_token):
    import base64
    payload = id_token.split('.')[1]
    claims = json.loads(base64.urlsafe_b64decode(payload + '=' * (-len(payload) % 4)))
    address = claims.get('email') or claims.get('preferred_username') or ''
    return _check_address(address)


def login(provider, timeout=180):
    """Opens the official sign-in page in the browser and saves the account."""
    import base64, hashlib, secrets, urllib.parse, webbrowser
    from http.server import BaseHTTPRequestHandler, HTTPServer
    if provider not in OAUTH:
        raise ValueError('Provedor desconhecido')
    client_id, _ = _client(provider)
    verifier = secrets.token_urlsafe(64)
    state = secrets.token_urlsafe(24)
    result = {}

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            query = dict(urllib.parse.parse_qsl(urllib.parse.urlparse(self.path).query))
            if query.get('state') == state:
                result.update(query)
            self.send_response(200)
            self.send_header('Content-Type', 'text/html; charset=utf-8')
            self.end_headers()
            self.wfile.write('<h2>Pronto! Pode fechar esta aba e voltar ao Jarvis.</h2>'.encode())

        def log_message(self, *args):
            pass

    server = HTTPServer(('127.0.0.1', 0), Handler)
    server.timeout = 2
    redirect = f'http://localhost:{server.server_port}/'
    conf = OAUTH[provider]
    params = {'client_id': client_id, 'response_type': 'code', 'redirect_uri': redirect, 'scope': conf['scope'],
              'state': state, 'code_challenge_method': 'S256',
              'code_challenge': base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(b'=').decode(),
              **conf['extra']}
    webbrowser.open(conf['auth'] + '?' + urllib.parse.urlencode(params))
    deadline = time.time() + timeout
    try:
        while not result and time.time() < deadline:
            server.handle_request()
    finally:
        server.server_close()
    if 'code' not in result:
        raise ValueError(result.get('error_description') or result.get('error') or 'Login nao concluido a tempo')
    data = _token_request(provider, {'grant_type': 'authorization_code', 'code': result['code'],
                                     'redirect_uri': redirect, 'code_verifier': verifier})
    if 'access_token' not in data or 'refresh_token' not in data:
        raise ValueError(data.get('error_description', 'Autorizacao recusada'))
    address = _identity(data['id_token'])
    with _lock:
        accounts = _load()
        accounts[address] = {'provider': provider_for(address) if provider == 'outlook' else 'gmail',
                             'refresh_token': data['refresh_token'], 'access_token': data['access_token'],
                             'expires': time.time() + data.get('expires_in', 3600) - 60}
        _save(accounts)
    return {'connected': address}


def _access_token(address):
    with _lock:
        accounts = _load()
        entry = accounts[address]
        if entry.get('expires', 0) > time.time():
            return entry['access_token']
        data = _token_request(entry['provider'], {'grant_type': 'refresh_token', 'refresh_token': entry['refresh_token']})
        if 'access_token' not in data:
            raise ValueError('Autorizacao expirou; entre de novo na conta pelo painel de email')
        entry.update(access_token=data['access_token'], expires=time.time() + data.get('expires_in', 3600) - 60,
                     refresh_token=data.get('refresh_token', entry['refresh_token']))
        _save(accounts)
        return entry['access_token']


# ── Shared IMAP/SMTP operations ───────────────────────────────────────────────
def _account(address=None):
    with _lock:
        accounts = {k: v for k, v in _load().items() if not k.startswith('_')}
    if not accounts:
        raise ValueError('Nenhuma conta de email conectada. Use o painel de email nas configuracoes do PC.')
    if not address:
        if len(accounts) > 1:
            raise ValueError('Mais de uma conta conectada; informe qual: ' + ', '.join(accounts))
        address = next(iter(accounts))
    address = _check_address(address)
    if address not in accounts:
        raise ValueError(f'Conta {address} nao conectada')
    return address, accounts[address]


def _xoauth(address, token):
    return f'user={address}\x01auth=Bearer {token}\x01\x01'


def _imap(address, entry):
    imap = imaplib.IMAP4_SSL(*PROVIDERS[entry['provider']]['imap'], timeout=30)
    auth = _xoauth(address, _access_token(address)).encode()
    imap.authenticate('XOAUTH2', lambda _: auth)
    return imap


def _text(value):
    try: return str(make_header(decode_header(value or '')))
    except Exception: return value or ''


def list_emails(query='', count=10, account=None):
    address, entry = _account(account)
    imap = _imap(address, entry)
    try:
        imap.select('INBOX', readonly=True)
        if query:
            if entry['provider'] == 'gmail':
                imap.literal = query[:500].encode()
                _, ids = imap.uid('SEARCH', 'CHARSET', 'UTF-8', 'X-GM-RAW')
            else:
                imap.literal = query[:500].encode()
                _, ids = imap.uid('SEARCH', 'CHARSET', 'UTF-8', 'TEXT')
        else:
            _, ids = imap.uid('SEARCH', None, 'ALL')
        uids = ids[0].split()
        chosen = uids[-max(1, min(20, count)):][::-1]
        rows = []
        for uid in chosen:
            _, data = imap.uid('FETCH', uid, '(BODY.PEEK[HEADER.FIELDS (SUBJECT FROM DATE)])')
            headers = email.message_from_bytes(data[0][1])
            rows.append({'id': uid.decode(), 'subject': _text(headers['Subject']), 'from': _text(headers['From']), 'date': headers['Date'] or ''})
        return {'account': address, 'messages': rows, 'has_more': len(uids) > len(chosen)}
    finally:
        imap.logout()


def read_email(message_id, account=None):
    address, entry = _account(account)
    if not str(message_id).isdigit():
        raise ValueError('message_id invalido')
    imap = _imap(address, entry)
    try:
        imap.select('INBOX', readonly=True)
        _, data = imap.uid('FETCH', str(message_id), '(BODY.PEEK[])')
        if not data or data[0] is None:
            raise ValueError('Mensagem nao encontrada')
        message = email.message_from_bytes(data[0][1])
    finally:
        imap.logout()
    texts = [p.get_payload(decode=True).decode(p.get_content_charset() or 'utf-8', errors='replace')
             for p in message.walk()
             if p.get_content_type() == 'text/plain' and not p.get_filename() and p.get_payload(decode=True)]
    body = '\n'.join(texts)
    return {'account': address, 'id': str(message_id), 'subject': _text(message['Subject']), 'from': _text(message['From']),
            'to': _text(message['To']), 'date': message['Date'] or '', 'text': body[:20000], 'truncated': len(body) > 20000,
            'note': 'Plain-text body only; attachments are not read automatically.'}


def send_email(to, subject, body, account=None):
    if not isinstance(to, str) or '\n' in to or '\r' in to or parseaddr(to)[1] != to or '@' not in to:
        raise ValueError('Provide one explicit recipient email address')
    if not isinstance(subject, str) or not subject.strip() or len(subject) > 300 or '\n' in subject or '\r' in subject:
        raise ValueError('Provide a plain subject, at most 300 characters')
    if not isinstance(body, str) or not body.strip() or len(body) > 20000:
        raise ValueError('Provide a message body, at most 20000 characters')
    address, entry = _account(account)
    message = EmailMessage()
    message['From'], message['To'], message['Subject'] = address, to, subject
    message.set_content(body)
    with smtplib.SMTP(*PROVIDERS[entry['provider']]['smtp'], timeout=30) as smtp:
        smtp.starttls()
        auth = _xoauth(address, _access_token(address))
        smtp.ehlo()
        smtp.auth('XOAUTH2', lambda challenge=None: auth, initial_response_ok=True)
        smtp.send_message(message)
    return {'account': address, 'sent': True}
