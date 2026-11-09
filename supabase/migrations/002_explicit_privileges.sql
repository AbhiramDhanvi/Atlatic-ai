-- Supabase default privileges may grant anon EXECUTE explicitly, independently of PUBLIC.
revoke all on function public.is_atlatic_admin(),public.reserve_usage(text),public.commit_document(uuid,text,text,jsonb),public.match_chunks(extensions.vector,float,int),public.save_turn(uuid,text,text,jsonb,text,int),public.decide_approval(uuid,boolean) from anon;
revoke all on public.documents,public.document_chunks,public.conversations,public.chat_messages,public.approvals,public.feedback,public.audit_events from authenticated;
grant select,insert,update,delete on public.documents,public.document_chunks,public.conversations,public.chat_messages to authenticated;
grant select,insert on public.approvals,public.feedback,public.audit_events to authenticated;
create policy deny_direct_admin_access on public.atlatic_admins for all to authenticated using(false) with check(false);
create policy deny_direct_usage_access on public.usage_events for all to authenticated using(false) with check(false);
