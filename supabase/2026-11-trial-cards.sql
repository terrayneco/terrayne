-- Run once in Supabase: SQL Editor -> New query -> paste -> Run.
-- One free trial per card (Nov 2026). Card fingerprints only (not card numbers); readable by the server only.
create table if not exists public.trial_cards (
  fingerprint text primary key,
  customer text not null,
  created_at timestamptz not null default now()
);
alter table public.trial_cards enable row level security;
