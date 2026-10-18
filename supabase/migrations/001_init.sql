-- Calorie tracker initial schema.
-- Run in the Supabase SQL Editor. Users come from Supabase Auth (auth.users).
-- FastAPI connects directly to Postgres and filters by user_id; RLS is a backup layer.

create table public.profiles (
  user_id uuid primary key references auth.users(id) on delete cascade,
  sex text check (sex in ('male', 'female')),
  birthdate date,
  height_cm numeric,
  activity_level text not null default 'sedentary'
    check (activity_level in ('sedentary', 'light', 'moderate', 'high', 'extreme')),
  unit_pref text not null default 'imperial' check (unit_pref in ('imperial', 'metric')),
  goal_rate_kg_per_week numeric not null default 0,
  goal_mode text not null default 'tdee' check (goal_mode in ('tdee', 'adaptive')),
  adaptive_opt_out boolean not null default false,
  exercise_eat_back text not null default 'none' check (exercise_eat_back in ('none', 'half', 'all')),
  created_at timestamptz not null default now()
);

create table public.weights (
  id bigint generated always as identity primary key,
  user_id uuid not null references auth.users(id) on delete cascade,
  date date not null,
  weight_kg numeric not null,
  unique (user_id, date)
);

-- Books are shared records of parsed FACTS only; no files or page images are stored.
create table public.books (
  id bigint generated always as identity primary key,
  title text not null,
  file_hash text not null unique,
  status text not null default 'processing' check (status in ('processing', 'ready', 'failed')),
  created_at timestamptz not null default now()
);

-- A user gets access to a book only by uploading a file with a matching hash.
create table public.user_books (
  user_id uuid not null references auth.users(id) on delete cascade,
  book_id bigint not null references public.books(id) on delete cascade,
  primary key (user_id, book_id)
);

-- owner_id is null for the public restaurant cache and for book recipes (access via user_books).
create table public.foods (
  id bigint generated always as identity primary key,
  owner_id uuid references auth.users(id) on delete cascade,
  source_type text not null check (source_type in ('recipe', 'restaurant', 'custom')),
  book_id bigint references public.books(id) on delete cascade,
  restaurant text,
  name text not null,
  serving_desc text,
  calories numeric not null,
  protein_g numeric not null default 0,
  carbs_g numeric not null default 0,
  fat_g numeric not null default 0,
  fiber_g numeric,
  ingredients jsonb,
  is_estimate boolean not null default false,
  estimate_note text,
  source_url text,
  source_page int,
  created_at timestamptz not null default now()
);
create index foods_name_idx on public.foods (lower(name));
create index foods_book_idx on public.foods (book_id);
create index foods_owner_idx on public.foods (owner_id);

-- Per-user confirmation after the first-use side-by-side check.
create table public.food_verifications (
  user_id uuid not null references auth.users(id) on delete cascade,
  food_id bigint not null references public.foods(id) on delete cascade,
  verified_at timestamptz not null default now(),
  primary key (user_id, food_id)
);

create table public.food_logs (
  id bigint generated always as identity primary key,
  user_id uuid not null references auth.users(id) on delete cascade,
  date date not null,
  meal_slot text not null default 'snack' check (meal_slot in ('breakfast', 'lunch', 'dinner', 'snack')),
  food_id bigint references public.foods(id) on delete set null,
  name text not null,
  servings numeric not null default 1,
  calories numeric not null,
  protein_g numeric not null default 0,
  carbs_g numeric not null default 0,
  fat_g numeric not null default 0,
  is_estimate boolean not null default false,
  created_at timestamptz not null default now()
);
create index food_logs_user_date_idx on public.food_logs (user_id, date);

-- User marks a day fully logged; used for adaptive-mode eligibility.
create table public.complete_days (
  user_id uuid not null references auth.users(id) on delete cascade,
  date date not null,
  primary key (user_id, date)
);

create table public.exercise_logs (
  id bigint generated always as identity primary key,
  user_id uuid not null references auth.users(id) on delete cascade,
  date date not null,
  type text not null,
  duration_min numeric,
  distance_km numeric,
  kcal_burned numeric not null,
  source text not null default 'manual' check (source in ('manual', 'shortcut', 'health_export')),
  created_at timestamptz not null default now()
);
create index exercise_logs_user_date_idx on public.exercise_logs (user_id, date);

create table public.goal_history (
  id bigint generated always as identity primary key,
  user_id uuid not null references auth.users(id) on delete cascade,
  effective_date date not null,
  tdee_estimate numeric not null,
  calorie_target int not null,
  protein_g int,
  carbs_g int,
  fat_g int,
  method text not null check (method in ('formula', 'adaptive')),
  created_at timestamptz not null default now()
);

-- Row Level Security: enabled on everything; owners only.
alter table public.profiles enable row level security;
alter table public.weights enable row level security;
alter table public.books enable row level security;
alter table public.user_books enable row level security;
alter table public.foods enable row level security;
alter table public.food_verifications enable row level security;
alter table public.food_logs enable row level security;
alter table public.complete_days enable row level security;
alter table public.exercise_logs enable row level security;
alter table public.goal_history enable row level security;

create policy profiles_owner on public.profiles for all using (user_id = auth.uid()) with check (user_id = auth.uid());
create policy weights_owner on public.weights for all using (user_id = auth.uid()) with check (user_id = auth.uid());
create policy user_books_owner on public.user_books for all using (user_id = auth.uid()) with check (user_id = auth.uid());
create policy verif_owner on public.food_verifications for all using (user_id = auth.uid()) with check (user_id = auth.uid());
create policy logs_owner on public.food_logs for all using (user_id = auth.uid()) with check (user_id = auth.uid());
create policy complete_owner on public.complete_days for all using (user_id = auth.uid()) with check (user_id = auth.uid());
create policy exercise_owner on public.exercise_logs for all using (user_id = auth.uid()) with check (user_id = auth.uid());
create policy goals_owner on public.goal_history for all using (user_id = auth.uid()) with check (user_id = auth.uid());

create policy books_member on public.books for select
  using (exists (select 1 from public.user_books ub where ub.book_id = books.id and ub.user_id = auth.uid()));

create policy foods_visible on public.foods for select
  using (
    owner_id = auth.uid()
    or source_type = 'restaurant'
    or exists (select 1 from public.user_books ub where ub.book_id = foods.book_id and ub.user_id = auth.uid())
  );
create policy foods_custom_write on public.foods for all
  using (owner_id = auth.uid() and source_type = 'custom')
  with check (owner_id = auth.uid() and source_type = 'custom');
