-- Serving splits: batch recipes and per-user "makes N servings" overrides.
-- Run in the Supabase SQL Editor after 001_init.sql.

alter table public.foods
  add column if not exists is_batch boolean not null default false,   -- macros are for the entire batch
  add column if not exists book_servings numeric;                      -- the book's "makes N" for per-serving macros

-- Backfill recipes imported before this migration.
update public.foods set is_batch = true where serving_desc ilike '%entire batch%';
update public.foods
  set book_servings = (regexp_match(serving_desc, 'makes (\d+)'))[1]::numeric
  where book_servings is null and serving_desc ~ 'makes \d+';

-- How many portions THIS user splits a recipe into. Never changes the shared recipe.
create table if not exists public.food_prefs (
  user_id uuid not null references auth.users(id) on delete cascade,
  food_id bigint not null references public.foods(id) on delete cascade,
  servings numeric not null check (servings > 0 and servings <= 200),
  primary key (user_id, food_id)
);

alter table public.food_prefs enable row level security;
create policy prefs_owner on public.food_prefs for all
  using (user_id = auth.uid()) with check (user_id = auth.uid());
