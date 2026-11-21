-- Same-day alerts (Team) and the first brief sent straight after sign-up.
-- Paste into Supabase > SQL Editor and run once (safe to re-run).

-- Team members can turn same-day alert emails off on their profile page.
alter table public.profiles add column if not exists instant_email boolean not null default true;

-- What each saved place has already been alerted about, so nothing is sent twice. Server only.
create table if not exists public.instant_alerts (
  place_id bigint not null references public.saved_places(id) on delete cascade,
  ref text not null,
  kind text not null check (kind in ('new','decided')),
  item jsonb,
  sent_at timestamptz not null default now(),
  primary key (place_id, ref, kind)
);
alter table public.instant_alerts enable row level security;

-- Who has had their first brief, so it is only ever sent once per account. Server only.
create table if not exists public.first_briefs (
  user_id uuid primary key references public.profiles(id) on delete cascade,
  week date,
  sent_at timestamptz not null default now()
);
alter table public.first_briefs enable row level security;
