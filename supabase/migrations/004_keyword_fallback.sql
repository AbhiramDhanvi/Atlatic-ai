-- Search remains private and available when the embedding provider is unavailable.
create function public.keyword_chunks(search_query text, match_count int default 5)
returns table(id uuid,document_id uuid,title text,page int,content text,score double precision)
language sql stable security invoker set search_path='' as $$
 with q as (
   select websearch_to_tsquery('english',regexp_replace(left(search_query,2000),'[[:space:]]+',' OR ','g')) as terms
 )
 select c.id,c.document_id,d.title,c.page,c.content,
 ts_rank_cd(to_tsvector('english',d.title || ' ' || c.content),q.terms)::double precision
 from public.document_chunks c join public.documents d on d.id=c.document_id cross join q
 where c.owner_id=auth.uid() and d.status='ready'
 and to_tsvector('english',d.title || ' ' || c.content) @@ q.terms
 order by ts_rank_cd(to_tsvector('english',d.title || ' ' || c.content),q.terms) desc,c.id
 limit least(greatest(match_count,1),10);
$$;
revoke all on function public.keyword_chunks(text,int) from public,anon;
grant execute on function public.keyword_chunks(text,int) to authenticated;
