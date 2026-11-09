-- Transactional fixtures only: rollback leaves no users, files, or test records.
begin;
insert into auth.users(id,email) values
('11111111-1111-4111-8111-111111111111','fixture-a@example.invalid'),
('22222222-2222-4222-8222-222222222222','fixture-b@example.invalid');
insert into public.documents(id,owner_id,title,s3_key) values
('33333333-3333-4333-8333-333333333333','11111111-1111-4111-8111-111111111111','Private A','11111111-1111-4111-8111-111111111111/a.txt');
insert into public.conversations(id,owner_id,title) values
('44444444-4444-4444-8444-444444444444','11111111-1111-4111-8111-111111111111','Private conversation');
insert into public.chat_messages(conversation_id,owner_id,role,content) values
('44444444-4444-4444-8444-444444444444','11111111-1111-4111-8111-111111111111','user','Private message');
insert into storage.objects(bucket_id,name) values('documents','11111111-1111-4111-8111-111111111111/a.txt');
insert into public.document_chunks(document_id,owner_id,page,content,embedding) values('33333333-3333-4333-8333-333333333333','11111111-1111-4111-8111-111111111111',1,'secretalpha private A evidence',array_fill(.1::real,array[768])::extensions.vector(768));
set local role authenticated;
select set_config('request.jwt.claims','{"sub":"22222222-2222-4222-8222-222222222222","role":"authenticated"}',true);
do $$ begin
 if (select count(*) from public.documents)<>0 then raise exception 'FAIL document isolation'; end if;
 if (select count(*) from public.chat_messages)<>0 then raise exception 'FAIL message isolation'; end if;
 if (select count(*) from public.conversations)<>0 then raise exception 'FAIL conversation isolation'; end if;
 if (select count(*) from storage.objects where bucket_id='documents')<>0 then raise exception 'FAIL file isolation'; end if;
 if public.is_atlatic_admin() then raise exception 'FAIL admin escalation'; end if;
 if has_function_privilege('anon','public.reserve_usage(text)','EXECUTE') then raise exception 'FAIL anon execute'; end if;
end $$;
do $$ declare denied boolean:=false; begin
 begin
 insert into public.documents(id,owner_id,title,s3_key) values(gen_random_uuid(),'11111111-1111-4111-8111-111111111111','Attack','attack.txt');
 exception when insufficient_privilege then denied:=true; end;
 if not denied then raise exception 'FAIL forged owner insertion'; end if;
end $$;
do $$ declare denied boolean:=false; begin
 begin
 perform public.save_turn('44444444-4444-4444-8444-444444444444','attack','attack','[]','answered',1);
 exception when raise_exception then denied:=true; end;
 if not denied then raise exception 'FAIL cross-owner conversation'; end if;
end $$;
do $$ declare denied boolean:=false; begin
 begin perform public.decide_approval(gen_random_uuid(),true);
 exception when raise_exception then denied:=true; end;
 if not denied then raise exception 'FAIL non-admin decision'; end if;
end $$;
select public.commit_document('55555555-5555-4555-8555-555555555555','Own handbook','22222222-2222-4222-8222-222222222222/b.txt',
 jsonb_build_array(jsonb_build_object('page',1,'content','Annual leave is 20 days.','embedding',to_jsonb(array_fill(.1::float,array[768])))));
do $$ declare hits int; begin
 select count(*) into hits from public.match_chunks(array_fill(.1::real,array[768])::extensions.vector(768),.1,5);
 if hits<>1 then raise exception 'FAIL own-vector search'; end if;
end $$;
do $$ declare n int; begin
 for n in 1..30 loop
 if not public.reserve_usage('chat') then raise exception 'FAIL early quota'; end if;
 end loop;
 if public.reserve_usage('chat') then raise exception 'FAIL quota enforcement'; end if;
end $$;
do $$ begin
 if (select count(*) from public.keyword_chunks('annual leave',5))<>1 then raise exception 'FAIL own keyword retrieval'; end if;
 if (select count(*) from public.keyword_chunks('secretalpha',5))<>0 then raise exception 'FAIL keyword cross-user isolation'; end if;
 if has_function_privilege('anon','public.keyword_chunks(text,int)','EXECUTE') then raise exception 'FAIL anonymous keyword access'; end if;
end $$;
select json_build_object('passed',true,'checks',14,'fixture_data','rolled back') as rls_verification;
rollback;
