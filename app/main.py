import time
import uuid
from pathlib import Path
from collections import defaultdict, deque
from urllib.parse import urlencode
from fastapi import FastAPI, Depends, HTTPException, Request, UploadFile, File
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from app.config import settings
from app.backend import Principal, principal, request as upstream, rest, rpc, audit, require_admin
from app.guardrails import classify_input
from app.graph import chat
from worker.ingest import ingest

BASE = Path(__file__).resolve().parent
app = FastAPI(title='Atlatic AI', docs_url='/api/docs', version='1.0.0')
app.mount('/static', StaticFiles(directory=BASE/'static'), name='static')

@app.middleware('http')
async def security_headers(request: Request, call_next):
    response = await call_next(request)
    response.headers['X-Content-Type-Options'] = 'nosniff'
    response.headers['Referrer-Policy'] = 'no-referrer'
    response.headers['X-Frame-Options'] = 'DENY'
    response.headers['Cache-Control'] = 'no-store'
    if request.url.path in ('/', '/auth/confirmed'):
        response.headers['Content-Security-Policy'] = "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; connect-src 'self'; frame-ancestors 'none'; base-uri 'self'; form-action 'self'"
    return response

@app.exception_handler(Exception)
async def unexpected_error(request, exc):
    # Do not export model prompts, bearer tokens, document contents or passwords.
    return JSONResponse({'detail':'An unexpected error occurred. Retry or contact the administrator.'}, status_code=500)

@app.get('/')
@app.get('/auth/confirmed', include_in_schema=False)
def home():
    return FileResponse(BASE/'templates/index.html')

@app.get('/health/live')
def live():
    return {'status':'alive'}

@app.get('/health/ready')
def ready():
    s=settings()
    if not s.gemini_api_key or not s.supabase_url or not s.supabase_publishable_key:
        raise HTTPException(503,'Server configuration is incomplete.')
    upstream('GET','/auth/v1/health')
    # Authenticated RLS and model access are verified by the opt-in live smoke suite.
    return {'status':'ready','checks':['configuration','supabase_auth'], 'model_access_checked':False}

@app.get('/api/config')
def config():
    s=settings()
    return {'configured':bool(s.supabase_url and s.supabase_publishable_key),
            'ai_configured':bool(s.gemini_api_key), 'name':'Atlatic AI', 'version':s.app_version}

class Credentials(BaseModel):
    email: str = Field(min_length=5,max_length=254,pattern=r'^[^\s@]+@[^\s@]+\.[^\s@]+$')
    password: str = Field(min_length=8,max_length=128)

class Refresh(BaseModel):
    refresh_token: str = Field(min_length=10,max_length=4096)

_auth_attempts = defaultdict(deque)
def auth_limit(req):
    key=req.client.host if req.client else 'unknown'
    now=time.monotonic()
    if len(_auth_attempts)>2000:
        _auth_attempts.clear()
    q=_auth_attempts[key]
    while q and q[0]<now-300: q.popleft()
    if len(q)>=15: raise HTTPException(429,'Too many sign-in attempts. Wait five minutes.')
    q.append(now)

@app.post('/api/auth/login')
def login(body:Credentials,request:Request):
    auth_limit(request)
    return upstream('POST','/auth/v1/token?grant_type=password',json=body.model_dump())

@app.post('/api/auth/signup')
def signup(body:Credentials,request:Request):
    auth_limit(request)
    # Use a server-configured destination, never the untrusted request Host header.
    redirect = settings().app_origin.rstrip('/') + '/auth/confirmed'
    return upstream('POST','/auth/v1/signup?' + urlencode({'redirect_to': redirect}),json=body.model_dump())

@app.post('/api/auth/refresh')
def refresh(body:Refresh):
    return upstream('POST','/auth/v1/token?grant_type=refresh_token',json=body.model_dump())

@app.post('/api/auth/logout')
def logout(p:Principal=Depends(principal)):
    upstream('POST','/auth/v1/logout',p.token)
    return {'ok':True}

@app.get('/api/me')
def me(p:Principal=Depends(principal)):
    return {'id':p.subject,'email':p.email,'admin':rpc(p,'is_atlatic_admin')}

@app.get('/api/documents')
def documents(p:Principal=Depends(principal)):
    return {'documents':rest(p,'GET','documents',params={'select':'id,title,status,chunk_count,created_at','order':'created_at.desc','limit':'100'})}

@app.post('/api/documents')
def upload(file:UploadFile=File(...),p:Principal=Depends(principal)):
    if not settings().gemini_api_key: raise HTTPException(503,'Configure the AI key before uploading.')
    if not rpc(p,'reserve_usage',{'operation':'ingest'}): raise HTTPException(429,'Daily document quota reached.')
    blob=file.file.read(settings().max_upload_bytes+1)
    result=ingest(p,blob,Path(file.filename or 'document.txt').name)
    audit(p,'ingest_ready',{'document_id':result['id'],'chunks':result['chunks']})
    return result

