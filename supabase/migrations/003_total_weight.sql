-- Per-user total cooked weight of a recipe, for logging by grams. Run after 002.
alter table public.food_prefs
  alter column servings drop not null,
  add column if not exists total_weight_g numeric check (total_weight_g > 0 and total_weight_g <= 100000);
