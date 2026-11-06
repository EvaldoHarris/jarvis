"""Jarvis's own OAuth app registrations, filled in ONCE by the developer.

Users never see or touch these: they just click "Entrar com Google/Microsoft".
Desktop OAuth clients are "public": Google's desktop secret is not treated as
confidential, and PKCE protects the login. Environment variables override.

Google  (console.cloud.google.com): enable Gmail API, OAuth client type
        "Desktop app". Scope used: https://mail.google.com/
Microsoft (entra.microsoft.com > App registrations): "Personal Microsoft
        accounts", platform "Mobile and desktop" with redirect http://localhost,
        API permissions IMAP.AccessAsUser.All + SMTP.Send + offline_access.
"""
import os

GOOGLE_CLIENT_ID = ''
GOOGLE_CLIENT_SECRET = ''
MICROSOFT_CLIENT_ID = ''


def client(provider):
    if provider == 'gmail':
        cid = os.environ.get('JARVIS_GOOGLE_CLIENT_ID', GOOGLE_CLIENT_ID)
        secret = os.environ.get('JARVIS_GOOGLE_CLIENT_SECRET', GOOGLE_CLIENT_SECRET)
    else:
        cid, secret = os.environ.get('JARVIS_MS_CLIENT_ID', MICROSOFT_CLIENT_ID), ''
    if not cid:
        raise ValueError('O login ainda nao foi habilitado nesta instalacao (preencha core/oauth_clients.py)')
    return cid, secret
