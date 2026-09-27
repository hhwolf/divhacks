-- Public furniture asset catalog. Apply in Supabase SQL Editor after 002.
-- Binary GLB/PNG files live in Supabase Storage; Postgres stores searchable metadata.

insert into storage.buckets(id, name, public, file_size_limit, allowed_mime_types)
values (
  'furniture-assets',
  'furniture-assets',
  true,
  20971520,
  array['model/gltf-binary', 'image/png', 'application/json']
)
on conflict(id) do update
set public = true,
    file_size_limit = 20971520,
    allowed_mime_types = array['model/gltf-binary', 'image/png', 'application/json'];

create table if not exists public.arp_furniture_assets (
  asset_path text primary key,
  furniture_id text,
  asset_kind text not null check (asset_kind in ('glb', 'thumbnail', 'manifest')),
  storage_bucket text not null default 'furniture-assets',
  storage_path text not null unique,
  content_type text not null,
  byte_size bigint not null check (byte_size >= 0),
  sha256 text not null,
  public_url text not null,
  metadata jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create index if not exists arp_furniture_assets_furniture_idx
  on public.arp_furniture_assets(furniture_id, asset_kind);

alter table public.arp_furniture_assets enable row level security;
revoke all on public.arp_furniture_assets from anon, authenticated;
grant select on public.arp_furniture_assets to anon, authenticated;
grant select, insert, update, delete on public.arp_furniture_assets to service_role;

drop policy if exists arp_furniture_assets_public_read on public.arp_furniture_assets;
create policy arp_furniture_assets_public_read
  on public.arp_furniture_assets for select
  to anon, authenticated
  using (true);

drop policy if exists arp_furniture_assets_storage_public_read on storage.objects;
create policy arp_furniture_assets_storage_public_read
  on storage.objects for select
  to anon, authenticated
  using (bucket_id = 'furniture-assets');

drop policy if exists arp_furniture_assets_storage_service_write on storage.objects;
create policy arp_furniture_assets_storage_service_write
  on storage.objects for all
  to service_role
  using (bucket_id = 'furniture-assets')
  with check (bucket_id = 'furniture-assets');
