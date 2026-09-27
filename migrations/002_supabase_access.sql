-- Apply in Supabase SQL Editor after 001. API uses the server-only service role.
create table if not exists public.arp_documents (
 collection text not null, id text not null, room_id text, user_id text, phone text,
 doc jsonb not null, seq bigint not null, primary key(collection,id)
);
create index if not exists arp_documents_owner_idx on public.arp_documents(user_id,collection);
create unique index if not exists arp_phone_owner_idx on public.arp_documents(phone) where collection = 'phone_links';
alter table public.arp_documents enable row level security;
revoke all on public.arp_documents from anon, authenticated;
grant select on public.arp_documents to authenticated;
grant select, insert, update, delete on public.arp_documents to service_role;
drop policy if exists arp_owner_read on public.arp_documents;
create policy arp_owner_read on public.arp_documents for select to authenticated using (user_id = (select auth.uid())::text);
-- Client roles cannot create/alter quotes, tenancy evidence, recipient details or payment states.
alter table public.arp_fin_tenancies enable row level security;
alter table public.arp_fin_quotes enable row level security;
alter table public.arp_fin_payments enable row level security;
alter table public.arp_fin_events enable row level security;
revoke all on public.arp_fin_tenancies, public.arp_fin_quotes, public.arp_fin_payments, public.arp_fin_events from anon, authenticated;
grant select, insert, update, delete on public.arp_fin_tenancies, public.arp_fin_quotes, public.arp_fin_payments, public.arp_fin_events to service_role;
-- Photos are served only through the authenticated API, with a second ownership check.
insert into storage.buckets(id,name,public,file_size_limit,allowed_mime_types)
values ('housing-evidence','housing-evidence',false,5242880,array['image/jpeg'])
on conflict(id) do update set public=false, file_size_limit=5242880, allowed_mime_types=array['image/jpeg'];
