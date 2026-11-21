-- Growth: free sample-brief sign-ups and anonymous funnel counts.
-- Paste into Supabase → SQL Editor → Run. Safe to run more than once.

-- ============ Free sample brief (email only, no account) ============
-- Written only by the sample-brief Edge Function (service role). Nobody can read it from the browser.
create table if not exists public.brief_signups (
  id bigint generated always as identity primary key,
  email text not null,
  area text not null,
  updates boolean not null default false,          -- ticked "also send me occasional updates"
  source text,                                      -- page the form was on, e.g. /london/ilford/
  token uuid not null default gen_random_uuid(),    -- for the one-click "stop emails" link
  unsubscribed boolean not null default false,
  created_at timestamptz not null default now(),
  constraint brief_signups_fields check (length(email) between 3 and 200 and length(area) <= 60 and length(coalesce(source,'')) <= 120)
);
create index if not exists brief_signups_email on public.brief_signups (email);
create index if not exists brief_signups_created on public.brief_signups (created_at);
alter table public.brief_signups enable row level security;
revoke all on public.brief_signups from anon, authenticated;

-- Spam guard: at most 2 sample briefs per email per day, 300 in total per day.
create or replace function public.brief_signup_limit() returns trigger
language plpgsql security definer set search_path = public as $$
begin
  new.email := lower(trim(new.email));
  if new.email !~ '^[^@\s]+@[^@\s]+\.[^@\s]+$' then raise exception 'Invalid email'; end if;
  if (select count(*) from public.brief_signups where email = new.email and created_at > now() - interval '1 day') >= 2
     or (select count(*) from public.brief_signups where created_at > now() - interval '1 day') >= 300 then
    raise exception 'Too many requests, please try again tomorrow';
  end if;
  return new;
end $$;
drop trigger if exists brief_signup_limit on public.brief_signups;
create trigger brief_signup_limit before insert on public.brief_signups for each row execute function public.brief_signup_limit();

-- ============ Anonymous funnel events ============
-- One row per action (checked a postcode, clicked Start free, started checkout...). No names, emails,
-- IP addresses or cookies: just the action, the page, a short detail and the referring website.
create table if not exists public.events (
  id bigint generated always as identity primary key,
  name text not null,
  page text,
  detail text,
  ref text,
  created_at timestamptz not null default now(),
  constraint events_fields check (name ~ '^[a-z_]{2,40}$' and length(coalesce(page,'')) <= 80
    and length(coalesce(detail,'')) <= 80 and length(coalesce(ref,'')) <= 80)
);
create index if not exists events_created on public.events (created_at);
alter table public.events enable row level security;
drop policy if exists "anyone can log" on public.events;
create policy "anyone can log" on public.events for insert to anon, authenticated with check (true);
revoke select, update, delete on public.events from anon, authenticated;

-- Spam guard: at most 20,000 events a day.
create or replace function public.events_cap() returns trigger
language plpgsql security definer set search_path = public as $$
begin
  if (select count(*) from public.events where created_at > now() - interval '1 day') >= 20000 then
    raise exception 'Event limit reached';
  end if;
  return new;
end $$;
drop trigger if exists events_cap on public.events;
create trigger events_cap before insert on public.events for each row execute function public.events_cap();

-- ============ Admin: growth numbers (admin.html calls this; admins only) ============
create or replace function public.admin_growth(days int default 30)
returns jsonb language plpgsql security definer set search_path = public as $$
declare d int := least(greatest(coalesce(days, 30), 1), 365);
begin
  if not exists (select 1 from public.profiles where id = auth.uid() and is_admin) then
    raise exception 'Admins only';
  end if;
  return jsonb_build_object(
    'days', d,
    'events', coalesce((select jsonb_agg(jsonb_build_object('name', name, 'n', n, 'n7', n7) order by n desc)
       from (select name, count(*) n, count(*) filter (where created_at > now() - interval '7 days') n7
             from public.events where created_at > now() - make_interval(days => d) group by name) e), '[]'::jsonb),
    'pages', coalesce((select jsonb_agg(jsonb_build_object('page', page, 'n', n) order by n desc)
       from (select page, count(*) n from public.events where created_at > now() - make_interval(days => d)
             and name in ('signup_click', 'brief_signup', 'plan_click', 'report_click')
             group by page order by n desc limit 15) p), '[]'::jsonb),
    'refs', coalesce((select jsonb_agg(jsonb_build_object('ref', ref, 'n', n) order by n desc)
       from (select ref, count(*) n from public.events where created_at > now() - make_interval(days => d)
             and coalesce(ref, '') <> '' group by ref order by n desc limit 15) r), '[]'::jsonb),
    'signups', coalesce((select jsonb_agg(jsonb_build_object('email', email, 'area', area, 'updates', updates,
         'source', source, 'unsubscribed', unsubscribed, 'created_at', created_at) order by created_at desc)
       from (select * from public.brief_signups order by created_at desc limit 1000) s), '[]'::jsonb)
  );
end $$;
revoke all on function public.admin_growth(int) from public, anon;
grant execute on function public.admin_growth(int) to authenticated;
