-- Atlatic AI: private, user-scoped documents, vectors, memory, approvals and audit.
create extension if not exists vector with schema extensions;
create table public.atlatic_admins (user_id uuid primary key references auth.users(id) on delete cascade);
alter table public.atlatic_admins enable row level security;
revoke all on public.atlatic_admins from anon, authenticated;
create function public.is_atlatic_admin() returns boolean language sql stable security definer
set search_path = '' as $$
 select exists(select 1 from public.atlatic_admins where user_id = (select auth.uid()));
$$;
revoke all on function public.is_atlatic_admin() from public;
grant execute on function public.is_atlatic_admin() to authenticated;

create table public.documents (
 id uuid primary key, owner_id uuid not null default auth.uid() references auth.users(id) on delete cascade,
 title text not null check(length(title) between 1 and 180), s3_key text not null unique,
 status text not null default 'ready' check(status in ('ready','failed')),
 chunk_count int not null default 0, created_at timestamptz not null default now(),
 unique(id,owner_id)
);
create index on public.documents(owner_id,created_at desc);
create table public.document_chunks (
 id uuid primary key default gen_random_uuid(), document_id uuid not null,
 owner_id uuid not null default auth.uid() references auth.users(id) on delete cascade,
 page int not null check(page>0), content text not null check(length(content)<=1500),
 embedding extensions.vector(768) not null,
 foreign key(document_id,owner_id) references public.documents(id,owner_id) on delete cascade
);
create index on public.document_chunks(owner_id,document_id);
create table public.conversations (
 id uuid primary key default gen_random_uuid(), owner_id uuid not null default auth.uid() references auth.users(id) on delete cascade,
 title text not null default 'New conversation', created_at timestamptz not null default now(), unique(id,owner_id)
);
create table public.chat_messages (
 id bigint generated always as identity primary key, conversation_id uuid not null,
 owner_id uuid not null default auth.uid(), role text not null check(role in ('user','assistant')),
 content text not null, sources jsonb not null default '[]', status text not null default 'answered',
 latency_ms int, created_at timestamptz not null default now(),
 foreign key(conversation_id,owner_id) references public.conversations(id,owner_id) on delete cascade
);
create index on public.chat_messages(owner_id,conversation_id,id desc);
create table public.approvals (
 id uuid primary key default gen_random_uuid(), owner_id uuid not null default auth.uid() references auth.users(id) on delete cascade,
 question text not null check(length(question)<=2000), status text not null default 'pending' check(status in ('pending','approved','rejected')),
 reviewer uuid references auth.users(id), created_at timestamptz not null default now(), reviewed_at timestamptz
);
create table public.feedback (
 id bigint generated always as identity primary key, owner_id uuid not null default auth.uid() references auth.users(id) on delete cascade,
 rating int not null check(rating in (-1,1)), note text not null default '' check(length(note)<=500), created_at timestamptz default now()
);
create table public.audit_events (
 id bigint generated always as identity primary key, owner_id uuid not null default auth.uid() references auth.users(id) on delete cascade,
 action text not null, detail jsonb not null default '{}', created_at timestamptz default now()
);
create index on public.audit_events(owner_id,created_at desc);
create table public.usage_events (owner_id uuid not null references auth.users(id) on delete cascade, action text not null, created_at timestamptz default now());
create index on public.usage_events(created_at,owner_id,action);
alter table public.usage_events enable row level security;
revoke all on public.usage_events from anon,authenticated;

-- Deny anonymous access. All backend requests carry the verified user's JWT.
do $$ declare t text; begin
 foreach t in array array['documents','document_chunks','conversations','chat_messages','feedback','audit_events'] loop
 execute format('alter table public.%I enable row level security',t);
 execute format('revoke all on public.%I from anon',t);
 execute format('create policy own_rows on public.%I for all to authenticated using (owner_id = (select auth.uid())) with check (owner_id = (select auth.uid()))',t);
 end loop;
end $$;
grant select,insert,update,delete on public.documents,public.document_chunks,public.conversations,public.chat_messages to authenticated;
grant select,insert on public.feedback,public.audit_events to authenticated;
revoke update,delete on public.audit_events,public.feedback from authenticated;
grant usage,select on all sequences in schema public to authenticated;
alter table public.approvals enable row level security;
revoke all on public.approvals from anon;
grant select,insert on public.approvals to authenticated;
revoke update,delete on public.approvals from authenticated;
create policy approval_read on public.approvals for select to authenticated using(owner_id=(select auth.uid()) or public.is_atlatic_admin());
create policy approval_insert on public.approvals for insert to authenticated with check(owner_id=(select auth.uid()) and status='pending' and reviewer is null and reviewed_at is null);

