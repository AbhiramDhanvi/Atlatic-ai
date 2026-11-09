-- Operator-managed invitation, consumed only after Supabase confirms the exact email.
create schema if not exists atlatic_private;
revoke all on schema atlatic_private from public,anon,authenticated;
create table atlatic_private.admin_invites(email text primary key);
alter table atlatic_private.admin_invites enable row level security;
revoke all on atlatic_private.admin_invites from public,anon,authenticated;
create function atlatic_private.bootstrap_admin() returns trigger language plpgsql security definer set search_path='' as $$
begin
 if new.email_confirmed_at is not null and exists(select 1 from atlatic_private.admin_invites where email=lower(new.email)) then
 insert into public.atlatic_admins(user_id) values(new.id) on conflict do nothing;
 delete from atlatic_private.admin_invites where email=lower(new.email);
 end if;
 return new;
end $$;
revoke all on function atlatic_private.bootstrap_admin() from public,anon,authenticated;
create trigger atlatic_admin_on_verified_email after insert or update of email_confirmed_at,email on auth.users
for each row execute function atlatic_private.bootstrap_admin();
