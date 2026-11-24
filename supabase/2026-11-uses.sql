-- Monday Brief land-use choice: which kinds of scheme each user wants in their brief and alerts.
-- Paste into Supabase > SQL Editor and run once (safe to re-run).
-- null = everything (the default). Otherwise any of: res (new homes), ma (office-to-home, Class MA),
-- com (commercial), ind (industrial & logistics).
alter table public.profiles add column if not exists brief_uses text[];
alter table public.profiles drop constraint if exists profiles_brief_uses_check;
alter table public.profiles add constraint profiles_brief_uses_check
  check (brief_uses is null or (cardinality(brief_uses) between 1 and 4 and brief_uses <@ array['res','ma','com','ind']));
