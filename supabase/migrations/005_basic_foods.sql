-- Basic foods (eggs, rice, chicken breast, ...) from the USDA FoodData Central SR Legacy dataset (public domain).
-- Run after 004, then run backend/scripts/seed_basic_foods.py once to load the data.

alter table public.foods drop constraint if exists foods_source_type_check;
alter table public.foods add constraint foods_source_type_check
  check (source_type in ('recipe', 'restaurant', 'custom', 'basic'));

-- Basic foods store macros PER 100 g (serving_desc = '100 g'); portions = [{"unit": "large", "grams": 50}, ...]
alter table public.foods add column if not exists portions jsonb;
alter table public.foods add column if not exists fiber_per_100g numeric;
alter table public.foods add column if not exists fdc_id integer;
create unique index if not exists foods_fdc_uniq on public.foods (fdc_id) where fdc_id is not null;

-- Everyone can see basic foods (the backend connects directly, but keep the RLS policy consistent).
drop policy if exists foods_visible on public.foods;
create policy foods_visible on public.foods for select
  using (
    owner_id = auth.uid()
    or source_type in ('restaurant', 'basic')
    or exists (select 1 from public.user_books ub where ub.book_id = foods.book_id and ub.user_id = auth.uid())
  );