create function public.reserve_usage(operation text) returns boolean language plpgsql security definer set search_path='' as $$
declare personal int; total int; begin
 if auth.uid() is null or operation not in ('chat','ingest') then return false; end if;
 perform pg_advisory_xact_lock(1945819123);
 select count(*) into personal from public.usage_events where owner_id=auth.uid() and action=operation and created_at>=date_trunc('day',now());
 select count(*) into total from public.usage_events where action=operation and created_at>=date_trunc('day',now());
 if personal >= (case when operation='chat' then 30 else 5 end) or total >= (case when operation='chat' then 100 else 20 end) then return false; end if;
 insert into public.usage_events(owner_id,action) values(auth.uid(),operation);
 return true;
end $$;

create function public.commit_document(doc_id uuid, doc_title text, object_path text, parts jsonb)
returns uuid language plpgsql security invoker set search_path='' as $$
begin
 if auth.uid() is null or split_part(object_path,'/',1) <> auth.uid()::text then raise exception 'access denied'; end if;
 if jsonb_array_length(parts) not between 1 and 40 then raise exception 'invalid chunk count'; end if;
 if (select count(*) from public.documents where owner_id=auth.uid()) >= 20 then raise exception 'document limit reached'; end if;
 insert into public.documents(id,title,s3_key,chunk_count) values(doc_id,doc_title,object_path,jsonb_array_length(parts));
 insert into public.document_chunks(document_id,page,content,embedding)
 select doc_id,(x->>'page')::int,x->>'content',(x->>'embedding')::extensions.vector(768) from jsonb_array_elements(parts) x;
 return doc_id;
end $$;

create function public.match_chunks(query_embedding extensions.vector(768),match_threshold float default .35,match_count int default 5)
returns table(id uuid,document_id uuid,title text,page int,content text,score double precision)
language sql stable security invoker set search_path='' as $$
 select c.id,c.document_id,d.title,c.page,c.content,
 1-(c.embedding operator(extensions.<=>) query_embedding) as score
 from public.document_chunks c join public.documents d on d.id=c.document_id
 where c.owner_id=auth.uid() and d.status='ready'
 and 1-(c.embedding operator(extensions.<=>) query_embedding)>=match_threshold
 order by c.embedding operator(extensions.<=>) query_embedding limit least(greatest(match_count,1),10);
$$;

create function public.save_turn(cid uuid,question text,response text,response_sources jsonb,response_status text,elapsed_ms int)
returns void language plpgsql security invoker set search_path='' as $$
begin
 if not exists(select 1 from public.conversations where id=cid and owner_id=auth.uid()) then raise exception 'conversation not found'; end if;
 insert into public.chat_messages(conversation_id,role,content) values(cid,'user',question);
 insert into public.chat_messages(conversation_id,role,content,sources,status,latency_ms) values(cid,'assistant',response,response_sources,response_status,elapsed_ms);
end $$;

create function public.decide_approval(approval_id uuid,approve boolean) returns boolean
language plpgsql security definer set search_path='' as $$
declare changed uuid; begin
 if not public.is_atlatic_admin() then raise exception 'admin required'; end if;
 update public.approvals set status=case when approve then 'approved' else 'rejected' end,reviewer=auth.uid(),reviewed_at=now()
 where id=approval_id and status='pending' returning id into changed;
 if changed is null then return false; end if;
 insert into public.audit_events(owner_id,action,detail) values(auth.uid(),'approval_decided',jsonb_build_object('id',changed,'approved',approve));
 return true;
end $$;
revoke all on function public.reserve_usage(text),public.commit_document(uuid,text,text,jsonb),public.match_chunks(extensions.vector,float,int),public.save_turn(uuid,text,text,jsonb,text,int),public.decide_approval(uuid,boolean) from public;
grant execute on function public.reserve_usage(text),public.commit_document(uuid,text,text,jsonb),public.match_chunks(extensions.vector,float,int),public.save_turn(uuid,text,text,jsonb,text,int),public.decide_approval(uuid,boolean) to authenticated;

insert into storage.buckets(id,name,public,file_size_limit,allowed_mime_types)
values('documents','documents',false,5242880,array['application/octet-stream']) on conflict(id) do nothing;
create policy own_files_read on storage.objects for select to authenticated using(bucket_id='documents' and (storage.foldername(name))[1]=(select auth.uid())::text);
create policy own_files_insert on storage.objects for insert to authenticated with check(bucket_id='documents' and (storage.foldername(name))[1]=(select auth.uid())::text);
create policy own_files_delete on storage.objects for delete to authenticated using(bucket_id='documents' and (storage.foldername(name))[1]=(select auth.uid())::text);
