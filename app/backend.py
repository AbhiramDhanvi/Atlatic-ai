"""User-scoped Supabase REST access. Never uses a service-role key."""
from dataclasses import dataclass
import httpx
from fastapi import Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from app.config import settings

@dataclass(frozen=True)
class Principal:
    subject: str
    token: str
    email: str = ''

def request(method, path, token='', **kwargs):
    s = settings()
    if not s.supabase_url or not s.supabase_publishable_key:
        raise HTTPException(503, 'Authentication and database are not configured.')
    headers = {'apikey': s.supabase_publishable_key}
    if token:
        headers['Authorization'] = 'Bearer ' + token
    headers.update(kwargs.pop('headers', {}))
    try:
        r = httpx.request(method, s.supabase_url.rstrip('/') + path,
                          headers=headers, timeout=45, **kwargs)
    except httpx.HTTPError as exc:
        raise HTTPException(503, 'Database service is temporarily unavailable.') from exc
    if r.is_error:
        if r.status_code in (401, 403):
            raise HTTPException(r.status_code, 'Session expired or access denied.')
        raise HTTPException(502, 'Database operation failed. Please retry.')
    return r.json() if r.content else None

bearer = HTTPBearer(auto_error=False)

def principal(credentials: HTTPAuthorizationCredentials | None = Depends(bearer)):
    if not credentials or credentials.scheme.lower() != 'bearer':
        raise HTTPException(401, 'Sign in to continue.')
    user = request('GET', '/auth/v1/user', credentials.credentials)
    if not user.get('id'):
        raise HTTPException(401, 'Invalid session.')
    return Principal(user['id'], credentials.credentials, user.get('email', ''))

def rest(p, method, table, **kwargs):
    headers = {'Prefer': 'return=representation'}
    headers.update(kwargs.pop('headers', {}))
    return request(method, '/rest/v1/' + table, p.token, headers=headers, **kwargs)

def rpc(p, name, payload=None):
    return rest(p, 'POST', 'rpc/' + name, json=payload or {})

def audit(p, action, detail=None):
    rest(p, 'POST', 'audit_events', json={
        'owner_id': p.subject, 'action': action, 'detail': detail or {}})

def require_admin(p):
    if not rpc(p, 'is_atlatic_admin'):
        raise HTTPException(403, 'Administrator access required.')
