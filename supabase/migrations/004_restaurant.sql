-- Restaurant lookups: per-user log (rate limit + binds saves to what Claude returned) and shared-cache dedupe.
-- Run after 003.

alter table public.foods add column if not exists source_quote text;

create table if not exists public.lookup_log (
  id bigint generated always as identity primary key,
  user_id uuid not null references auth.users(id) on delete cascade,
  query text not null,
  result jsonb,
  created_at timestamptz not null default now()
);
create index if not exists lookup_log_user_time_idx on public.lookup_log (user_id, created_at);
alter table public.lookup_log enable row level security;
create policy lookup_owner on public.lookup_log for all
  using (user_id = auth.uid()) with check (user_id = auth.uid());

-- One shared row per restaurant + item name.
create unique index if not exists foods_restaurant_uniq
  on public.foods (lower(restaurant), lower(name)) where source_type = 'restaurant';