@app.post('/api/documents/sample')
def sample(p:Principal=Depends(principal)):
    if not settings().gemini_api_key: raise HTTPException(503,'Configure the AI key before uploading.')
    if not rpc(p,'reserve_usage',{'operation':'ingest'}): raise HTTPException(429,'Daily document quota reached.')
    return ingest(p,(BASE.parent/'samples/handbook.txt').read_bytes(),'NovaCore handbook.txt')

@app.delete('/api/documents/{document_id}')
def delete_document(document_id:uuid.UUID,p:Principal=Depends(principal)):
    rows=rest(p,'GET','documents',params={'id':f'eq.{document_id}','select':'id,s3_key'})
    if not rows: raise HTTPException(404,'Document not found.')
    # Delete database evidence first: an object-store failure cannot leave searchable deleted data.
    rest(p,'DELETE','documents',params={'id':f'eq.{document_id}'})
    cleanup=True
    try: upstream('DELETE','/storage/v1/object/documents',p.token,json={'prefixes':[rows[0]['s3_key']]})
    except HTTPException: cleanup=False
    audit(p,'document_deleted',{'document_id':str(document_id),'storage_cleanup':cleanup})
    return {'deleted':True,'storage_cleanup':cleanup}

class Conversation(BaseModel):
    title:str=Field(default='New conversation',min_length=1,max_length=120)

@app.post('/api/conversations')
def create_conversation(body:Conversation,p:Principal=Depends(principal)):
    return rest(p,'POST','conversations',json={'title':body.title})[0]

@app.get('/api/conversations')
def conversations(p:Principal=Depends(principal)):
    return {'conversations':rest(p,'GET','conversations',params={'select':'id,title,created_at','order':'created_at.desc','limit':'50'})}

def own_conversation(p,cid):
    if not rest(p,'GET','conversations',params={'id':f'eq.{cid}','select':'id'}):
        raise HTTPException(404,'Conversation not found.')

@app.get('/api/conversations/{cid}/messages')
def messages(cid:uuid.UUID,p:Principal=Depends(principal)):
    own_conversation(p,cid)
    rows=rest(p,'GET','chat_messages',params={'conversation_id':f'eq.{cid}','order':'id.desc','limit':'100'})
    return {'messages':list(reversed(rows))}

class Ask(BaseModel):
    question:str=Field(min_length=3,max_length=2000)
    conversation_id:uuid.UUID

@app.post('/api/chat')
def ask(body:Ask,p:Principal=Depends(principal)):
    start=time.monotonic()
    own_conversation(p,body.conversation_id)
    if classify_input(body.question):
        audit(p,'guardrail_input_blocked')
        raise HTTPException(400,'This request was blocked by an input guardrail.')
    if any(x in body.question.lower() for x in ('delete','export','send to','update policy')):
        record=rest(p,'POST','approvals',json={'question':body.question})[0]
        return {'answer':'Your request is waiting for administrator review. A decision records approval only; no action is executed.',
                'sources':[],'status':'pending_approval','approval_id':record['id']}
    if not settings().gemini_api_key: raise HTTPException(503,'AI is not configured yet.')
    if not rpc(p,'reserve_usage',{'operation':'chat'}): raise HTTPException(429,'Daily chat quota reached.')
    prior=rest(p,'GET','chat_messages',params={'conversation_id':f'eq.{body.conversation_id}',
               'select':'role,content','order':'id.desc','limit':str(settings().memory_turns*2)})
    result=chat(p,body.question,list(reversed(prior)))
    elapsed=int((time.monotonic()-start)*1000)
    rpc(p,'save_turn',{'cid':str(body.conversation_id),'question':body.question,'response':result['answer'],
        'response_sources':result.get('sources',[]),'response_status':result['status'],'elapsed_ms':elapsed})
    audit(p,'chat_completed',{'status':result['status'],'latency_ms':elapsed})
    return {k:result[k] for k in ('answer','sources','status')} | {
        'latency_ms':elapsed, 'retrieval_mode':result.get('retrieval_mode','vector')}

class Feedback(BaseModel):
    rating:int=Field(ge=-1,le=1)
    note:str=Field(default='',max_length=500)

@app.post('/api/feedback')
def feedback(body:Feedback,p:Principal=Depends(principal)):
    if body.rating==0: raise HTTPException(400,'Rating must be -1 or 1.')
    rest(p,'POST','feedback',json=body.model_dump())
    return {'saved':True}

@app.get('/api/approvals')
def approvals(p:Principal=Depends(principal)):
    return {'approvals':rest(p,'GET','approvals',params={'order':'created_at.desc','limit':'100'})}

class Decision(BaseModel):
    approve:bool

@app.post('/api/approvals/{approval_id}/decision')
def decision(approval_id:uuid.UUID,body:Decision,p:Principal=Depends(principal)):
    require_admin(p)
    if not rpc(p,'decide_approval',{'approval_id':str(approval_id),'approve':body.approve}):
        raise HTTPException(409,'Request already reviewed or not found.')
    return {'status':'approved' if body.approve else 'rejected','executed':False}

@app.get('/api/activity')
def activity(p:Principal=Depends(principal)):
    return {'events':rest(p,'GET','audit_events',params={'order':'created_at.desc','limit':'50'})}
